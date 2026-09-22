"""Palette-aware ATLAS project dashboard."""
import curses
from datetime import datetime
import re
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
    return clean(snapshot.get('branch') or 'UNBORN')


def overview(snapshot, width):
    name = clean(snapshot.get('repo_name') or 'PROJECT')
    state = _branch(snapshot) if snapshot.get('is_git') else 'NOT A GIT REPOSITORY'
    rows = [(title('projects', width), 'accent'),
            (_pair(name, state, width), 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    _section(rows, 'Project', width)
    rows.append((_pair('Current path', snapshot.get('path') or 'UNAVAILABLE', width), 'foreground'))
    if not snapshot.get('is_git'):
        rows.append(('NO GIT REPOSITORY', 'yellow'))
        rows.append(('This directory is still a valid project location.', 'secondary'))
        rows.append(('Git details appear when a repository is present.', 'foreground'))
        for error in snapshot.get('errors', [])[:4]:
            rows.append((clip(clean(error), width), 'yellow'))
        return rows
    rows.append((_pair('Repository root', snapshot.get('repo_root') or 'UNAVAILABLE', width),
                 'foreground'))
    rows.append((_pair('Branch', _branch(snapshot), width), 'bright_foreground'))
    upstream = snapshot.get('upstream')
    if upstream:
        rows.append((_pair('Tracking', upstream, width), 'foreground'))
        rows.append((_pair('Local divergence',
                           f"↑ {snapshot.get('ahead', 0)}  ↓ {snapshot.get('behind', 0)}",
                           width), 'accent' if snapshot.get('ahead') else 'secondary'))
    else:
        rows.append((_pair('Tracking', 'LOCAL ONLY / NONE', width), 'secondary'))

    counts = snapshot.get('counts') if isinstance(snapshot.get('counts'), dict) else {}
    _section(rows, 'Working tree', width)
    rows.append((_pair('Staged', counts.get('staged', 0), width),
                 'green' if counts.get('staged') else 'secondary'))
    rows.append((_pair('Unstaged', counts.get('unstaged', 0), width),
                 'yellow' if counts.get('unstaged') else 'secondary'))
    rows.append((_pair('Untracked', counts.get('untracked', 0), width),
                 'accent' if counts.get('untracked') else 'secondary'))

    _section(rows, 'Changed files', width)
    changes = snapshot.get('changes') if isinstance(snapshot.get('changes'), list) else []
    if not changes:
        rows.append(('Working tree clean.', 'green'))
    for item in changes:
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
    rows = [(title('projects', width), 'accent'),
            (_pair('HISTORY', name, width), 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    if not snapshot.get('is_git'):
        rows.append(('No local Git history for this directory.', 'yellow'))
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
    if not commits:
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
    rows.append(('Local refs only · no fetch or network access.', 'muted'))
    return rows


def dashboard(snapshot, width, page=1):
    width = max(0, min(int(width), 4096))
    renderer = history if page == 2 else overview
    palette = read_palette()
    return [(clip(text, width), role if role in palette else 'foreground')
            for text, role in renderer(snapshot if isinstance(snapshot, dict) else {}, width)]


def _screen(screen, collector, palette_path):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.timeout(500)
    offset, page, next_update = 0, 1, 0
    snapshot, previous_palette, style = {}, None, {}
    while True:
        tick = time.monotonic()
        if tick >= next_update:
            try:
                snapshot = collector.collect()
            except (OSError, ValueError) as error:
                snapshot = dict(snapshot, errors=[f'Collector unavailable: {error}'])
            next_update = tick + 2
        palette = read_palette(palette_path)
        if palette != previous_palette:
            style = styles(palette)
            screen.bkgd(' ', style['foreground'])
            previous_palette = palette
        height, columns = screen.getmaxyx()
        _, width = layout(columns)
        rows = dashboard(snapshot, width, page)
        fixed = min(4, max(0, height - 1))
        available = max(0, height - fixed - 1)
        body = rows[4:]
        offset = min(offset, max(0, len(body) - available))
        footer = ('1 overview · 2 history · ↑↓/jk scroll · r refresh · q close'
                  if width >= 55 else
                  '1 overview · 2 history · ↑↓ · r refresh · q close' if width >= 43 else
                  '1 overview · 2 history · ↑↓ · r · q' if width >= 35 else
                  '1 overview · 2 history · q' if width >= 24 else '1/2 pages · q')
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


def run(collector, palette_path=None):
    curses.wrapper(_screen, collector, palette_path)
