"""Palette-aware ATLAS project dashboard."""
import curses
from datetime import datetime
import re
import queue
import signal
import threading
import time
import unicodedata

from atlas_panel import (cell_width, clip, draw_panel_frame, layout, read_palette,
                         styles, title)


_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)|'
                   r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')
_MAX_TEXT = 4096


def clean(value):
    value = _ANSI.sub('', str('' if value is None else value)[:_MAX_TEXT])
    return ' '.join(''.join(character for character in value
                            if not unicodedata.category(character).startswith('C')
                            or character in '\n\r\t').split())


def _pair(label, value, width):
    label, value = clean(label), clean(value)
    room = max(1, width - cell_width(label) - 1)
    value = clip(value, room)
    gap = max(1, width - cell_width(label) - cell_width(value))
    return clip(label + ' ' * gap + value, width)


def _section(rows, name, width):
    if len(rows) > 4 and rows[-1][0]:
        rows.append(('', 'foreground'))
    rows.append((clip(clean(name).upper(), width), 'secondary'))


def _branch(snapshot):
    if snapshot.get('detached'):
        head = clean(snapshot.get('head') or '')
        return 'DETACHED ' + (head[:12] if head else 'HEAD')
    return clean(snapshot.get('branch') or 'UNKNOWN')


def _when(value):
    try:
        return datetime.fromtimestamp(float(value)).strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError, OverflowError, OSError):
        return 'NEVER'


def overview(snapshot, width):
    name = clean(snapshot.get('repo_name') or 'PROJECT')
    discovery = snapshot.get('discovery_state', 'unavailable')
    state = _branch(snapshot) if snapshot.get('is_git') else discovery.upper()
    rows = [(title('git status', width), 'accent'),
            (_pair(name, state, width), 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    rows.append((_pair('Path', snapshot.get('path') or 'UNAVAILABLE', width), 'foreground'))
    if not snapshot.get('is_git'):
        rows.append(('NO GIT REPOSITORY' if discovery == 'not_repo' else
                     'Repository data unavailable.', 'yellow'))
        rows.extend((clip(clean(error), width), 'yellow') for error in snapshot.get('errors', [])[:4])
        return rows
    _section(rows, 'Checkout handoff', width)
    rows.append((_pair('Branch', _branch(snapshot), width), 'bright_foreground'))
    status_ok = snapshot.get('status_available', False)
    counts = snapshot.get('counts') if isinstance(snapshot.get('counts'), dict) else {}
    total = snapshot.get('changes_total') if status_ok else None
    rows.append((_pair('Uncommitted files', total if total is not None else 'UNKNOWN', width),
                 'yellow' if total else 'secondary'))
    if status_ok:
        rows.append((_pair('Conflicts', counts.get('conflicts', 0), width),
                     'yellow' if counts.get('conflicts') else 'secondary'))
        rows.append((_pair('Staged / unstaged / new',
                           f"{counts.get('staged', 0)} / {counts.get('unstaged', 0)} / {counts.get('untracked', 0)}",
                           width), 'secondary'))
    upstream = snapshot.get('upstream')
    tracking = upstream or ('UNKNOWN' if not status_ok else
                            'DETACHED HEAD' if snapshot.get('detached') else 'NO UPSTREAM')
    rows.append((_pair('Tracking', tracking, width), 'foreground'))
    remote = snapshot.get('remote_check') or {}
    _section(rows, 'Remote comparison', width)
    rows.append(('Counts use cached refs · f checks remote', 'muted'))
    divergence_ok = snapshot.get('divergence_available', False)
    for label, key in (('Ahead of upstream', 'ahead'), ('Upstream changes', 'behind')):
        count = snapshot.get(key) if divergence_ok else None
        rows.append((_pair(label, count if count is not None else 'UNKNOWN', width),
                     'yellow' if count else 'secondary'))
    remote_state = remote.get('state', 'never')
    labels = {'never': 'NOT CHECKED', 'checking': 'CHECKING…', 'ok': 'SUCCEEDED',
              'failed': 'FAILED', 'unavailable': 'UNAVAILABLE'}
    rows.append((_pair('Remote check', labels.get(remote_state, 'UNKNOWN'), width),
                 'yellow' if remote_state in ('failed', 'unavailable') else 'accent'))
    rows.append((_pair('Last success', _when(remote.get('checked_at')), width), 'secondary'))
    if remote_state == 'failed':
        rows.append((_pair('Last attempt', _when(remote.get('attempted_at')), width), 'secondary'))
    if remote.get('error'):
        rows.append((clip(clean(remote['error']), width), 'yellow'))
    if not status_ok:
        rows.append(('Working tree status unavailable.', 'yellow'))
    elif counts.get('conflicts'):
        rows.append(('Resolve conflicts before handoff.', 'yellow'))
    elif total:
        rows.append(('Uncommitted files remain on this machine.', 'yellow'))
    elif snapshot.get('detached'):
        rows.append(('Detached HEAD: choose a branch for handoff.', 'yellow'))
    elif not upstream:
        rows.append(('Set an upstream to compare machines.', 'yellow'))
    elif divergence_ok and snapshot.get('ahead') and snapshot.get('behind'):
        rows.append(('Branches diverged: review both histories.', 'yellow'))
    elif divergence_ok and snapshot.get('ahead'):
        rows.append(('Local commits absent from upstream.', 'yellow'))
    elif divergence_ok and snapshot.get('behind'):
        rows.append(('Upstream has commits absent here.', 'yellow'))
    elif divergence_ok and snapshot.get('ahead') == 0 and snapshot.get('behind') == 0:
        rows.append(('Clean and aligned with cached upstream.', 'green'))
    rows.append(('Other machines’ uncommitted work is unknown.', 'muted'))
    _section(rows, 'Changed files', width)
    changes = snapshot.get('changes') if isinstance(snapshot.get('changes'), list) else []
    if status_ok and total == 0:
        rows.append(('Working tree clean.', 'green'))
    elif not status_ok:
        rows.append(('Changed files unavailable.', 'yellow'))
    for item in changes if status_ok else []:
        if not isinstance(item, dict):
            continue
        status = clean(item.get('status') or '??')
        role = 'accent' if item.get('untracked') else 'yellow' if item.get('unstaged') else 'green'
        rows.append((clip(f'{status:2}  {clean(item.get("path") or "unknown")}', width), role))
        if item.get('original_path'):
            rows.append((clip('    from ' + clean(item['original_path']), width), 'secondary'))
    omitted = snapshot.get('changes_omitted')
    if isinstance(omitted, int) and omitted:
        rows.append((f'{omitted} more changed files omitted', 'secondary'))
    errors = snapshot.get('errors') if isinstance(snapshot.get('errors'), list) else []
    if errors:
        _section(rows, 'Unavailable', width)
        rows.extend((clip(clean(error), width), 'yellow') for error in errors[:6])
    return rows


def history(snapshot, width):
    name = clean(snapshot.get('repo_name') or 'PROJECT')
    rows = [(title('git status', width), 'accent'),
            (_pair('HISTORY', name, width), 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    if not snapshot.get('is_git'):
        rows.append(('No Git repository.' if snapshot.get('discovery_state') == 'not_repo'
                     else 'Repository data unavailable.', 'yellow'))
        rows.append((clip(clean(snapshot.get('path') or ''), width), 'secondary'))
        return rows
    _section(rows, 'Worktrees', width)
    worktrees = snapshot.get('worktrees') if isinstance(snapshot.get('worktrees'), list) else []
    if not worktrees:
        rows.append(('Worktree data unavailable.', 'yellow'))
    root = snapshot.get('repo_root')
    for item in worktrees:
        if not isinstance(item, dict):
            continue
        label = item.get('branch') or ('DETACHED' if item.get('detached') else 'WORKTREE')
        marker = '●' if item.get('path') == root else '○'
        rows.append((_pair(f'{marker} {label}', item.get('path') or 'UNAVAILABLE', width),
                     'bright_foreground' if marker == '●' else 'foreground'))
        if item.get('locked') or item.get('prunable'):
            flags = ' · '.join(key.upper() for key in ('locked', 'prunable') if item.get(key))
            rows.append((clip('  ' + flags, width), 'yellow'))

    _section(rows, 'Recent local commits', width)
    commits = snapshot.get('commits') if isinstance(snapshot.get('commits'), list) else []
    if not snapshot.get('history_available', False):
        rows.append(('Commit history unavailable.', 'yellow'))
        commits = []
    elif not commits:
        rows.append(('No commits yet.', 'secondary'))
    for item in commits:
        if not isinstance(item, dict):
            continue
        try:
            when = datetime.fromtimestamp(float(item.get('timestamp'))).strftime('%Y-%m-%d')
        except (TypeError, ValueError, OverflowError, OSError):
            when = 'UNKNOWN'
        rows.append((_pair(item.get('short_hash') or '—', when, width), 'accent'))
        rows.append((clip('  ' + clean(item.get('subject') or '(no subject)'), width), 'foreground'))
    rows.append(('', 'foreground'))
    rows.append(('Local history · f checks the tracked remote.', 'muted'))
    return rows


def dashboard(snapshot, width, page=1):
    width = max(0, min(int(width), 4096))
    renderer = history if page == 2 else overview
    palette = read_palette()
    return [(clip(text, width), role if role in palette else 'foreground')
            for text, role in renderer(snapshot if isinstance(snapshot, dict) else {}, width)]


class _Worker:
    """One daemon worker; repeated remote requests never build a fetch queue."""

    def __init__(self, collector):
        self.collector = collector
        self.results = queue.Queue()
        self.lock = threading.Lock()
        self.active = None
        self.pending_remote = False
        self.closed = False

    @property
    def checking(self):
        with self.lock:
            return self.active == 'remote' or self.pending_remote

    def request(self, kind='local'):
        with self.lock:
            if self.closed:
                return
            if self.active:
                if kind == 'remote' and self.active == 'local':
                    self.pending_remote = True
                return
            self.active = kind
            threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        while True:
            try:
                result = (self.collector.check_remote() if self.active == 'remote'
                          else self.collector.collect())
            except Exception as error:
                result = {'path': getattr(self.collector, 'path', ''),
                          'discovery_state': 'unavailable', 'is_git': False,
                          'errors': [f'Collector unavailable: {clean(error)}']}
            with self.lock:
                if self.closed:
                    self.active = None
                    return
                self.results.put(result)
                if self.pending_remote:
                    self.pending_remote = False
                    self.active = 'remote'
                else:
                    self.active = None
                    return

    def poll(self):
        result = None
        while True:
            try:
                result = self.results.get_nowait()
            except queue.Empty:
                return result

    def close(self):
        with self.lock:
            self.closed = True
            self.pending_remote = False
        cancel = getattr(self.collector, 'cancel', None)
        if cancel:
            cancel()


def _screen(screen, collector, palette_path):
    worker = _Worker(collector)
    try:
        _screen_loop(screen, worker, palette_path)
    finally:
        worker.close()


def _screen_loop(screen, worker, palette_path):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.timeout(100)
    offset, page, next_update = 0, 1, 0
    snapshot, previous_palette, style = {}, None, {}
    while True:
        tick = time.monotonic()
        if tick >= next_update:
            worker.request()
            next_update = tick + 2
        result = worker.poll()
        if result is not None:
            snapshot = result
        display = snapshot
        if worker.checking:
            display = dict(snapshot, remote_check=dict(snapshot.get('remote_check') or {},
                                                      state='checking'))
        palette = read_palette(palette_path)
        if palette != previous_palette:
            style = styles(palette)
            screen.bkgd(' ', style['foreground'])
            previous_palette = palette
        height, columns = screen.getmaxyx()
        _, width = layout(columns)
        rows = dashboard(display, width, page)
        fixed = min(4, max(0, height - 1))
        available = max(0, height - fixed - 1)
        body = rows[4:]
        offset = min(offset, max(0, len(body) - available))
        footer = ('1/2 pages · ↑↓ scroll · r local · f check remote · q'
                  if width >= 55 else
                  '1/2 · ↑↓ · r local · f check remote · q' if width >= 43 else
                  '1/2 · r local · f remote · q' if width >= 30 else '1/2 · f remote · q')
        if len(body) > available and width >= 48:
            footer += f'  {offset + 1}/{max(1, len(body) - available + 1)}'
        offset, available, body_length, width = draw_panel_frame(
            screen, rows, style, offset, footer)
        screen.refresh()
        key = screen.getch()
        if key in (ord('q'), ord('Q'), 27):
            return
        if key in (ord('1'), ord('2')):
            page, offset = key - ord('0'), 0
        elif key in (curses.KEY_DOWN, ord('j')):
            offset += 1
        elif key in (curses.KEY_UP, ord('k')):
            offset = max(0, offset - 1)
        elif key == curses.KEY_NPAGE:
            offset += max(1, available)
        elif key == curses.KEY_PPAGE:
            offset = max(0, offset - max(1, available))
        elif key == curses.KEY_HOME:
            offset = 0
        elif key == curses.KEY_END:
            offset = max(0, len(body) - available)
        elif key in (ord('r'), ord('R')):
            next_update = 0
        elif key in (ord('f'), ord('F')):
            worker.request('remote')


def run(collector, palette_path=None):
    # tmux kill-pane sends SIGHUP. Unwind the screen so its worker cancels Git,
    # whose separate process group otherwise survives terminal teardown.
    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    previous = {}
    try:
        for signum in (signal.SIGHUP, signal.SIGTERM):
            previous[signum] = signal.signal(signum, terminate)
        curses.wrapper(_screen, collector, palette_path)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
