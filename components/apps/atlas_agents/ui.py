"""Read-only, palette-aware terminal dashboard for the current Codex agents."""
import curses
import math
import re
import time
import unicodedata

from atlas_panel import (
    DEFAULT_PALETTE, cell_width, clip, color_index as _color_index,
    draw_bar, layout, put as _put, read_palette, styles as _styles, title,
    card_rows, field_rows, read_layout_style, draw_panel_frame,
)


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
_MAX_AGENTS = 200
_MAX_TEXT = 4096
_COMPLETION_GRACE_SECONDS = 30


def clean(value):
    """Remove terminal escapes and invisible formatting from observer text."""
    value = _ANSI.sub('', str(value or '')[:_MAX_TEXT])
    return ' '.join(''.join(character for character in value
                            if not unicodedata.category(character).startswith('C')
                            or character in '\n\r\t').split())


def _wrapped(text, width, limit=2):
    """Wrap a short description to a bounded number of terminal-cell lines."""
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


def elapsed(agent, now, *, compact=False):
    start = _timestamp(agent.get('started_at'), now)
    end = now
    if agent.get('status') in ('completed', 'interrupted', 'error'):
        end = _timestamp(agent.get('finished_at'),
                         _timestamp(agent.get('updated_at'), start))
    seconds = max(0, int(min(now, end) - start))
    if compact:
        minutes, seconds = divmod(seconds, 60)
        if minutes >= 60:
            return f'{minutes // 60}:{minutes % 60:02d}:{seconds:02d}'
        return f'{minutes:02d}:{seconds:02d}'
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
    fallback = re.sub(r'[_-]+', ' ', clean(agent.get('name')))
    task = agent.get('task') or (fallback[:1].upper() + fallback[1:]) or 'Agent task'
    lines.extend(('  ' + line, 'foreground') for line in
                 _wrapped(task, max(0, width - 2), 2))
    plan = agent.get('plan')
    if isinstance(plan, list) and plan:
        valid = [item for item in plan if isinstance(item, dict)]
        if valid:
            done = sum(item.get('status') == 'completed' for item in valid)
            lines.append((f'  Plan: {done} / {len(valid)} complete', 'secondary'))
    lines.append(('', 'foreground'))
    return lines


def _plan_steps(plan):
    if not isinstance(plan, list):
        return []
    aliases = {'pending': 'pending', 'inProgress': 'in_progress',
               'in_progress': 'in_progress', 'completed': 'completed'}
    return [{'status': aliases[item['status']],
             'step': clean(item.get('step')) if isinstance(item.get('step'), str) else ''}
            for item in plan[:64] if isinstance(item, dict)
            and isinstance(item.get('status'), str) and item['status'] in aliases]


def _split_rows(left, right, width, left_role, right_role):
    right_width = cell_width(right)
    if right and cell_width(left) + right_width + 2 <= width:
        return [(left + ' ' * (width - cell_width(left) - right_width) + right,
                 f'split:{left_role}:{right_role}:{right_width}')]
    rows = [(line, left_role) for line in _wrapped(left, width, 2)]
    if right:
        rows.extend((line, right_role) for line in _wrapped(right, width, 2))
    return rows


def _framed_agent_rows(agent, width, now, *, show_plan=False):
    if width < 16:
        return _agent_rows(agent, width, now)
    inner = width - 4
    symbol, label, role = STATUS.get(agent.get('status'), STATUS['unknown'])
    symbol = {'waiting': '▲', 'error': '✖', 'completed': '■'}.get(agent.get('status'), symbol)
    name = re.sub(r'[_-]+', ' ', clean(agent.get('name') or agent.get('id') or 'Agent'))
    name = name[:1].upper() + name[1:]
    completed = agent.get('status') == 'completed'
    valid = _plan_steps(agent.get('plan'))
    agent_role = clean(agent.get('role')).upper()
    heading = 'Agent' if name.casefold() == 'agent' else 'Agent · ' + name
    rows = _split_rows(heading, agent_role, inner, 'bright_foreground', 'secondary')
    rows.extend(_split_rows(symbol + ' ' + label, elapsed(agent, now, compact=True), inner,
                            role, 'secondary'))
    if valid:
        done = sum(item['status'] == 'completed' for item in valid)
        count = f'Plan  {done} of {len(valid)} steps complete'
        cells = ' '.join('█' if item['status'] == 'completed' else '□' for item in valid)
        if cell_width(count) + cell_width(cells) + 2 <= inner:
            rows.extend(_split_rows(count, cells, inner, 'secondary',
                                    'plan_green' if completed else 'plan_accent'))
        else:
            rows.extend((line, 'secondary') for line in _wrapped(count, inner, 2))
    if isinstance(agent.get('plan'), list) and len(agent['plan']) > 64:
        rows.extend((line, 'secondary') for line in _wrapped('Plan limited to first 64 entries', inner, 2))
    task = clean(agent.get('task'))
    normalized = lambda text: text.casefold().rstrip('.')
    if task and normalized(task) != normalized(name):
        rows.extend((line, 'foreground') for line in _wrapped(task, inner, 2))
    activity = clean(agent.get('activity'))
    if not completed and activity and normalized(activity) not in (
            normalized(task), normalized(name), label.casefold()):
        rows.extend((line, 'secondary') for line in _wrapped('Now · ' + activity, inner, 2))
    if agent.get('status') in ('running', 'starting', 'waiting', 'idle'):
        next_step = next((item['step'] for item in valid
                          if item['status'] == 'pending'), '')
        if next_step and normalized(next_step) not in (
                normalized(task), normalized(activity), normalized(name)):
            rows.extend((line, 'secondary') for line in _wrapped('Next · ' + next_step, inner, 2))
    if show_plan:
        symbols = {'completed': ('✓', 'green'), 'in_progress': ('●', 'accent'),
                   'pending': ('○', 'secondary')}
        for item in valid:
            symbol, step_role = symbols[item['status']]
            wrapped = _wrapped(item['step'] or 'Unnamed step', inner - 2, 2)
            rows.extend(((symbol if index == 0 else ' ') + ' ' + line, step_role)
                        for index, line in enumerate(wrapped))
    return card_rows(rows, width) + [('', 'foreground')]


def dashboard(snapshot, width, now=None, *, show_completed=False, show_plan=False, style="classic"):
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
    if style == 'framed':
        if show_completed and history:
            counts['completed'] = counts.get('completed', 0) + len(history)
        summary = ' / '.join(f'{counts[key]} ' + ('DONE' if key == 'completed' else key.upper())
                             for key in ('running', 'waiting', 'completed', 'interrupted', 'error', 'unknown')
                             if counts.get(key))
    lines = [(title('agents', width), 'accent'),
             (summary or (('NO ACTIVE AGENTS' if history else 'NO AGENTS YET') if style == 'framed'
                          else ('No active agents' if history else 'No agents yet')), 'secondary'),
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
                     _wrapped('Task status and reported plan steps update automatically.', width, 3))
    for agent in agents:
        lines.extend(_framed_agent_rows(agent, width, now, show_plan=show_plan) if style == 'framed'
                     else _agent_rows(agent, width, now))
    if history:
        symbol, action = ('▾', 'hide') if show_completed else ('▸', 'show')
        lines.append((f'{symbol} Recently completed ({len(history)}) · h {action}', 'secondary'))
        if show_completed:
            lines.append(('', 'foreground'))
            for agent in history:
                lines.extend(_framed_agent_rows(agent, width, now, show_plan=show_plan) if style == 'framed'
                     else _agent_rows(agent, width, now))
    if len(raw_agents) > _MAX_AGENTS:
        lines.append((f'{len(raw_agents) - _MAX_AGENTS} more agents omitted', 'secondary'))
    return [(clip(text, width), role) for text, role in lines]


def _footer(width, presentation):
    if presentation == 'framed' and width >= 34:
        return ['↑↓/jk scroll · h history', 'p plan · r refresh · q close']
    if presentation == 'framed':
        width = max(0, width - 4)
        return ('h history · p plan · q' if width >= 23 else
                'p plan · q close' if width >= 16 else 'q close')
    return ('↑↓/jk scroll · h history · r refresh · q close' if width >= 44 else
            '↑↓ scroll · h history · r refresh · q close' if width >= 41 else
            '↑↓ scroll · h history · r · q close' if width >= 34 else
            '↑↓ · h history · r · q' if width >= 23 else
            'h history · q close' if width >= 19 else 'q close')


def _screen(screen, get_snapshot, palette_path, on_refresh):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.timeout(500)
    offset = 0
    show_completed = False
    show_plan = False
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
        left, width = layout(columns)
        presentation = read_layout_style()
        rows = dashboard(snapshot, width, now, show_completed=show_completed,
                         show_plan=show_plan, style=presentation)
        body = rows[4:]
        footer = _footer(width, presentation)
        offset, available, body_length, width = draw_panel_frame(
            screen, rows, styles, offset, footer, style=presentation,
            dimensions=(height, columns))
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
        elif key in (ord('p'), ord('P')) and presentation == 'framed':
            show_plan = not show_plan
            offset = 0
        elif key in (ord('r'), ord('R')):
            if on_refresh is not None:
                on_refresh()
            next_update = 0


def run(get_snapshot, palette_path=None, on_refresh=None):
    """Display agent snapshots without changing terminal fonts or global colors."""
    curses.wrapper(_screen, get_snapshot, palette_path, on_refresh)
