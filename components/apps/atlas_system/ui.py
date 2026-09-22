"""Palette-aware curses presentation for local system snapshots."""
import curses
import re
import time
import unicodedata

from atlas_panel import cell_width, clip, draw_panel_frame, layout, read_palette, styles, title


_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)|'
                   r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')


def clean(value):
    """Collapse terminal controls from kernel and process-provided strings."""
    value = _ANSI.sub('', str('' if value is None else value)[:4096])
    return ' '.join(''.join(character for character in value
                            if not unicodedata.category(character).startswith('C')
                            or character in '\n\r\t').split())


def bytes_text(value, rate=False):
    try:
        value = max(0.0, float(value))
    except (TypeError, ValueError):
        return 'INITIALIZING' if rate else 'UNAVAILABLE'
    units = ('B', 'KiB', 'MiB', 'GiB', 'TiB')
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    result = f'{value:.0f} {unit}' if value >= 10 or unit == 'B' else f'{value:.1f} {unit}'
    return result + '/s' if rate else result


def _pair(label, value, width):
    label, value = clean(label), clean(value)
    room = max(1, width - cell_width(label) - 1)
    value = clip(value, room)
    return clip(label + ' ' * max(1, width - cell_width(label) - cell_width(value)) + value, width)


def _bar(value, width=16):
    if not isinstance(value, (int, float)):
        return 'INITIALIZING'
    value = max(0, min(100, value))
    filled = round(width * value / 100)
    return '█' * filled + '░' * (width - filled) + f' {value:4.1f}%'


def _section(rows, label, width):
    if len(rows) > 4 and rows[-1][0]:
        rows.append(('', 'foreground'))
    rows.append((clip(label.upper(), width), 'secondary'))


def overview(snapshot, width):
    rows = [(title('system', width), 'accent'),
            (_pair(snapshot.get('hostname') or 'LOCAL', snapshot.get('uptime_text') or 'UPTIME UNKNOWN', width), 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    _section(rows, 'Resources', width)
    rows.append((_pair('CPU', _bar(snapshot.get('cpu_percent')), width), 'accent'))
    memory = snapshot.get('memory') if isinstance(snapshot.get('memory'), dict) else {}
    rows.append((_pair('MEMORY', _bar(memory.get('percent')), width), 'foreground'))
    rows.append((_pair('Used', f"{bytes_text(memory.get('used'))} / {bytes_text(memory.get('total'))}", width), 'secondary'))
    disk = snapshot.get('filesystem') if isinstance(snapshot.get('filesystem'), dict) else {}
    rows.append((_pair('ROOT', _bar(disk.get('percent')), width), 'foreground'))
    rows.append((_pair('Used', f"{bytes_text(disk.get('used'))} / {bytes_text(disk.get('total'))}", width), 'secondary'))
    load = snapshot.get('load')
    rows.append((_pair('Load 1 / 5 / 15', ' / '.join(f'{value:.2f}' for value in load) if isinstance(load, list) and len(load) == 3 else 'UNAVAILABLE', width), 'foreground'))

    _section(rows, 'Network activity', width)
    network = snapshot.get('network') if isinstance(snapshot.get('network'), dict) else {}
    rows.append((_pair('Receive', bytes_text(network.get('receive_rate'), True), width), 'green'))
    rows.append((_pair('Send', bytes_text(network.get('send_rate'), True), width), 'accent'))
    rows.append((_pair('Interface counters', f"↓ {bytes_text(network.get('received'))}  ↑ {bytes_text(network.get('sent'))}", width), 'secondary'))

    if snapshot.get('temperature') is not None or snapshot.get('battery'):
        _section(rows, 'Hardware', width)
        if snapshot.get('temperature') is not None:
            temperature = float(snapshot['temperature'])
            rows.append((_pair('Peak thermal zone', f'{temperature:.1f} °C', width),
                         'yellow' if temperature >= 80 else 'foreground'))
        battery = snapshot.get('battery')
        if isinstance(battery, dict):
            percent = battery.get('percent')
            value = (f'{percent}% · ' if isinstance(percent, int) else '') + str(battery.get('status') or 'Unknown')
            rows.append((_pair('Battery', value, width), 'foreground'))

    errors = snapshot.get('errors') if isinstance(snapshot.get('errors'), list) else []
    if errors:
        _section(rows, 'Unavailable', width)
        rows.extend((clip(clean(error), width), 'yellow') for error in errors[:8])
    _section(rows, 'Host', width)
    rows.append((_pair('Kernel', snapshot.get('kernel') or 'UNAVAILABLE', width), 'secondary'))
    rows.append(('First-sample rates initialize on the next refresh.', 'muted'))
    return rows


def processes(snapshot, width):
    items = snapshot.get('processes') if isinstance(snapshot.get('processes'), list) else []
    rows = [(title('system', width), 'accent'),
            (f'{len(items)} processes · current CPU and memory', 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    if not items:
        rows.append(('Process data unavailable.', 'yellow'))
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = item.get('pid', '?')
        rows.append((_pair(f'PID {pid}', bytes_text(item.get('rss')) + ' RSS', width), 'bright_foreground'))
        current = item.get('cpu_percent')
        cpu = f'{current:.1f}%' if isinstance(current, (int, float)) else 'INITIALIZING'
        rows.append((_pair('  CPU', cpu, width), 'accent'))
        rows.append((clip('  ' + clean(item.get('command') or 'unknown'), width), 'foreground'))
        rows.append(('', 'foreground'))
    return rows


def dashboard(snapshot, width, page=1):
    width = max(0, min(int(width), 4096))
    render = processes if page == 2 else overview
    palette = read_palette()
    return [(clip(text, width), role if role in palette else 'foreground')
            for text, role in render(snapshot if isinstance(snapshot, dict) else {}, width)]


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
            except (OSError, ValueError) as error:
                snapshot = dict(snapshot, errors=[f'Collector unavailable: {error}'])
            next_update = now + 1
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
        footer = ('1 overview · 2 processes · ↑↓/jk scroll · r refresh · q close'
                  if width >= 58 else
                  '1 overview · 2 processes · ↑↓ · r refresh · q close'
                  if width >= 49 else
                  '1 overview · 2 processes · ↑↓ · r · q close'
                  if width >= 42 else
                  '1 overview · 2 processes · r · q' if width >= 32 else
                  '1/2 pages · r · q')
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
            offset = max(0, body_length - available)
        elif key in (ord('r'), ord('R')):
            next_update = 0


def run(collector, palette_path=None):
    curses.wrapper(_screen, collector, palette_path)
