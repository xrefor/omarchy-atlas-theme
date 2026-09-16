from __future__ import annotations
import asyncio
import codecs
import os
from pathlib import Path
import shutil
import signal
import tempfile
import sys
import zipfile
import yaml


def _xdg(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else fallback.expanduser().resolve()


BASE = _xdg('XDG_DATA_HOME', Path.home() / '.local/share') / 'atlas-nutcracker'
REPO = Path(os.environ.get('NUTCRACKER_HOME', BASE / 'source')).expanduser().resolve()
DATA = Path(os.environ.get('ATLAS_NUTCRACKER_DATA', BASE)).expanduser().resolve()
CONFIG = Path(os.environ.get(
    'ATLAS_NUTCRACKER_CONFIG',
    _xdg('XDG_CONFIG_HOME', Path.home() / '.config') / 'atlas/nutcracker.yaml',
)).expanduser().resolve()
TOOLS = Path(os.environ.get('ATLAS_NUTCRACKER_TOOLS', BASE / 'tools')).expanduser().resolve()


def environment():
    env = os.environ.copy()
    jre = TOOLS / 'jre'
    paths = [str(Path(sys.executable).parent), str(TOOLS / 'jadx/bin')]
    if jre.exists():
        env['JAVA_HOME'] = str(jre)
        paths.append(str(jre / 'bin'))
    env['PATH'] = os.pathsep.join(paths + [env.get('PATH', '')])
    env['PYTHONUNBUFFERED'] = '1'
    return env


def local_timezone():
    try:
        from tzlocal import get_localzone_name
        return get_localzone_name()
    except Exception:
        return os.environ.get('TZ', 'UTC')


def setup():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA.chmod(0o700)
    for name in ('reports', 'logs', 'downloads'):
        (DATA / name).mkdir(exist_ok=True, mode=0o700)
        (DATA / name).chmod(0o700)
    if CONFIG.exists():
        CONFIG.chmod(0o600)
        return
    config = yaml.safe_load((REPO / 'config.yaml.example').read_text())
    config['language'] = 'en'
    config['timezone'] = local_timezone()
    config['features'].update(sast_scan=True, osint_scan=False, report_json=True)
    config['sast']['engine'] = 'regex'
    config['leak_scan'].update(apkleaks=False, gitleaks=False)
    config['reports'].update(output_dir=str(DATA / 'reports'), save_json=True)
    config['downloader']['output_dir'] = str(DATA / 'downloads')
    config['store']['db_path'] = str(DATA / 'nutcracker.db')
    config['pipelines']['protected'].update(decompilation='jadx', runtime_methods=[])
    config['scheduler']['enabled'] = False
    config['post_hooks'] = []
    config['toolbox']['enabled'] = False
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.nutcracker-', dir=CONFIG.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            yaml.safe_dump(config, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, CONFIG)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)


def apk_path(value):
    path = Path(value.strip()).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.apk':
        raise ValueError('Choose an existing .apk file.')
    try:
        with zipfile.ZipFile(path) as apk:
            if 'AndroidManifest.xml' not in apk.namelist():
                raise ValueError('This APK has no AndroidManifest.xml.')
    except zipfile.BadZipFile as exc:
        raise ValueError('This file is not a valid APK archive.') from exc
    return path


def analysis_command(path):
    return [sys.executable, '-m', 'atlas_nutcracker', 'native', 'analyze',
            str(apk_path(str(path))), '--static-only', '--config', str(CONFIG)]


def tool_status():
    path = environment()['PATH']
    return [(name, purpose, shutil.which(name, path=path)) for name, purpose in (
        ('jadx', 'Java/Kotlin decompilation'), ('java', 'JADX runtime'),
        ('adb', 'Optional · Android devices'), ('frida', 'Optional · runtime analysis'),
        ('apktool', 'Optional · smali fallback'), ('semgrep', 'Optional · additional SAST'),
        ('gitleaks', 'Optional · additional secret rules'), ('apkeep', 'Optional · app downloads'))]


def reports():
    try:
        config = (yaml.safe_load(CONFIG.read_text()) or {}) if CONFIG.exists() else {}
    except yaml.YAMLError as exc:
        raise ValueError(f'Invalid YAML in {CONFIG}: {exc}') from exc
    if not isinstance(config, dict) or not isinstance(config.get('reports', {}), dict):
        raise ValueError(f'Expected a reports mapping in {CONFIG}')
    folder = Path(config.get('reports', {}).get('output_dir') or DATA / 'reports').expanduser()
    if not folder.is_absolute():
        folder = DATA / folder
    if not folder.exists():
        return []
    return sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.json', '.pdf')),
                  key=lambda p: p.stat().st_mtime, reverse=True)


class OutputCleaner:
    """Strip terminal controls, including escape sequences split across reads."""
    def __init__(self): self.state = 'text'

    def feed(self, text):
        out = []
        for char in text:
            if char in '\n\r':
                self.state = 'text'; out.append('\n'); continue
            if self.state == 'text':
                if char == '\x1b': self.state = 'escape'
                elif char == '\t' or ord(char) >= 32 and not 127 <= ord(char) <= 159: out.append(char)
            elif self.state == 'escape':
                self.state = 'csi' if char == '[' else 'osc' if char in ']P^_' else 'text'
            elif self.state == 'csi':
                if '@' <= char <= '~': self.state = 'text'
            elif self.state == 'osc':
                if char == '\x07': self.state = 'text'
                elif char == '\x1b': self.state = 'osc-end'
            elif self.state == 'osc-end': self.state = 'text' if char == '\\' else 'osc'
        return ''.join(out)


class ProcessRunner:
    """One child session, streamed output, and cancellation of its entire process group."""
    def __init__(self):
        self.process = None; self.cancelled = False; self.stopping = False

    async def run(self, command, on_output, cwd=None, logfile=None):
        env = environment(); env['NO_COLOR'] = '1'
        self.process = await asyncio.create_subprocess_exec(
            *command, cwd=DATA if cwd is None else cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        if self.cancelled: await self.stop()
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        cleaner = OutputCleaner(); log = None
        try:
            if logfile:
                fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                log = os.fdopen(fd, 'w')
            while chunk := await self.process.stdout.read(8192):
                text = cleaner.feed(decoder.decode(chunk))
                if log: log.write(text); log.flush()
                on_output(text)
            tail = cleaner.feed(decoder.decode(b'', final=True))
            if tail:
                on_output(tail)
                if log: log.write(tail)
            return await self.process.wait()
        finally:
            if self.process.returncode is None: await self.stop()
            if log: log.close()
            self.process = None

    async def stop(self):
        self.cancelled = True; proc = self.process
        if proc is None or proc.returncode is not None or self.stopping: return
        self.stopping = True
        try:
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: return
            await asyncio.sleep(.5)
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            await proc.wait()
        finally: self.stopping = False
