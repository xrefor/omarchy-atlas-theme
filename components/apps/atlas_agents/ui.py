"""Read-only, palette-aware terminal dashboard for the current Codex agents."""
import curses
import json
import math
from pathlib import Path
import re
import time
import unicodedata


DEFAULT_PALETTE = {
    'background': '#100e0c',
    'lighter_background': '#1c1814',
    'foreground': '#d6cfc4',
    'dark_foreground': '#6e675c',
    'bright_foreground': '#f2ebe0',
    'secondary': '#a69b8c',
    'muted': '#3a342c',
    'accent': '#ff5a12',
    'green': '#8a9a4a',
    'yellow': '#f0a202',
    'red': '#c22e16',
}
STATUS = {
    'starting': ('◌', 'STARTING', 'accent'),
    'running': ('●', 'RUNNING', 'accent'),
    'waiting': ('◌', 'WAITING', 'yellow'),
    'idle': ('○', 'IDLE', 'secondary'),
    'completed': ('✓', 'COMPLETED', 'green'),
    'interrupted': ('−', 'INTERRUPTED', 'yellow'),
    'error': ('!', 'ERROR', 'red'),
    'unknown': ('?', 'UNKNOWN', 'secondary'),
}
_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)|'
                   r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')
_HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')
_MAX_AGENTS = 200
_MAX_TEXT = 4096
_COMPLETION_GRACE_SECONDS = 30


def read_palette(path=None):
    """Read active semantic colors; missing or invalid roles use ATLAS defaults."""
    colors = DEFAULT_PALETTE.copy()
    path = Path(path) if path is not None else Path.home() / '.config/atlas/agents-palette.json'
    try:
        if path.stat().st_size > 65536:
            return colors
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return colors
    if isinstance(value, dict):
        colors.update({key: value[key].lower() for key in colors
                       if isinstance(value.get(key), str) and _HEX.fullmatch(value[key])})
    return colors


def clean(value):
    """Remove terminal escapes and invisible formatting from observer text."""
    value = _ANSI.sub('', str(value or '')[:_MAX_TEXT])
    return ' '.join(''.join(character for character in value
                            if not unicodedata.category(character).startswith('C')
                            or character in '\n\r\t').split())


def cell_width(text):
    return sum(0 if unicodedata.combining(character) else
               2 if unicodedata.east_asian_width(character) in ('W', 'F') else 1
               for character in text)


def clip(text, width):
    """Clip by display cells, keeping wide glyphs intact and marking truncation."""
    if width <= 0:
        return ''
    if cell_width(text) <= width:
        return text
    result, used = [], 0
    for character in text:
        size = cell_width(character)
        if used + size > width - 1:
            break
        if size or result:
            result.append(character)
            used += size
    return ''.join(result) + '…'


def _wrapped(text, width, limit=2):
    """Wrap a short activity to a bounded number of lines without dropping words."""
    text = clean(text)
    if not text or width <= 0:
        return []
    lines = []
    while text and len(lines) < limit - 1 and cell_width(text) > width:
        used, end = 0, 0
        for index, character in enumerate(text):
            size = cell_width(character)
            if used + size > width:
                break
            used += size
            end = index + 1
        if not end:
            break
        space = text.rfind(' ', 0, end + 1)
        if space > end // 2:
            end = space
        lines.append(text[:end])
        text = text[end:].lstrip()
    if text:
        lines.append(clip(text, width))
    return lines


def _timestamp(value, fallback):
    try:
        value = float(value)
        return value if math.isfinite(value) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def elapsed(agent, now):
    start = _timestamp(agent.get('started_at'), now)
    end = now
    if agent.get('status') in ('completed', 'interrupted', 'error'):
        end = _timestamp(agent.get('finished_at'),
                         _timestamp(agent.get('updated_at'), start))
    seconds = max(0, int(min(now, end) - start))
    if seconds >= 3600:
        return f'{seconds // 3600}h {(seconds % 3600) // 60:02d}m'
    if seconds >= 60:
        return f'{seconds // 60}m {seconds % 60:02d}s'
    return f'{seconds}s'


def _in_history(agent, now):
    finished = agent.get('finished_at')
    if agent.get('status') != 'completed' or isinstance(finished, bool):
        return False
    finished = _timestamp(finished, None)
    return finished is not None and finished >= 0 and now - finished >= _COMPLETION_GRACE_SECONDS


def _agent_rows(agent, width, now):
    symbol, label, role = STATUS.get(agent.get('status'), STATUS['unknown'])
    name = clean(agent.get('name') or agent.get('id') or 'Agent')
    lines = [(f'{symbol} {name}', 'bright_foreground'),
             (f'  {label} · {elapsed(agent, now)}', role)]
    agent_role = clean(agent.get('role'))
    if agent_role:
        lines.append((f'  {agent_role}', 'secondary'))
    activity = agent.get('activity') or agent.get('task') or 'Waiting for an activity update…'
    lines.extend(('  ' + line, 'foreground') for line in
                 _wrapped(activity, max(0, width - 2), 2))
    plan = agent.get('plan')
    if isinstance(plan, list) and plan:
        valid = [item for item in plan if isinstance(item, dict)]
        if valid:
            done = sum(item.get('status') == 'completed' for item in valid)
            lines.append((f'  Plan: {done} / {len(valid)} complete', 'secondary'))
    lines.append(('', 'foreground'))
    return lines


def dashboard(snapshot, width, now=None, *, show_completed=False):
    """Return bounded (text, semantic color role) rows; the first four are fixed."""
    now = time.time() if now is None else now
    width = max(0, min(int(width), 4096))
    raw_agents = snapshot.get('agents', [])
    if not isinstance(raw_agents, list):
        raw_agents = []
    agents = [agent for agent in raw_agents[:_MAX_AGENTS] if isinstance(agent, dict)]
    history = [agent for agent in agents if _in_history(agent, now)]
    agents = [agent for agent in agents if not _in_history(agent, now)]
    history.sort(key=lambda agent: -_timestamp(agent.get('finished_at'), 0))
    order = {'running': 0, 'starting': 0, 'waiting': 1, 'error': 2,
             'interrupted': 3, 'idle': 4, 'unknown': 5, 'completed': 6}
    agents.sort(key=lambda agent: (order.get(agent.get('status'), 5),
                                  -_timestamp(agent.get('started_at'), 0)))
    counts = {}
    for agent in agents:
        status = agent.get('status', 'unknown')
        if status not in STATUS:
            status = 'unknown'
        label = {'starting': 'running', 'idle': 'waiting'}.get(status, status)
        counts[label] = counts.get(label, 0) + 1
    summary = ' · '.join(f'{counts[key]} {key}' for key in
                         ('running', 'waiting', 'completed', 'interrupted', 'error', 'unknown')
                         if counts.get(key))
    lines = [('// A G E N T S' if width >= 14 else '// AGENTS', 'accent'),
             (summary or ('No active agents' if history else 'No agents yet'), 'secondary'),
             ('─' * width, 'muted'), ('', 'foreground')]
    if snapshot.get('error'):
        lines.extend((line, 'yellow') for line in _wrapped(snapshot['error'], width, 2))
        lines.append(('', 'foreground'))
    elif not snapshot.get('connected'):
        lines.extend((line, 'secondary') for line in
                     _wrapped('Waiting for this Codex conversation…', width, 2))
        lines.append(('', 'foreground'))
    if not agents and not history:
        lines.extend((line, 'foreground') for line in
                     _wrapped('Spawned agents will appear here.', width, 2))
        lines.extend((line, 'secondary') for line in
                     _wrapped('Activity and reported plan steps update automatically.', width, 3))
    for agent in agents:
        lines.extend(_agent_rows(agent, width, now))
    if history:
        symbol, action = ('▾', 'hide') if show_completed else ('▸', 'show')
        lines.append((f'{symbol} Recently completed ({len(history)}) · h {action}', 'secondary'))
        if show_completed:
            lines.append(('', 'foreground'))
            for agent in history:
                lines.extend(_agent_rows(agent, width, now))
    if len(raw_agents) > _MAX_AGENTS:
        lines.append((f'{len(raw_agents) - _MAX_AGENTS} more agents omitted', 'secondary'))
    return [(clip(text, width), role) for text, role in lines]


def _rgb(value):
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _indexed_rgb(index):
    if index >= 232:
        return (8 + (index - 232) * 10,) * 3
    steps = (0, 95, 135, 175, 215, 255)
    value = index - 16
    return steps[value // 36], steps[(value // 6) % 6], steps[value % 6]


def _color_index(value):
    rgb = _rgb(value)
    count = getattr(curses, 'COLORS', 0)
    if count >= 16777216 and getattr(curses, 'has_extended_color_support', lambda: False)():
        return rgb[0] << 16 | rgb[1] << 8 | rgb[2]
    if count >= 256:
        candidates = [(index, _indexed_rgb(index)) for index in range(16, 256)]
    else:
        candidates = []
        for index in range(min(count, 16)):
            try:
                channels = curses.color_content(index)
                candidates.append((index, tuple(channel * 255 // 1000 for channel in channels)))
            except curses.error:
                pass
        if not candidates:
            return -1
    return min(candidates, key=lambda item: sum((a - b) ** 2 for a, b in zip(rgb, item[1])))[0]


def _styles(palette):
    styles = {key: curses.A_NORMAL for key in palette}
    styles['header'] = curses.A_NORMAL
    styles['header_prefix'] = curses.A_NORMAL
    styles['footer'] = curses.A_NORMAL
    try:
        if not curses.has_colors():
            return styles
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        background = _color_index(palette['background'])
        pairs = [(key, value, background) for key, value in palette.items()]
        pairs += [('header', palette['accent'], _color_index(palette['lighter_background'])),
                  ('header_prefix', palette['dark_foreground'], _color_index(palette['lighter_background'])),
                  ('footer', palette['secondary'], _color_index(palette['lighter_background']))]
        for pair, (key, value, backing) in enumerate(pairs, 1):
            if pair >= getattr(curses, 'COLOR_PAIRS', 0):
                break
            try:
                curses.init_pair(pair, _color_index(value), backing)
                styles[key] = curses.color_pair(pair)
            except (curses.error, ValueError, OverflowError):
                continue
    except curses.error:
        pass
    return styles


def _put(screen, row, text, style, width):
    try:
        screen.addstr(row, 0, clip(text, width), style)
    except (curses.error, UnicodeError):
        # Resizes and terminals without the glyph can make an individual draw fail.
        pass


def _screen(screen, get_snapshot, palette_path, on_refresh):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.timeout(500)
    offset = 0
    show_completed = False
    previous_palette = None
    styles = {}
    snapshot = {'agents': [], 'connected': False}
    next_update = 0
    while True:
        now = time.time()
        tick = time.monotonic()
        if tick >= next_update:
            try:
                snapshot = get_snapshot()
            except (OSError, ValueError) as error:
                snapshot = dict(snapshot, connected=False, error=f'Observer unavailable: {error}')
            next_update = tick + 1
        palette = read_palette(palette_path)
        if palette != previous_palette:
            styles = _styles(palette)
            screen.bkgd(' ', styles['foreground'])
            previous_palette = palette
        height, columns = screen.getmaxyx()
        width = max(0, columns - 1)
        rows = dashboard(snapshot, width, now, show_completed=show_completed)
        fixed = min(4, max(0, height - 1))
        available = max(0, height - fixed - 1)
        body = rows[4:]
        offset = min(offset, max(0, len(body) - available))
        screen.erase()
        for row, (line, role) in enumerate(rows[:fixed]):
            if row == 0:
                _put(screen, row, line.ljust(width), styles['header'], width)
                _put(screen, row, line[:2], styles['header_prefix'], width)
            else:
                _put(screen, row, line, styles[role], width)
        for row, (line, role) in enumerate(body[offset:offset + available], fixed):
            _put(screen, row, line, styles[role], width)
        if height:
            footer = ('↑↓/jk scroll · h history · r refresh · q close' if width >= 44 else
                      '↑↓ scroll · h history · r · q close' if width >= 34 else
                      '↑↓ · h history · r · q' if width >= 23 else
                      'h history · q close' if width >= 19 else 'q close')
            if len(body) > available and width >= 48:
                footer += f'  {offset + 1}/{max(1, len(body) - available + 1)}'
            _put(screen, height - 1, footer.ljust(width), styles['footer'], width)
        screen.refresh()
        key = screen.getch()
        if key in (ord('q'), ord('Q'), 27):
            return
        if key in (curses.KEY_DOWN, ord('j')):
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
        elif key in (ord('h'), ord('H')):
            show_completed = not show_completed
            offset = 0
        elif key in (ord('r'), ord('R')):
            if on_refresh is not None:
                on_refresh()
            next_update = 0


def run(get_snapshot, palette_path=None, on_refresh=None):
    """Display agent snapshots without changing terminal fonts or global colors."""
    curses.wrapper(_screen, get_snapshot, palette_path, on_refresh)
