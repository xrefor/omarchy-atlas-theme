#!/usr/bin/env python3
"""Coordinate short-lived GHOSTLINE overlay terminals on one workspace."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import time


SCHEDULE = [
    (3, "gate", "TRUST GATE", 2.4, 0),
    (9, "rf_lock", "RF LOCK", 3.2, 2),
    (15, "pump", "PUMP TRAIN", 5.4, 1),
    (22, "burst", "FRAME BURST", 3.0, 3),
    (29, "key", "KEY ACCEPTED", 4.0, 1),
    (38, "key", "MIC VERIFIED", 3.6, 4),
    (44, "pump", "BOOSTER FLOW", 5.4, 0),
    (51, "shard", "PROVENANCE", 3.0, 2),
    (57, "selector", "SELECTOR HIT", 4.0, 2),
    (63, "inspection", "ILI TOOL PASS", 5.8, 1),
    (69, "pcode", "P-CODE TRACE", 4.2, 4),
    (76, "perimeter", "PERIMETER", 3.4, 3),
    (82, "gate", "ACCESS PACKAGE", 2.8, 0),
    (87, "route", "ROUTE MUTATION", 3.4, 0),
    (94, "inspection", "BORE SCAN", 5.8, 2),
    (100, "route", "CHANNEL OPEN", 3.2, 1),
    (104, "objective", "OBJECTIVE", 5.2, 4),
    (111, "route", "VOLATILE RETIRE", 2.8, 3),
]
SEQUENCE_LENGTH = 116

CARD_SIZES = {
    "rf_lock": (700, 390),
    "track": (700, 390),
    "perimeter": (700, 390),
    "burst": (920, 290),
    "relay": (920, 290),
    "key": (760, 300),
    "gate": (760, 300),
    "objective": (760, 300),
    "pcode": (940, 390),
    "route": (940, 390),
    "shard": (820, 350),
    "selector": (820, 350),
    "pump": (1080, 540),
    "inspection": (1160, 580),
}

EQUIPMENT_KINDS = {"pump", "inspection"}
MAIN_WINDOW_CLASSES = {
    "atlas-ghostline-core",
    "atlas-ghostline-wireless",
    "atlas-ghostline-fusion",
    "atlas-ghostline-graph",
    "atlas-ghostline-sre",
    "atlas-ghostline-access",
}

Rect = tuple[int, int, int, int]


def hypr_json(command: str) -> object:
    result = subprocess.run(["hyprctl", "-j", command], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def dispatch(expression: str) -> None:
    subprocess.run(["hyprctl", "dispatch", expression], check=True, stdout=subprocess.DEVNULL)


def logical_monitor_rect(monitor: dict) -> Rect:
    scale = float(monitor["scale"])
    physical_width = int(monitor["width"])
    physical_height = int(monitor["height"])
    if int(monitor.get("transform", 0)) % 2 == 1:
        physical_width, physical_height = physical_height, physical_width
    width = int(physical_width / scale)
    height = int(physical_height / scale)
    # Monitor origins are already in the compositor's logical coordinate space.
    origin_x = int(monitor["x"])
    origin_y = int(monitor["y"])
    left, top, right, bottom = monitor["reserved"]
    margin = max(42, min(72, round(min(width, height) * 0.045)))
    x = origin_x + int(left) + margin
    y = origin_y + int(top) + margin
    return x, y, width - int(left) - int(right) - margin * 2, height - int(top) - int(bottom) - margin * 2


def rect_overlap(first: Rect, second: Rect) -> int:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))


def card_size(kind: str, safe: Rect) -> tuple[int, int]:
    target_w, target_h = CARD_SIZES[kind]
    _, _, safe_w, safe_h = safe
    width_limit, height_limit = (0.60, 0.56) if kind in EQUIPMENT_KINDS else (0.44, 0.42)
    return min(target_w, int(safe_w * width_limit)), min(target_h, int(safe_h * height_limit))


def main_wall_present(clients: list[dict], workspace: int) -> bool:
    return any(
        client.get("class") in MAIN_WINDOW_CLASSES
        and client.get("workspace", {}).get("id") == workspace
        and client.get("mapped")
        for client in clients
    )


def focus_context(workspace: int) -> tuple[dict, dict]:
    monitors = list(hypr_json("monitors"))
    clients = [
        client
        for client in hypr_json("clients")
        if client.get("workspace", {}).get("id") == workspace
        and client.get("mapped")
        and not client.get("class", "").startswith("atlas-ghostline-overlay-")
    ]

    def focus_rank(client: dict) -> tuple[int, int, int]:
        history = int(client.get("focusHistoryID", -1))
        is_core = client.get("class") == "atlas-ghostline-core"
        width, height = client.get("size", [0, 0])
        return (history if history >= 0 else 1_000_000, 0 if is_core else 1, -(int(width) * int(height)))

    focus = min(clients, key=focus_rank) if clients else {}
    monitor_id = focus.get("monitor")
    monitor = next((item for item in monitors if item.get("id") == monitor_id), None)
    if monitor is None:
        monitor = next((item for item in monitors if item.get("focused")), monitors[0])
    if not focus:
        safe_x, safe_y, safe_w, safe_h = logical_monitor_rect(monitor)
        focus = {
            "at": [safe_x + safe_w // 8, safe_y + safe_h // 5],
            "size": [max(1, safe_w // 3), max(1, safe_h // 2)],
        }
    return monitor, focus


def layout_near_focus(monitor: dict, focus: dict, lane: int, kind: str, occupied: list[Rect]) -> Rect:
    safe_x, safe_y, safe_w, safe_h = logical_monitor_rect(monitor)
    safe = (safe_x, safe_y, safe_w, safe_h)
    card_w, card_h = card_size(kind, safe)
    focus_x, focus_y = (int(value) for value in focus.get("at", [safe_x, safe_y]))
    focus_w, focus_h = (int(value) for value in focus.get("size", [1, 1]))
    focus_rect = (focus_x, focus_y, focus_w, focus_h)
    gap = 22

    vertical = (focus_y, focus_y + (focus_h - card_h) // 2, focus_y + focus_h - card_h)
    horizontal = (focus_x, focus_x + (focus_w - card_w) // 2, focus_x + focus_w - card_w)
    by_side = {
        "right": [(focus_x + focus_w + gap, y) for y in vertical],
        "bottom": [(x, focus_y + focus_h + gap) for x in horizontal],
        "left": [(focus_x - card_w - gap, y) for y in vertical],
        "top": [(x, focus_y - card_h - gap) for x in horizontal],
    }
    side_orders = (
        ("right", "bottom", "left", "top"),
        ("bottom", "left", "top", "right"),
        ("left", "top", "right", "bottom"),
        ("top", "right", "bottom", "left"),
    )
    side_order = side_orders[lane % len(side_orders)]
    align_order = (lane % 3, (lane + 1) % 3, (lane + 2) % 3)
    candidates: list[tuple[int, Rect]] = []
    fallback: list[tuple[int, Rect]] = []
    max_x = safe_x + safe_w - card_w
    max_y = safe_y + safe_h - card_h

    for side_rank, side in enumerate(side_order):
        for align_rank, alignment in enumerate(align_order):
            ideal_x, ideal_y = by_side[side][alignment]
            clamped_x = max(safe_x, min(max_x, ideal_x))
            clamped_y = max(safe_y, min(max_y, ideal_y))
            rect = (clamped_x, clamped_y, card_w, card_h)
            popup_overlap = sum(rect_overlap(rect, other) for other in occupied)
            preference = side_rank * 100 + align_rank * 10
            displacement = abs(clamped_x - ideal_x) + abs(clamped_y - ideal_y)
            fallback_score = rect_overlap(rect, focus_rect) * 50 + popup_overlap * 100 + displacement * 20 + preference
            fallback.append((fallback_score, rect))
            if clamped_x == ideal_x and clamped_y == ideal_y:
                candidates.append((popup_overlap * 100 + preference, rect))

    return min(candidates or fallback, key=lambda item: item[0])[1]


def find_address(window_class: str, workspace: int, timeout: float = 4.0) -> str | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        clients = hypr_json("clients")
        for client in clients:
            if client.get("class") == window_class and client.get("workspace", {}).get("id") == workspace:
                return client.get("address")
        time.sleep(0.08)
    return None


class Director:
    def __init__(self, workspace: int, start: float, script_dir: Path) -> None:
        self.workspace = workspace
        self.start = start
        self.script_dir = script_dir
        self.running = True
        self.active: dict[str, tuple[str, float, Rect]] = {}
        self.fired: set[tuple[int, int]] = set()

    def stop(self, *_: object) -> None:
        self.running = False

    def close_active_cards(self) -> None:
        """Close only cards that still match their recorded compositor identity."""
        try:
            clients = list(hypr_json("clients"))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return
        by_address = {client.get("address"): client for client in clients}
        for window_class, (address, _, _) in list(self.active.items()):
            client = by_address.get(address)
            if (
                client
                and client.get("class") == window_class
                and client.get("workspace", {}).get("id") == self.workspace
            ):
                try:
                    dispatch(f'hl.dsp.window.close({{ window = "address:{address}" }})')
                except (OSError, subprocess.SubprocessError):
                    pass
            self.active.pop(window_class, None)

    def spawn_card(self, kind: str, label: str, duration: float, lane: int, cycle: int) -> None:
        if len(self.active) >= 2:
            return
        nonce = f"{cycle}-{int(time.time() * 1000) % 100000}"
        window_class = f"atlas-ghostline-overlay-{nonce}"
        renderer = self.script_dir / "ghostline_overlay.py"
        monitor, focus = focus_context(self.workspace)
        x, y, width, height = layout_near_focus(
            monitor, focus, lane, kind, [entry[2] for entry in self.active.values()]
        )
        font_size = "11.0" if kind in EQUIPMENT_KINDS else "10.0"
        sandbox = (
            "bwrap --unshare-net --die-with-parent --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp "
            "--clearenv --setenv HOME /tmp --setenv TERM xterm-256color --setenv LANG C.UTF-8 "
            if shutil.which("bwrap")
            else ""
        )
        command = (
            f"alacritty --class {window_class} --title 'ATLAS // {label}' "
            f"-o 'font.size={font_size}' -o 'window.opacity=0.985' -o 'window.padding.x=10' -o 'window.padding.y=8' "
            "-o 'window.decorations=\"None\"' "
            f"-e {sandbox}"
            f"/usr/bin/python3 -I -u {shlex.quote(str(renderer))} {shlex.quote(kind)} "
            f"--label {shlex.quote(label)} --duration {duration}"
        )
        rules = (
            f'{{ float = true, no_initial_focus = true, workspace = "{self.workspace} silent", '
            f'size = {{{width}, {height}}}, move = {{{x}, {y}}} }}'
        )
        dispatch(f"hl.dsp.exec_cmd({json.dumps(command)}, {rules})")
        address = find_address(window_class, self.workspace)
        if not address:
            return
        target = f"address:{address}"
        dispatch(f'hl.dsp.window.float({{ action = "enable", window = "{target}" }})')
        dispatch(f'hl.dsp.window.resize({{ x = {width}, y = {height}, relative = false, window = "{target}" }})')
        dispatch(f'hl.dsp.window.move({{ x = {x}, y = {y}, relative = false, window = "{target}" }})')
        self.active[window_class] = (address, time.monotonic() + duration + 1.5, (x, y, width, height))

    def reap(self) -> None:
        now = time.monotonic()
        expired = [name for name, (_, deadline, _) in self.active.items() if deadline <= now]
        for name in expired:
            self.active.pop(name)

    def run(self) -> None:
        try:
            while self.running:
                clients = list(hypr_json("clients"))
                # The director is detached from the launcher. Treat closing the
                # final main panel as an intentional stop instead of continuing
                # to schedule cards against fallback geometry forever.
                if not main_wall_present(clients, self.workspace):
                    break
                self.reap()
                elapsed = max(0.0, time.time() - self.start)
                cycle = int(elapsed // SEQUENCE_LENGTH)
                position = elapsed % SEQUENCE_LENGTH
                for at, kind, label, duration, lane in SCHEDULE:
                    key = (cycle, at)
                    if key not in self.fired and at <= position < at + 0.7:
                        self.fired.add(key)
                        self.spawn_card(kind, label, duration, lane, cycle)
                self.fired = {item for item in self.fired if item[0] >= cycle - 1}
                time.sleep(0.12)
        finally:
            self.close_active_cards()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=int, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        state = args.state_dir.lstat()
    except OSError as error:
        raise SystemExit(f"invalid GHOSTLINE runtime state directory: {error}") from None
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.getuid()
        or stat.S_IMODE(state.st_mode) & 0o077
    ):
        raise SystemExit("GHOSTLINE runtime state directory must be private and owned by the current user")
    pid_file = args.state_dir / f"director-{args.workspace}.pid"
    lock_file = args.state_dir / f"director-{args.workspace}.lock"
    with lock_file.open("a+", encoding="ascii") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another ATLAS GHOSTLINE director already owns this workspace") from None
        pid_file.write_text(f"{os.getpid()}\n", encoding="ascii")
        director = Director(args.workspace, args.start, Path(__file__).resolve().parent)
        signal.signal(signal.SIGTERM, director.stop)
        signal.signal(signal.SIGINT, director.stop)
        try:
            director.run()
        finally:
            try:
                if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                    pid_file.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
