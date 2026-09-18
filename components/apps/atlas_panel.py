"""Shared presentation for ATLAS terminal panels; no service or observer logic."""
import curses
import json
from pathlib import Path
import re
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
