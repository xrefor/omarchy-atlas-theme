"""Shared presentation for ATLAS terminal panels; no service or observer logic."""
import curses
import json
from pathlib import Path
import re
import unicodedata


DEFAULT_PALETTE = {
    'background': '#100e0c',
    'dark_background': '#0a0908',
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


_HEX = re.compile(r'#[0-9a-fA-F]{6}\Z')


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


def read_layout_style(path=None):
    """Missing or invalid preferences retain the original, reversible layout."""
    path = Path(path) if path is not None else Path.home() / '.config/atlas/layout.json'
    try:
        if path.stat().st_size <= 65536:
            value = json.loads(path.read_text())
            if isinstance(value, dict) and value.get('style') == 'framed':
                return 'framed'
    except (OSError, ValueError):
        pass
    return 'classic'


def card_rows(rows, width):
    """Frame content without changing its semantic colors or claiming progress."""
    if width < 12:
        return [(clip(text, width), role) for text, role in rows]
    inner = width - 4
    result = [('┌' + '─' * (width - 2) + '┐', 'card:dark_foreground')]
    for text, role in rows:
        text = clip(text, inner)
        result.append(('│ ' + text + ' ' * (inner - cell_width(text)) + ' │',
                       'card:' + role))
    result.append(('└' + '─' * (width - 2) + '┘', 'card:dark_foreground'))
    return result


def _card_split(text, role, width):
    """Validate a paired row and locate its right span on display-cell boundaries."""
    match = re.fullmatch(r'split:([a-z_]+):([a-z_]+):([0-9]{1,4})', role)
    if not match or not (text.startswith('│ ') and text.endswith(' │')):
        return None
    left_role, right_role, count = match.groups()
    base_right = right_role.removeprefix('plan_')
    if (left_role not in DEFAULT_PALETTE or base_right not in DEFAULT_PALETTE
            or (right_role.startswith('plan_') and right_role not in ('plan_accent', 'plan_green'))):
        return None
    inner, count = text[2:-2], int(count)
    inner_width = cell_width(inner)
    if cell_width(text) != width or not 0 < count <= inner_width:
        return None
    target, used = inner_width - count, 0
    for index, character in enumerate(inner):
        # A combining mark belongs to the preceding cell, never the right span.
        if used == target and not unicodedata.combining(character):
            return left_role, base_right, inner[index:], target, right_role.startswith('plan_')
        used += cell_width(character)
        if used > target:
            break
    return None


def draw_row(screen, row, text, role, panel_styles, columns, left, width):
    """Outline cards on the continuous panel surface, without a dark tile."""
    if role.startswith('card:'):
        role = role[5:]
        split = _card_split(text, role, width) if role.startswith('split:') else None
        base_role = split[0] if split else 'foreground' if role.startswith('split:') else role
        backing = panel_styles.get(base_role, panel_styles.get('muted', panel_styles['foreground']))
        put(screen, row, clip(text, width), backing, columns, left)
        # Unfinished plan cells describe absence of completion, not activity.
        cell_style = panel_styles['secondary']
        if split:
            _, right_role, suffix, start, plan = split
            right = left + 2 + start
            put(screen, row, suffix, panel_styles.get(right_role, panel_styles['foreground']), columns, right)
            if plan:
                for index, character in enumerate(suffix):
                    if character == '□':
                        put(screen, row, '█', cell_style, columns,
                            right + cell_width(suffix[:index]))
        else:
            plan_cells = re.fullmatch(r'[█□](?: [█□])*', text[2:-2].strip())
            for index, character in enumerate(text):
                if plan_cells and character == '□':
                    put(screen, row, '█', cell_style, columns,
                        left + cell_width(text[:index]))
            metadata = re.match(r'^│ ((?:Elapsed|Plan)\s+)(.*?)(\s+│)$', text)
            if metadata:
                put(screen, row, metadata[2], panel_styles['bright_foreground'],
                    columns, left + 2 + cell_width(metadata[1]))
        edge = panel_styles.get('dark_foreground', panel_styles['muted'])
        if text.startswith('│'):
            put(screen, row, '│', edge, columns, left)
            put(screen, row, '│', edge, columns, left + width - 1)
    else:
        put(screen, row, clip(text, width), panel_styles.get(role, panel_styles['foreground']), columns, left)


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


def _rgb(value):
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _indexed_rgb(index):
    if index >= 232:
        return (8 + (index - 232) * 10,) * 3
    steps = (0, 95, 135, 175, 215, 255)
    value = index - 16
    return steps[value // 36], steps[(value // 6) % 6], steps[value % 6]


def color_index(value):
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


def styles(palette):
    styles = {key: curses.A_NORMAL for key in palette}
    styles['header'] = curses.A_NORMAL
    styles['header_prefix'] = curses.A_NORMAL
    styles['footer'] = curses.A_NORMAL
    styles.update({'card_' + key: curses.A_NORMAL for key in palette})
    try:
        if not curses.has_colors():
            return styles
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        background = color_index(palette['background'])
        pairs = [(key, value, background) for key, value in palette.items()]
        pairs += [('card_' + key, value, color_index(palette['dark_background']))
                  for key, value in palette.items()]
        pairs += [('header', palette['accent'], color_index(palette['lighter_background'])),
                  ('header_prefix', palette['dark_foreground'], color_index(palette['lighter_background'])),
                  ('footer', palette['secondary'], color_index(palette['lighter_background']))]
        for pair, (key, value, backing) in enumerate(pairs, 1):
            if pair >= getattr(curses, 'COLOR_PAIRS', 0):
                break
            try:
                curses.init_pair(pair, color_index(value), backing)
                styles[key] = curses.color_pair(pair)
            except (curses.error, ValueError, OverflowError):
                continue
    except curses.error:
        pass
    return styles


def layout(columns):
    """Keep a common inset and leave the terminal's final cell untouched."""
    usable = max(0, columns - 1)
    left = 2 if usable >= 12 else 1 if usable >= 4 else 0
    return left, max(0, usable - 2 * left)


def put(screen, row, text, style, columns, left=0):
    """Draw text without splitting wide glyphs or writing through the right edge."""
    width = max(0, columns - 1 - left)
    if width == 0 or row < 0:
        return
    try:
        screen.addstr(row, left, clip(text, width), style)
    except (curses.error, UnicodeError):
        # A resize can invalidate coordinates between layout and drawing.
        pass


def draw_bar(screen, row, text, style, columns, prefix_style=None):
    """Paint a full strip with text aligned to the common content inset."""
    left, width = layout(columns)
    put(screen, row, ' ' * max(0, columns - 1), style, columns)
    put(screen, row, clip(text, width), style, columns, left)
    if prefix_style is not None and text.startswith('//'):
        put(screen, row, clip('//', width), prefix_style, columns, left)


def draw_panel_frame(screen, rows, panel_styles, offset, footer, *, style=None, dimensions=None):
    """Draw the shared pinned header, scrolling body and footer strip.

    The first four rows are the panel header contract used by Agents and Nym.
    Returns the clamped offset, visible body rows, total body rows and content
    width so panel-specific input handling can remain local.
    """
    height, columns = dimensions or screen.getmaxyx()
    style = read_layout_style() if style is None else style
    if style == 'framed':
        return draw_framed_panel(screen, rows, panel_styles, offset, footer,
                                 dimensions=(height, columns))
    left, width = layout(columns)
    fixed = min(4, max(0, height - 1))
    available = max(0, height - fixed - (1 if height else 0))
    body = rows[4:]
    offset = min(max(0, offset), max(0, len(body) - available))
    screen.erase()
    for row, (line, role) in enumerate(rows[:fixed]):
        if row == 0:
            draw_bar(screen, row, line, panel_styles['header'], columns,
                     prefix_style=panel_styles['header_prefix'])
        else:
            put(screen, row, line, panel_styles.get(role, panel_styles['foreground']),
                columns, left=left)
    for row, (line, role) in enumerate(body[offset:offset + available], fixed):
        put(screen, row, line, panel_styles.get(role, panel_styles['foreground']),
            columns, left=left)
    if height:
        draw_bar(screen, height - 1, footer, panel_styles['footer'], columns)
    return offset, available, len(body), width


def draw_framed_panel(screen, rows, panel_styles, offset, footer, *, dimensions=None):
    """Retain four pinned header rows and a scrolling body; reclaim rails when tiny."""
    height, columns = dimensions or screen.getmaxyx()
    left, width = layout(columns)
    if height < 10 or columns < 16:
        # Small terminals prioritize content and controls over decoration.
        plain = [(text, role.removeprefix('card:')) for text, role in rows]
        if not isinstance(footer, str):
            choices = list(footer)
            exits = [line for line in choices if re.search(r'\bq\b|\bclose\b', line, re.I)]
            footer = exits[-1] if exits else choices[0] if choices else ''
            if exits and cell_width(footer) > width:
                footer = 'q close'
        return draw_panel_frame(screen, plain, panel_styles, offset, footer,
                                style='classic', dimensions=(height, columns))
    footer = [footer] if isinstance(footer, str) else list(footer)
    footer = footer[:max(1, height - 8)]
    footer_height = len(footer) + 3
    available = max(0, height - 4 - footer_height)
    body = rows[4:]
    offset = min(max(0, offset), max(0, len(body) - available))
    edge = panel_styles.get('dark_foreground', panel_styles['muted'])
    foreground = panel_styles['foreground']
    screen.erase()
    # Every surface shares the normal background, including empty body rows.
    for row in range(height):
        put(screen, row, ' ' * (columns - 1), foreground, columns)
        if 0 < row < height - 1:
            put(screen, row, '│', edge, columns)
            put(screen, row, '│', edge, columns, columns - 2)
    put(screen, 0, '┌' + '─' * (columns - 3) + '┐', edge, columns)
    put(screen, height - 1, '└' + '─' * (columns - 3) + '┘', edge, columns)
    heading = '▎ ' + rows[0][0].removeprefix('// ')
    subtitle = rows[1][0]
    combined = cell_width(heading) + 2 + cell_width(subtitle) <= width
    put(screen, 1, clip(heading, width), panel_styles['bright_foreground'], columns, left)
    put(screen, 1, '▎', panel_styles['accent'], columns, left)
    if combined:
        put(screen, 1, subtitle, panel_styles['secondary'], columns,
            left + width - cell_width(subtitle))
    else:
        put(screen, 2, clip(subtitle, width), panel_styles['secondary'], columns, left)
    separator = 2 if combined else 3
    put(screen, separator, '├' + '─' * (columns - 3) + '┤', edge, columns)
    for row, (line, role) in enumerate(body[offset:offset + available], 4):
        draw_row(screen, row, line, role, panel_styles, columns, left, width)
    start = height - footer_height
    put(screen, start, '┌' + '─' * (width - 2) + '┐', edge, columns, left)
    for row, text in enumerate(footer, start + 1):
        inner = width - 4
        text = clip(text, inner)
        line = '│ ' + text + ' ' * (inner - cell_width(text)) + ' │'
        put(screen, row, line, panel_styles['secondary'], columns, left)
        put(screen, row, '│', edge, columns, left)
        put(screen, row, '│', edge, columns, left + width - 1)
    put(screen, height - 2, '└' + '─' * (width - 2) + '┘', edge, columns, left)
    return offset, available, len(body), width


def title(name, width):
    """Use the same spaced title and compact fallback in every panel."""
    name = name.upper()
    spaced = '// ' + ' '.join(name)
    return clip(spaced if cell_width(spaced) <= width else '// ' + name, width)


def _word_lines(text, width):
    """Wrap values by terminal cells, including long identifiers without spaces."""
    if width <= 0:
        return []
    lines, line = [], ''
    for word in text.split():
        candidate = line + (' ' if line else '') + word
        if cell_width(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ''
        for character in word:
            size = cell_width(character)
            if size > width:
                character = '�'
                size = 1
            if cell_width(line) + size > width:
                lines.append(line)
                line = ''
            line += character
    if line:
        lines.append(line)
    return lines


def field_rows(fields, width, *, label_width=0, gap='   '):
    """Pack complete label/value groups, with aligned long-value continuations."""
    if width <= 0:
        return []
    rows, line = [], ''
    for label, value in fields:
        label, value = str(label), str(value)
        prefix = label + ' ' * max(2, label_width - cell_width(label))
        field = (prefix + value).rstrip()
        candidate = line + (gap if line else '') + field
        if cell_width(candidate) <= width:
            line = candidate
            continue
        if line:
            rows.append(line)
            line = ''
        if cell_width(field) <= width:
            line = field
            continue
        indent = cell_width(prefix)
        if width - indent >= min(12, width // 2) and indent < width:
            parts = _word_lines(value, width - indent)
            rows.extend((prefix if index == 0 else ' ' * indent) + part
                        for index, part in enumerate(parts))
        else:
            # Very narrow panes stack the label above its value to avoid a
            # large indent leaving only one or two characters per line.
            rows.extend(_word_lines(label, width))
            indent = 2 if width >= 8 else 0
            rows.extend(' ' * indent + part for part in _word_lines(value, width - indent))
    if line:
        rows.append(line)
    return rows


def sidebar_width(origin_columns):
    """Prefer 60 columns while reserving at least 80 for the originating task."""
    if origin_columns >= 141:
        return 60
    return 48 if origin_columns >= 130 else None
