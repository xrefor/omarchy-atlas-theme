"""Explicit, transactional installer for ATLAS boot and login appearance.

The public entry point is ``run(bundle_root, args)``.  It deliberately never
elevates privileges: callers applying to the real root must already be root.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib


STATE_PATH = Path("/var/lib/atlas-bundle/boot-state.json")
LOCK_PATH = Path("/var/lib/atlas-bundle/boot.lock")
TRANSACTIONS_PATH = Path("/var/lib/atlas-bundle/transactions")
SDDM_SELECTOR = Path("/etc/sddm.conf.d/99-atlas-theme.conf")
PLYMOUTH_CONFIG = Path("/etc/plymouth/plymouthd.conf")
PLYMOUTH_DEST = Path("/usr/share/plymouth/themes/atlas")
SDDM_DEST = Path("/usr/share/sddm/themes/atlas")
ESP_CANDIDATES = (Path("/boot"), Path("/efi"), Path("/boot/efi"))
COMPONENTS = ("limine", "plymouth", "sddm")

LIMINE_KEYS = (
    "interface_branding", "interface_branding_color",
    "interface_help_color", "interface_help_color_bright",
    "term_background", "backdrop", "term_palette",
    "term_palette_bright", "term_foreground",
    "term_foreground_bright", "term_background_bright",
)
_LIMINE_KEY_RE = re.compile(
    r"^\s*(" + "|".join(map(re.escape, LIMINE_KEYS)) + r")\s*:", re.I
)
_ATLAS_MARKER_RE = re.compile(r"^\s*#\s*(?:BEGIN|END) ATLAS APPEARANCE\s*$", re.I)


def _rooted(root: Path, path: Path) -> Path:
    """Map an absolute target path under root and reject existing symlinks."""
    root = root.resolve(strict=True)
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"Target path must be absolute: {path}")
    if root != Path("/") and path.resolve(strict=False).is_relative_to(root):
        candidate = path
    else:
        candidate = root / path.relative_to("/")
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Target escapes filesystem root: {path}") from error
    cursor = root
    for index, part in enumerate(relative.parts):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"Target path crosses a symlink: {cursor}")
        if index < len(relative.parts) - 1 and cursor.exists() and not cursor.is_dir():
            raise ValueError(f"Target parent is not a directory: {cursor}")
    resolved_parent = candidate.parent.resolve(strict=False)
    if not resolved_parent.is_relative_to(root):
        raise ValueError(f"Target escapes filesystem root through a symlink: {path}")
    return candidate


def _logical(root: Path, path: Path) -> str:
    root = root.resolve()
    path = path.resolve(strict=False)
    if root == Path("/"):
        return str(path)
    return "/" + str(path.relative_to(root))


def _snapshot(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"Refusing to manage symlink: {path}")
    if not path.exists():
        return {"kind": "absent"}
    if not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return {
        "kind": "file",
        "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        "mode": stat.S_IMODE(path.stat().st_mode),
    }


def _file_value(data: bytes | str, mode: int = 0o644) -> dict:
    if isinstance(data, str):
        data = data.encode()
    return {"kind": "file", "data": base64.b64encode(data).decode("ascii"), "mode": mode}


def _write(path: Path, item: dict) -> None:
    if path.is_symlink():
        raise ValueError(f"Refusing to replace symlink: {path}")
    if item["kind"] == "absent":
        existed = path.exists()
        path.unlink(missing_ok=True)
        if existed:
            _fsync_directory(path.parent)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(base64.b64decode(item["data"]))
            stream.flush()
            os.fsync(stream.fileno())
        tmp.chmod(item.get("mode", 0o644))
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _safe_write(root: Path, path: Path, item: dict) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Write target escapes filesystem root: {path}") from error
    validated = _rooted(root, Path("/") / relative)
    if validated != path:
        raise ValueError(f"Write target changed during transaction: {path}")
    _write(path, item)


@contextmanager
def _boot_lock(root: Path):
    path = _rooted(root, LOCK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def _payload_files(source: Path) -> list[Path]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"Missing or unsafe boot payload directory: {source}")
    result = []
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"Boot payload may not contain symlinks: {item}")
        if item.is_file():
            result.append(item)
        elif not item.is_dir():
            raise ValueError(f"Boot payload contains a special file: {item}")
    if not result:
        raise ValueError(f"Empty boot payload directory: {source}")
    return result


def _palette(bundle_root: Path) -> dict[str, str]:
    path = bundle_root / "colors.toml"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Bundle colors.toml is missing or is a symlink")
    colors = tomllib.loads(path.read_text())
    return colors


def _limine_values(bundle_root: Path) -> dict[str, str]:
    colors = _palette(bundle_root)
    template_path = bundle_root / "components/boot/limine.conf"
    if template_path.is_symlink() or not template_path.is_file():
        raise ValueError("Missing or unsafe Limine appearance fragment")
    text = template_path.read_text()
    roles = set(re.findall(r"@([A-Za-z0-9_]+)@", text))
    for name in roles:
        value = colors.get(name)
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError(f"Missing or invalid Limine colour role {name!r} in colors.toml")
        text = text.replace("@" + name + "@", value[1:])
    unresolved = re.findall(r"@[A-Za-z0-9_]+@", text)
    if unresolved:
        raise ValueError("Unresolved Limine palette roles: " + ", ".join(sorted(set(unresolved))))
    values = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    if set(values) != set(LIMINE_KEYS):
        raise ValueError("Limine appearance fragment has unexpected or missing keys")
    if values["interface_branding"] != "ATLAS Bootloader":
        raise ValueError("Limine fragment must use ATLAS branding")
    return values


def _split_limine(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if re.match(r"^\s*/", line):
            return lines[:index], lines[index:]
    return lines, []


def _limine_original(text: str) -> list[str]:
    global_lines, _ = _split_limine(text)
    return [line for line in global_lines if _LIMINE_KEY_RE.match(line)]


def _limine_current_values(text: str) -> dict[str, list[str]]:
    result = {key: [] for key in LIMINE_KEYS}
    global_lines, _ = _split_limine(text)
    for line in global_lines:
        match = _LIMINE_KEY_RE.match(line)
        if match:
            key = match.group(1).casefold()
            result[key].append(line[match.end():].strip())
    return result


def _strip_limine_appearance(lines: list[str]) -> list[str]:
    return [
        line for line in lines
        if not _LIMINE_KEY_RE.match(line) and not _ATLAS_MARKER_RE.match(line.rstrip("\r\n"))
    ]


def _edit_limine(text: str, values: dict[str, str]) -> str:
    global_lines, entries = _split_limine(text)
    global_lines = _strip_limine_appearance(global_lines)
    if global_lines and not global_lines[-1].endswith(("\n", "\r")):
        global_lines[-1] += "\n"
    if global_lines and global_lines[-1].strip():
        global_lines.append("\n")
    global_lines.append("# BEGIN ATLAS APPEARANCE\n")
    global_lines.extend(f"{key}: {values[key]}\n" for key in LIMINE_KEYS)
    global_lines.append("# END ATLAS APPEARANCE\n")
    if entries and global_lines[-1].strip():
        global_lines.append("\n")
    return "".join(global_lines + entries)


def _restore_limine(text: str, original_lines: list[str]) -> str:
    global_lines, entries = _split_limine(text)
    global_lines = _strip_limine_appearance(global_lines)
    while global_lines and not global_lines[-1].strip():
        global_lines.pop()
    if original_lines:
        if global_lines:
            if not global_lines[-1].endswith(("\n", "\r")):
                global_lines[-1] += "\n"
            global_lines.append("\n")
        global_lines.extend(line if line.endswith(("\n", "\r")) else line + "\n" for line in original_lines)
    if entries and global_lines:
        if not global_lines[-1].endswith(("\n", "\r")):
            global_lines[-1] += "\n"
        global_lines.append("\n")
    return "".join(global_lines + entries)


def _ini_value(text: str, section: str, key: str) -> tuple[bool, str | None]:
    current = None
    in_section = False
    section_exists = False
    for line in text.splitlines():
        heading = re.match(r"^\s*\[([^]]+)\]\s*(?:[#;].*)?$", line)
        if heading:
            in_section = heading.group(1).casefold() == section.casefold()
            section_exists |= in_section
            continue
        match = re.match(r"^\s*([^#;][^=]*)=(.*)$", line)
        if in_section and match and match.group(1).strip().casefold() == key.casefold():
            current = match.group(2).strip()
            break
    return section_exists, current


def _set_ini_value(text: str, section: str, key: str, value: str | None,
                   remove_empty_created_section: bool = False) -> str:
    lines = text.splitlines(keepends=True)
    section_start = section_end = None
    key_indexes = []
    current_section = None
    for index, line in enumerate(lines):
        heading = re.match(r"^\s*\[([^]]+)\]", line)
        if heading:
            if current_section == section.casefold() and section_end is None:
                section_end = index
            current_section = heading.group(1).casefold()
            if current_section == section.casefold() and section_start is None:
                section_start = index
            continue
        match = re.match(r"^\s*([^#;][^=]*)=", line)
        if current_section == section.casefold() and match and match.group(1).strip().casefold() == key.casefold():
            key_indexes.append(index)
    if section_start is not None and section_end is None:
        section_end = len(lines)
    if key_indexes:
        first = key_indexes[0]
        if value is None:
            for index in reversed(key_indexes):
                del lines[index]
        else:
            ending = "\n" if lines[first].endswith("\n") else ""
            lines[first] = f"{key}={value}{ending}"
            for index in reversed(key_indexes[1:]):
                del lines[index]
        return "".join(lines)
    if value is None:
        if remove_empty_created_section and section_start is not None:
            body = lines[section_start + 1:section_end]
            if not any(line.strip() and not line.lstrip().startswith(("#", ";")) for line in body):
                del lines[section_start:section_end]
        return "".join(lines)
    if section_start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend((f"[{section}]\n", f"{key}={value}\n"))
    else:
        lines.insert(section_end, f"{key}={value}\n")
    return "".join(lines)


def _detect_esp(root: Path, requested: Path | None) -> tuple[Path, str]:
    if requested is not None:
        path = _rooted(root, Path(requested))
        logical = _logical(root, path)
        if not path.is_dir() or not (path / "limine.conf").is_file():
            raise ValueError(f"ESP {logical} must contain limine.conf")
        _rooted(root, path / "limine.conf")
        return path, logical
    found = []
    for logical in ESP_CANDIDATES:
        candidate = _rooted(root, logical)
        if (candidate / "limine.conf").is_file():
            found.append((candidate, str(logical)))
    if not found:
        raise ValueError("No ESP with limine.conf found at /boot, /efi, or /boot/efi; pass --esp")
    if len(found) != 1:
        raise ValueError("Multiple ESP candidates contain limine.conf; pass --esp explicitly: " +
                         ", ".join(logical for _, logical in found))
    return found[0]


def _copy_payload(source: Path, logical_dest: Path, root: Path, component: str,
                  desired: dict[str, tuple[dict, str]]) -> None:
    for item in _payload_files(source):
        logical = logical_dest / item.relative_to(source)
        target = _rooted(root, logical)
        desired[_logical(root, target)] = (
            _file_value(item.read_bytes(), stat.S_IMODE(item.stat().st_mode)), component
        )


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "components": [], "files": {}, "selectors": {}}
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Unsafe ATLAS boot state: {path}")
    data = json.loads(path.read_text())
    if data.get("version") != 1 or not isinstance(data.get("files"), dict):
        raise ValueError("Unsupported ATLAS boot state")
    data.setdefault("components", [])
    data.setdefault("selectors", {})
    return data


def _selector_conflicts(root: Path) -> list[str]:
    directory = _rooted(root, Path("/etc/sddm.conf.d"))
    conflicts = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.conf")):
            if path.name <= SDDM_SELECTOR.name or path.name == SDDM_SELECTOR.name:
                continue
            if path.is_symlink():
                raise ValueError(f"SDDM configuration may not be a symlink: {path}")
            if _ini_value(path.read_text(), "Theme", "Current")[1] is not None:
                conflicts.append(_logical(root, path))
    main = _rooted(root, Path("/etc/sddm.conf"))
    if main.is_file() and _ini_value(main.read_text(), "Theme", "Current")[1] is not None:
        conflicts.append("/etc/sddm.conf")
    return conflicts


def _enrollment_enabled(root: Path) -> bool:
    value = None
    logical_paths = []
    for directory in (Path("/usr/share/limine-entry-tool.d"), Path("/etc/limine-entry-tool.d")):
        target = _rooted(root, directory)
        if target.exists() and not target.is_dir():
            raise ValueError(f"Limine configuration path is not a directory: {directory}")
        if target.is_dir():
            logical_paths.extend(Path(_logical(root, path)) for path in sorted(target.glob("*.conf")))
        if directory == Path("/usr/share/limine-entry-tool.d"):
            logical_paths.append(Path("/etc/limine-entry-tool.conf"))
    logical_paths.append(Path("/etc/default/limine"))
    assignment = re.compile(
        r"^\s*ENABLE_ENROLL_LIMINE_CONFIG\s*=\s*"
        r"(?:\"(yes|no)?\"|(yes|no)?)\s*$", re.I
    )
    starts = re.compile(r"^\s*ENABLE_ENROLL_LIMINE_CONFIG\s*=", re.I)
    for logical in logical_paths:
        path = _rooted(root, logical)
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError(f"Limine configuration is not a regular file: {logical}")
        for line in path.read_text().splitlines():
            if not starts.match(line):
                continue
            match = assignment.match(line)
            if not match:
                raise ValueError(
                    f"Complex ENABLE_ENROLL_LIMINE_CONFIG expression in {logical}; use a literal yes or no"
                )
            value = next((item for item in match.groups() if item is not None), "")
            value = value.casefold()
    return value == "yes"


def _preflight_tree(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"ESP must be a regular directory: {path}")
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"ESP contains a symlink; refusing unsafe transaction: {item}")
        if not item.is_dir() and not item.is_file():
            raise ValueError(f"ESP contains a special file: {item}")


def _validate_real_esp(path: Path) -> None:
    if not os.path.ismount(path):
        raise ValueError(f"ESP is not a mounted filesystem: {path}")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_manifest(path: Path) -> dict[str, str]:
    return {
        str(item.relative_to(path)): _hash_file(item)
        for item in sorted(path.rglob("*")) if item.is_file()
    }


def _kernel_fingerprint(root: Path) -> dict[str, str]:
    modules = _rooted(root, Path("/usr/lib/modules"))
    if not modules.exists():
        return {}
    if not modules.is_dir():
        raise ValueError("/usr/lib/modules is not a directory")
    result = {}
    for directory in sorted(modules.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Unsafe kernel modules entry: {directory}")
        markers = [item for item in (directory / "modules.builtin", directory / "vmlinuz") if item.is_file()]
        result[directory.name] = ":".join(_hash_file(item) for item in markers)
    return result


def _transaction_root(root: Path) -> Path:
    return _rooted(root, TRANSACTIONS_PATH)


def _active_transaction(root: Path) -> Path | None:
    directory = _transaction_root(root)
    if not directory.exists():
        return None
    if not directory.is_dir():
        raise ValueError("ATLAS boot transactions path is not a directory")
    found = []
    for item in sorted(directory.iterdir()):
        if item.is_symlink() or not item.is_dir():
            raise ValueError(f"Unsafe ATLAS boot transaction entry: {item}")
        journal = item / "journal.json"
        if journal.is_file():
            found.append(item)
    if len(found) > 1:
        raise ValueError("Multiple ATLAS boot transactions require manual inspection")
    return found[0] if found else None


def _journal_write(root: Path, transaction: Path, journal: dict) -> None:
    _safe_write(root, transaction / "journal.json",
                _file_value(json.dumps(journal, indent=2) + "\n", 0o600))


def _required_backup_bytes(esp: Path | None, before: list[tuple[Path, dict]]) -> int:
    total = 0
    if esp is not None:
        total += sum(item.stat().st_size for item in esp.rglob("*") if item.is_file())
    total += sum(len(base64.b64decode(item["data"])) for _, item in before if item["kind"] == "file")
    return total


def _prepare_transaction(root: Path, esp: Path | None, changes: list[tuple[Path, dict]],
                         state_path: Path, new_state: dict) -> tuple[Path, dict]:
    transaction_root = _transaction_root(root)
    transaction_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    transaction_root.chmod(0o700)
    before = [(path, _snapshot(path)) for path, _ in changes]
    needed = _required_backup_bytes(esp, before)
    free = shutil.disk_usage(transaction_root).free
    reserve = max(64 * 1024 * 1024, needed // 10)
    if free < needed + reserve:
        raise OSError(f"Insufficient backup storage: need {needed + reserve} bytes, have {free}")
    transaction = Path(tempfile.mkdtemp(prefix="boot-", dir=transaction_root))
    transaction.chmod(0o700)
    try:
        backup = transaction / "esp"
        if esp is not None:
            shutil.copytree(esp, backup, copy_function=shutil.copy2)
            for item in sorted(backup.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if item.is_file():
                    with item.open("rb") as stream:
                        os.fsync(stream.fileno())
                elif item.is_dir():
                    _fsync_directory(item)
            _fsync_directory(backup)
        journal = {
            "version": 1,
            "status": "prepared",
            "esp": _logical(root, esp) if esp is not None else None,
            "esp_before": _tree_manifest(backup) if esp is not None else None,
            "kernel": _kernel_fingerprint(root) if esp is not None else None,
            "state_path": _logical(root, state_path),
            "state_before": _snapshot(state_path),
            "state_after": _file_value(json.dumps(new_state, indent=2) + "\n", 0o600)
                if new_state["components"] else {"kind": "absent"},
            "changes": [
                {"path": _logical(root, path), "before": old, "after": after}
                for (path, after), (_, old) in zip(changes, before)
            ],
        }
        _journal_write(root, transaction, journal)
        _fsync_directory(transaction)
        _fsync_directory(transaction_root)
        return transaction, journal
    except BaseException:
        shutil.rmtree(transaction, ignore_errors=True)
        _fsync_directory(transaction_root)
        raise


def _restore_tree(root: Path, esp: Path, backup: Path) -> None:
    # Preflight already ruled out symlinks. Restore the exact pre-transaction
    # file set so a failed rebuild cannot leave a mixed config/image generation.
    before_files = {p.relative_to(backup) for p in backup.rglob("*") if p.is_file()}
    for item in sorted(esp.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if item.is_file() and item.relative_to(esp) not in before_files:
            _rooted(root, Path(_logical(root, item)))
            item.unlink()
            _fsync_directory(item.parent)
        elif item.is_dir():
            try:
                item.rmdir()
            except OSError:
                pass
    for source in sorted(backup.rglob("*")):
        relative = source.relative_to(backup)
        target = esp / relative
        if source.is_dir():
            _rooted(root, Path(_logical(root, target)))
            target.mkdir(parents=True, exist_ok=True)
        else:
            _rooted(root, Path(_logical(root, target)))
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix="." + target.name + ".", dir=target.parent)
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                shutil.copy2(source, tmp)
                with tmp.open("rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(tmp, target)
                _fsync_directory(target.parent)
            finally:
                tmp.unlink(missing_ok=True)


def _command(path: str) -> None:
    subprocess.run([path], check=True)


def _text_change(path: Path, text: str) -> dict:
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    return _file_value(text, mode)


def _commit(root: Path, esp: Path | None, changes: list[tuple[Path, dict]],
            state_path: Path, new_state: dict, rebuild=None, reenroll=None) -> None:
    """Commit changes and leave a durable first-boot recovery checkpoint."""
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path.parent.chmod(0o700)
    transaction, journal = _prepare_transaction(root, esp, changes, state_path, new_state)
    try:
        for path, item in changes:
            _safe_write(root, path, item)
        if rebuild is not None:
            rebuild()
        if reenroll is not None:
            reenroll()
        _safe_write(root, state_path, journal["state_after"])
        journal["esp_after"] = _tree_manifest(esp) if esp is not None else None
        journal["status"] = "completed"
        _journal_write(root, transaction, journal)
    except BaseException:
        try:
            for item in reversed(journal["changes"]):
                _safe_write(root, _rooted(root, Path(item["path"])), item["before"])
            _safe_write(root, state_path, journal["state_before"])
            if esp is not None:
                _restore_tree(root, esp, transaction / "esp")
            shutil.rmtree(transaction)
        except BaseException as rollback_error:
            raise RuntimeError(
                f"Boot rollback failed; pre-transaction data retained at {transaction}"
            ) from rollback_error
        raise
    print(f"Recovery checkpoint retained at {_logical(root, transaction)}; confirm it after a successful reboot")


def _snapshot_bytes(item: dict) -> bytes:
    return base64.b64decode(item["data"]) if item["kind"] == "file" else b""


def _guard_matches(path: Path, logical: str, current: dict, expected: dict,
                   esp_logical: str | None) -> bool:
    if esp_logical and logical == str(Path(esp_logical) / "limine.conf"):
        if current["kind"] != "file" or expected["kind"] != "file":
            return current == expected
        return _limine_current_values(_snapshot_bytes(current).decode()) == \
            _limine_current_values(_snapshot_bytes(expected).decode())
    if logical == str(PLYMOUTH_CONFIG):
        if current["kind"] != "file" or expected["kind"] != "file":
            return current == expected
        return _ini_value(_snapshot_bytes(current).decode(), "Daemon", "Theme")[1] == \
            _ini_value(_snapshot_bytes(expected).decode(), "Daemon", "Theme")[1]
    return current == expected


def _load_journal(transaction: Path) -> dict:
    path = transaction / "journal.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or unsafe boot transaction journal: {path}")
    journal = json.loads(path.read_text())
    if journal.get("version") != 1 or journal.get("status") not in ("prepared", "completed", "recovering"):
        raise ValueError("Unsupported ATLAS boot transaction journal")
    if not isinstance(journal.get("changes"), list):
        raise ValueError("Invalid ATLAS boot transaction changes")
    return journal


def _recover(root: Path, dry_run: bool) -> int:
    transaction = _active_transaction(root)
    if transaction is None:
        print("No ATLAS boot recovery checkpoint.")
        return 0
    journal = _load_journal(transaction)
    if journal.get("kernel") is not None and _kernel_fingerprint(root) != journal["kernel"]:
        raise ValueError("Kernel set changed since the checkpoint; refusing to restore older boot images")
    esp = _rooted(root, Path(journal["esp"])) if journal.get("esp") else None
    if esp is not None:
        _preflight_tree(esp)
        backup = transaction / "esp"
        if _tree_manifest(backup) != journal["esp_before"]:
            raise ValueError("Recovery ESP backup does not match its journal")
        if journal["status"] == "completed" and _tree_manifest(esp) != journal.get("esp_after"):
            raise ValueError("ESP changed after the completed transaction; refusing an obsolete image restore")
    state_path = _rooted(root, Path(journal["state_path"]))
    current_state = _snapshot(state_path)
    if current_state not in (journal["state_before"], journal["state_after"]):
        raise ValueError("Boot state changed after the checkpoint; refusing recovery")
    for change in journal["changes"]:
        logical = change["path"]
        path = _rooted(root, Path(logical))
        current = _snapshot(path)
        if not any(_guard_matches(path, logical, current, expected, journal.get("esp"))
                   for expected in (change["before"], change["after"])):
            raise ValueError(f"Managed boot path changed after the checkpoint: {logical}")
    print(f"RECOVER pre-transaction boot state from {_logical(root, transaction)}")
    if dry_run:
        return 0
    journal["status"] = "recovering"
    _journal_write(root, transaction, journal)
    for change in reversed(journal["changes"]):
        _safe_write(root, _rooted(root, Path(change["path"])), change["before"])
    _safe_write(root, state_path, journal["state_before"])
    if esp is not None:
        _restore_tree(root, esp, transaction / "esp")
    shutil.rmtree(transaction)
    _fsync_directory(_transaction_root(root))
    print("ATLAS boot transaction recovered.")
    return 0


def _confirm(root: Path, dry_run: bool) -> int:
    transaction = _active_transaction(root)
    if transaction is None:
        print("No ATLAS boot recovery checkpoint.")
        return 0
    journal = _load_journal(transaction)
    if journal["status"] != "completed":
        raise ValueError("Incomplete boot transaction must be recovered, not confirmed")
    print(f"CONFIRM completed boot transaction and remove {_logical(root, transaction)}")
    if dry_run:
        return 0
    shutil.rmtree(transaction)
    _fsync_directory(_transaction_root(root))
    print("ATLAS boot checkpoint confirmed.")
    return 0


def _selected(args) -> set[str]:
    chosen = {name for name in COMPONENTS if bool(getattr(args, name, False))}
    return chosen or set(COMPONENTS)


def _operate(bundle_root: Path, args) -> int:
    """Install or restore explicitly selected boot components."""
    bundle_root = Path(bundle_root).resolve(strict=True)
    root = Path(getattr(args, "root", Path("/"))).resolve(strict=True)
    dry_run = bool(getattr(args, "dry_run", False))
    action = getattr(args, "action", "")
    if action not in ("boot", "boot-restore"):
        raise ValueError(f"Unsupported boot action: {action}")
    selected = _selected(args)
    real_root = root == Path("/")
    if real_root and not dry_run and os.geteuid() != 0:
        raise PermissionError("Boot installation requires root. Re-run the explicit command with sudo.")

    state_path = _rooted(root, STATE_PATH)
    state = _load_state(state_path)
    installing = action == "boot"
    active = selected if installing else selected & set(state["components"])
    if not active:
        print("No selected ATLAS boot components are installed.")
        return 0

    need_esp = bool(active & {"limine", "plymouth"})
    esp = esp_logical = None
    if need_esp:
        esp, esp_logical = _detect_esp(root, getattr(args, "esp", None))
        _preflight_tree(esp)
        if real_root:
            _validate_real_esp(esp)
        saved_esp = state.get("esp")
        if saved_esp and saved_esp != esp_logical:
            raise ValueError(f"Installed boot state belongs to ESP {saved_esp}, not {esp_logical}")

    values = _limine_values(bundle_root) if "limine" in active and installing else None
    desired: dict[str, tuple[dict, str]] = {}
    selector_updates: dict[str, tuple[Path, str]] = {}
    new_state = json.loads(json.dumps(state))
    if esp_logical:
        new_state["esp"] = esp_logical

    if installing:
        if "plymouth" in active:
            _copy_payload(bundle_root / "components/boot/plymouth", PLYMOUTH_DEST, root, "plymouth", desired)
            conf = _rooted(root, PLYMOUTH_CONFIG)
            if conf.exists() and not conf.is_file():
                raise ValueError("Plymouth selector must be a regular file")
            old_text = conf.read_text() if conf.exists() else ""
            section_existed, old_value = _ini_value(old_text, "Daemon", "Theme")
            saved = new_state["selectors"].get("plymouth")
            if saved and old_value != saved.get("installed"):
                raise ValueError("Preserving a later edit to the Plymouth Theme selector")
            if saved is None:
                new_state["selectors"]["plymouth"] = {
                    "value": old_value, "section_existed": section_existed,
                    "installed": "atlas",
                }
            else:
                saved["installed"] = "atlas"
            selector_updates["plymouth"] = (conf, _set_ini_value(old_text, "Daemon", "Theme", "atlas"))
        if "sddm" in active:
            _copy_payload(bundle_root / "components/boot/sddm", SDDM_DEST, root, "sddm", desired)
            selector = _rooted(root, SDDM_SELECTOR)
            desired[_logical(root, selector)] = (_file_value("[Theme]\nCurrent=atlas\n"), "sddm")
            for conflict in _selector_conflicts(root):
                print(f"WARNING: SDDM theme selector {conflict} may override {SDDM_SELECTOR}")
        if "limine" in active:
            config_path = esp / "limine.conf"
            old_text = config_path.read_text()
            saved = new_state["selectors"].get("limine")
            current_values = _limine_current_values(old_text)
            if saved and current_values != saved.get("installed"):
                raise ValueError("Preserving a later edit to ATLAS Limine appearance")
            installed_values = {key: [values[key]] for key in LIMINE_KEYS}
            if saved is None:
                new_state["selectors"]["limine"] = {
                    "lines": _limine_original(old_text), "installed": installed_values,
                }
            else:
                saved["installed"] = installed_values
            selector_updates["limine"] = (config_path, _edit_limine(old_text, values))
    else:
        if "plymouth" in active:
            conf = _rooted(root, PLYMOUTH_CONFIG)
            current = conf.read_text() if conf.exists() else ""
            saved = state["selectors"].get("plymouth")
            if saved is None:
                raise ValueError("Plymouth restoration metadata is missing")
            if _ini_value(current, "Daemon", "Theme")[1] != saved.get("installed"):
                raise ValueError("Preserving a later edit to the Plymouth Theme selector")
            selector_updates["plymouth"] = (
                conf,
                _set_ini_value(current, "Daemon", "Theme", saved["value"],
                               remove_empty_created_section=not saved["section_existed"]),
            )
        if "limine" in active:
            config_path = esp / "limine.conf"
            saved = state["selectors"].get("limine")
            if saved is None:
                raise ValueError("Limine restoration metadata is missing")
            if _limine_current_values(config_path.read_text()) != saved.get("installed"):
                raise ValueError("Preserving a later edit to ATLAS Limine appearance")
            selector_updates["limine"] = (config_path, _restore_limine(config_path.read_text(), saved["lines"]))

    # Resolve desired payload changes against the persistent original baseline.
    file_changes: list[tuple[Path, dict]] = []
    if installing:
        for logical, (item, component) in desired.items():
            path = _rooted(root, Path(logical))
            current = _snapshot(path)
            record = new_state["files"].get(logical)
            if record and current not in (record["installed"], item):
                raise ValueError(f"Preserving a later edit to managed boot file: {logical}")
            if record is None:
                new_state["files"][logical] = {"before": current, "installed": item, "component": component}
            else:
                record["installed"] = item
            if current != item:
                file_changes.append((path, item))
        new_state["components"] = sorted(set(new_state["components"]) | active)
    else:
        for logical, record in list(new_state["files"].items()):
            if record.get("component") not in active:
                continue
            path = _rooted(root, Path(logical))
            current = _snapshot(path)
            if current not in (record["installed"], record["before"]):
                raise ValueError(f"Preserving a later edit to managed boot file: {logical}")
            if current != record["before"]:
                file_changes.append((path, record["before"]))
            del new_state["files"][logical]
        new_state["components"] = sorted(set(new_state["components"]) - active)
        for component in active:
            new_state["selectors"].pop(component, None)

    changes = [(path, _text_change(path, text)) for path, text in selector_updates.values()
               if _snapshot(path) != _text_change(path, text)] + file_changes
    for path, item in changes:
        verb = "REMOVE" if item["kind"] == "absent" else "WRITE "
        print(f"{verb} {_logical(root, path)}")
    if "plymouth" in active:
        print("REBUILD current initramfs/UKI images with limine-mkinitcpio")
    if "limine" in active and _enrollment_enabled(root):
        print("REENROLL Limine configuration without changing verification policy")
    if dry_run:
        print(f"{len(changes)} boot file changes planned; no files or boot images changed")
        return 0

    if real_root and "plymouth" in active:
        command = Path("/usr/bin/limine-mkinitcpio")
        if not command.is_file() or not os.access(command, os.X_OK):
            raise ValueError("Plymouth integration requires executable /usr/bin/limine-mkinitcpio")
    enrollment = bool("limine" in active and _enrollment_enabled(root))
    if real_root and enrollment:
        command = Path("/usr/bin/limine-enroll-config")
        if not command.is_file() or not os.access(command, os.X_OK):
            raise ValueError("Enrolled Limine configuration requires /usr/bin/limine-enroll-config")

    # Staged roots are intentionally subprocess-free. They still exercise
    # every file transaction and are suitable for package/test validation.
    rebuild = (lambda: _command("/usr/bin/limine-mkinitcpio")) \
        if real_root and "plymouth" in active else None
    reenroll = (lambda: _command("/usr/bin/limine-enroll-config")) \
        if real_root and enrollment else None
    _commit(root, esp if need_esp else None, changes, state_path, new_state,
            rebuild=rebuild, reenroll=reenroll)
    if not real_root and "plymouth" in active:
        print("STAGED: skipped limine-mkinitcpio")
    if not real_root and enrollment:
        print("STAGED: skipped Limine re-enrollment")

    # Clean now-empty, bundle-owned asset directories after restore.
    if not installing:
        for logical in (PLYMOUTH_DEST, SDDM_DEST):
            directory = _rooted(root, logical)
            try:
                directory.rmdir()
            except OSError:
                pass
    print(f"{len(changes)} boot file changes applied")
    return 0


def run(bundle_root: Path, args) -> int:
    """Serialize planning and writes, including durable recovery actions."""
    bundle_root = Path(bundle_root).resolve(strict=True)
    root = Path(getattr(args, "root", Path("/"))).resolve(strict=True)
    action = getattr(args, "action", "")
    dry_run = bool(getattr(args, "dry_run", False))
    if action not in ("boot", "boot-restore", "boot-recover", "boot-confirm"):
        raise ValueError(f"Unsupported boot action: {action}")
    if root == Path("/") and not dry_run and os.geteuid() != 0:
        raise PermissionError("Boot operations require root. Re-run the explicit command with sudo.")

    def operation():
        if action == "boot-recover":
            return _recover(root, dry_run)
        if action == "boot-confirm":
            return _confirm(root, dry_run)
        transaction = _active_transaction(root)
        if transaction is not None:
            journal = _load_journal(transaction)
            raise ValueError(
                f"Boot transaction checkpoint is {journal['status']}; run boot-recover after a failed boot "
                "or boot-confirm after a successful reboot"
            )
        return _operate(bundle_root, args)

    if dry_run:
        return operation()
    with _boot_lock(root):
        return operation()
