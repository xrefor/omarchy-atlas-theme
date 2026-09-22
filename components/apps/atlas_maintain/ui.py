"""Palette-aware curses UI for local maintenance status."""
import curses
import re
import subprocess
import time
import unicodedata

from atlas_panel import cell_width, clip, draw_panel_frame, layout, read_palette, styles, title


_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)|'
                   r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')


def clean(value):
    value = _ANSI.sub('', str('' if value is None else value)[:4096])
    return ' '.join(''.join(character for character in value
                            if not unicodedata.category(character).startswith('C')
                            or character in '\n\r\t').split())


def _pair(label, value, width):
    label, value = clean(label), clean(value)
    value = clip(value, max(1, width - cell_width(label) - 1))
    return clip(label + ' ' * max(1, width - cell_width(label) - cell_width(value)) + value,
                width)


def _section(rows, label, width):
    if len(rows) > 4 and rows[-1][0]:
        rows.append(('', 'foreground'))
    rows.append((clip(clean(label).upper(), width), 'secondary'))


def _scope(value):
    return value if isinstance(value, dict) else {'status': 'unavailable'}


def _items(value, key):
    value = _scope(value).get(key)
    return value if isinstance(value, list) else []


def _health(snapshot):
    failed = snapshot.get('failed') if isinstance(snapshot.get('failed'), dict) else {}
    scopes = [_scope(failed.get(name)) for name in ('system', 'user')]
    failures = sum(len(_items(scope, 'units')) for scope in scopes)
    upgrades = snapshot.get('upgrades') if isinstance(snapshot.get('upgrades'), dict) else {}
    partial = any(scope.get('status') != 'ok' for scope in scopes)
    partial = partial or upgrades.get('status') != 'ok' or bool(snapshot.get('collection_error'))
    attention = failures or (isinstance(upgrades.get('count'), int) and upgrades['count'] > 0)
    attention = attention or snapshot.get('kernel_current') is False
    if failures:
        return f'{failures} FAILED UNIT' + ('S' if failures != 1 else ''), 'red'
    if attention:
        return 'ATTENTION', 'yellow'
    if partial:
        return 'PARTIAL DATA', 'yellow'
    return 'HEALTHY', 'green'


def _header(snapshot, page, width):
    status, role = _health(snapshot)
    names = {1: 'HEALTH', 2: 'TIMERS', 3: 'ISSUES'}
    return [(title('maintain', width), 'accent'),
            (_pair(names.get(page, 'HEALTH'), status, width), role),
            ('─' * width, 'muted'), ('', 'foreground')]


def _collection_error(rows, snapshot, width):
    error = snapshot.get('collection_error')
    if error:
        _section(rows, 'Collection error', width)
        rows.append((clip(clean(error), width), 'red'))


def health(snapshot, width):
    rows = _header(snapshot, 1, width)
    _collection_error(rows, snapshot, width)
    _section(rows, 'Kernel', width)
    rows.append((_pair('Running', snapshot.get('running_kernel') or 'UNAVAILABLE', width),
                 'bright_foreground'))
    installed = snapshot.get('installed_kernel') or 'UNAVAILABLE'
    rows.append((_pair('Latest installed', installed, width), 'foreground'))
    current = snapshot.get('kernel_current')
    if current is False:
        rows.append(('Reboot needed to use the latest installed kernel.', 'yellow'))
    elif current is True:
        rows.append(('Running kernel matches latest installed.', 'green'))
    else:
        rows.append(('Installed kernel comparison unavailable.', 'secondary'))

    _section(rows, 'Failed units', width)
    failed = snapshot.get('failed') if isinstance(snapshot.get('failed'), dict) else {}
    for label, key in (('System', 'system'), ('User', 'user')):
        scope = _scope(failed.get(key))
        units = _items(scope, 'units')
        value = str(len(units)) if scope.get('status') == 'ok' else clean(scope.get('status')).upper()
        rows.append((_pair(label, value, width),
                     'red' if units else 'green' if scope.get('status') == 'ok' else 'yellow'))

    _section(rows, 'Package status', width)
    upgrades = snapshot.get('upgrades') if isinstance(snapshot.get('upgrades'), dict) else {}
    if upgrades.get('status') == 'ok':
        count = upgrades.get('count') if isinstance(upgrades.get('count'), int) else 0
        rows.append((_pair('Pending upgrades', count, width), 'yellow' if count else 'green'))
        for item in _items(upgrades, 'items')[:5]:
            if isinstance(item, dict):
                rows.append((_pair('  ' + clean(item.get('package') or 'package'),
                                   clean(item.get('available') or '—'), width), 'foreground'))
    else:
        rows.append((_pair('Pending upgrades', clean(upgrades.get('status') or 'unavailable').upper(), width),
                     'yellow'))
    rows.append((clip(clean(upgrades.get('note') or
                            'Local sync database only · no network refresh'), width), 'secondary'))

    _section(rows, 'Last package transaction', width)
    transaction = snapshot.get('transaction')
    if not isinstance(transaction, dict):
        rows.append(('No transaction found in the bounded pacman log tail.', 'secondary'))
    else:
        rows.append((_pair('Started', transaction.get('timestamp') or 'UNKNOWN', width), 'foreground'))
        rows.append((_pair('Status', clean(transaction.get('status') or 'UNKNOWN').upper(), width),
                     'green' if transaction.get('status') == 'completed' else 'yellow'))
        rows.append((_pair('Package changes', transaction.get('count', 0), width), 'foreground'))
        for item in _items(transaction, 'changes')[:5]:
            if isinstance(item, dict):
                rows.append((clip('  ' + clean(item.get('action')).upper() + ' ' +
                                       clean(item.get('package')), width), 'secondary'))
    rows.append(('', 'foreground'))
    rows.append(('Read-only view · no refresh, upgrade, sudo, or unit action.', 'muted'))
    return rows


def timers(snapshot, width):
    rows = _header(snapshot, 2, width)
    _collection_error(rows, snapshot, width)
    values = snapshot.get('timers') if isinstance(snapshot.get('timers'), dict) else {}
    for label, key in (('System timers', 'system'), ('User timers', 'user')):
        _section(rows, label, width)
        scope = _scope(values.get(key))
        entries = _items(scope, 'items')
        if scope.get('status') != 'ok':
            rows.append((f"Unavailable · {clean(scope.get('status')).upper()}", 'yellow'))
            continue
        if not entries:
            rows.append(('No timers reported.', 'secondary'))
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            rows.append((_pair(item.get('unit') or 'timer', item.get('activates') or '—', width),
                         'bright_foreground'))
            if item.get('schedule'):
                rows.append((clip('  ' + clean(item['schedule']), width), 'secondary'))
    return rows


def issues(snapshot, width):
    rows = _header(snapshot, 3, width)
    _collection_error(rows, snapshot, width)
    failed = snapshot.get('failed') if isinstance(snapshot.get('failed'), dict) else {}
    found = False
    for label, key in (('Failed system units', 'system'), ('Failed user units', 'user')):
        _section(rows, label, width)
        scope = _scope(failed.get(key))
        units = _items(scope, 'units')
        if scope.get('status') != 'ok':
            rows.append((f"Unavailable · {clean(scope.get('status')).upper()}", 'yellow'))
        elif not units:
            rows.append(('None.', 'green'))
        else:
            found = True
            rows.extend((clip('! ' + clean(unit), width), 'red') for unit in units)
    _section(rows, 'Interpretation', width)
    if found:
        rows.append(('Inspect failures with journalctl or systemctl status.', 'secondary'))
    else:
        rows.append(('No locally reported failed units.', 'green'))
    rows.append(('This panel never restarts, enables, or disables units.', 'muted'))
    return rows


def dashboard(snapshot, width, page=1):
    width = max(0, min(int(width), 4096))
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    renderer = {1: health, 2: timers, 3: issues}.get(page, health)
    palette = read_palette()
    return [(clip(text, width), role if role in palette else 'foreground')
            for text, role in renderer(snapshot, width)]


def _footer(width, offset, body_length, available):
    if width >= 64:
        text = '1 health · 2 timers · 3 issues · ↑↓/jk · r refresh · q close'
    elif width >= 43:
        text = '1 health · 2 timers · 3 issues · ↑↓ · r · q'
    elif width >= 34:
        text = '1 health · 2 timers · 3 issues · q'
    elif width >= 30:
        text = '1 health · 2 timers · 3 issues'
    else:
        text = '1 · 2 · 3 · q'
    if body_length > available and width >= 48:
        text += f'  {offset + 1}/{max(1, body_length - available + 1)}'
    return text


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
        now = time.monotonic()
        if now >= next_update:
            try:
                snapshot = collector.collect()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                snapshot = dict(snapshot, collection_error=f'Collection unavailable: {error}')
            next_update = now + 30
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
        body_length = max(0, len(rows) - 4)
        offset = min(offset, max(0, body_length - available))
        footer = _footer(width, offset, body_length, available)
        offset, available, body_length, width = draw_panel_frame(
            screen, rows, style, offset, footer)
        screen.refresh()
        key = screen.getch()
        if key in (ord('q'), ord('Q'), 27):
            return
        if key in (ord('1'), ord('2'), ord('3')):
            page, offset = key - ord('0'), 0
        elif key in (curses.KEY_RIGHT, ord('l')):
            page, offset = page % 3 + 1, 0
        elif key in (curses.KEY_LEFT, ord('h')):
            page, offset = (page - 2) % 3 + 1, 0
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
            offset = max(0, body_length - available)
        elif key in (ord('r'), ord('R')):
            next_update = 0


def run(collector, palette_path=None):
    curses.wrapper(_screen, collector, palette_path)
