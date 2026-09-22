"""Palette-aware, evidence-first EVE Frontier terminal dashboard."""
import curses
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
import re
import time
import unicodedata

from atlas_panel import cell_width, clip, draw_bar, field_rows, layout, put, read_palette, styles, title


_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)|'
                   r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')
_MAX_TEXT = 4096


def clean(value):
    value = _ANSI.sub('', str('' if value is None else value)[:_MAX_TEXT])
    return ' '.join(''.join(character for character in value
                            if not unicodedata.category(character).startswith('C')
                            or character in '\n\r\t').split())


def short(value, size=12):
    value = clean(value)
    return value if len(value) <= size else value[:6] + '…' + value[-4:]


def age(value, now=None):
    now = time.time() if now is None else now
    try:
        seconds = max(0, int(now - float(value)))
    except (TypeError, ValueError, OverflowError):
        return 'UNKNOWN'
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m'
    if seconds < 86400:
        return f'{seconds // 3600}h'
    return f'{seconds // 86400}d'


def timestamp(value):
    try:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError
        return datetime.fromtimestamp(value).strftime('%H:%M')
    except (TypeError, ValueError, OverflowError, OSError):
        return '--:--'


def balance_text(balance):
    if clean(balance.get('status')).lower() != 'available':
        return 'UNAVAILABLE'
    raw, decimals = clean(balance.get('amount')), balance.get('decimals')
    symbol = clean(balance.get('symbol') or 'EVE')
    if not raw.isdigit() or not isinstance(decimals, int):
        return f'{raw or "—"} RAW UNITS'
    try:
        value = Decimal(raw).scaleb(-decimals)
    except (InvalidOperation, ValueError):
        return 'UNAVAILABLE'
    formatted = f'{value:f}'
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    return f'{formatted} {symbol}'


def _pair(label, value, width):
    label, value = clean(label), clean(value)
    room = max(1, width - cell_width(label) - 1)
    value = clip(value, room)
    gap = max(1, width - cell_width(label) - cell_width(value))
    return clip(label + ' ' * gap + value, width)


def _section(lines, name, width):
    if len(lines) > 4 and lines[-1][0]:
        lines.append(('', 'foreground'))
    lines.append((clip(clean(name).upper(), width), 'secondary'))


def _observed_role(value):
    value = clean(value).upper()
    return {'ONLINE': 'green', 'OFFLINE': 'red'}.get(value, 'foreground')


def _monitor_role(value):
    value = clean(value).upper()
    return {'UPDATED': 'accent', 'UNAVAILABLE': 'yellow',
            'ERROR': 'red'}.get(value, 'secondary')


def overview(snapshot, width, now):
    environment = clean(snapshot.get('environment') or 'NOT CONFIGURED').upper()
    chain = clean(snapshot.get('chain_label') or snapshot.get('chain_id') or 'CHAIN UNVERIFIED')
    retrieved = snapshot.get('retrieved_at')
    if snapshot.get('connected'):
        sync = f'RETRIEVED {age(retrieved, now)} AGO'
        sync_role = 'green' if age(retrieved, now) not in ('UNKNOWN',) else 'yellow'
    else:
        sync, sync_role = 'DATA UNAVAILABLE', 'yellow'
    lines = [(title('frontier', width), 'accent'),
             (_pair(environment, sync, width), sync_role),
             ('─' * width, 'muted'), ('', 'foreground')]
    warnings = snapshot.get('warnings') if isinstance(snapshot.get('warnings'), list) else []
    if snapshot.get('error'):
        _section(lines, 'Attention', width)
        lines.append((clip(clean(snapshot['error']), width), 'yellow'))
    for warning in warnings[:3]:
        lines.append((clip('▲ ' + clean(warning), width), 'yellow'))

    character = snapshot.get('character') if isinstance(snapshot.get('character'), dict) else {}
    _section(lines, 'Smart character', width)
    tribe = character.get('tribe_id')
    lines.append((_pair(character.get('name') or 'Unavailable',
                        'TRIBE ' + clean('—' if tribe is None or tribe == '' else tribe), width),
                  'bright_foreground'))
    lines.append((_pair('Address', short(character.get('address') or snapshot.get('wallet') or '—'), width),
                  'foreground'))
    verified = 'MATCHED' if character.get('verified') else 'UNAVAILABLE'
    lines.append((_pair('On-chain address binding', verified, width),
                  'green' if character.get('verified') else 'yellow'))

    _section(lines, 'Control', width)
    count = snapshot.get('capabilities_count')
    assemblies = snapshot.get('assemblies') if isinstance(snapshot.get('assemblies'), list) else []
    lines.append((_pair('Capabilities held', count if isinstance(count, int) else 'UNAVAILABLE', width),
                  'foreground'))
    controlled_count = snapshot.get('controlled_assemblies_count')
    lines.append((_pair('Controlled assemblies', controlled_count if isinstance(controlled_count, int) else 'UNAVAILABLE', width),
                  'foreground'))
    watched_count = sum(bool(item.get('watched')) for item in assemblies if isinstance(item, dict))
    if watched_count:
        lines.append((_pair('Additional watches', watched_count, width), 'foreground'))
    balance = snapshot.get('balance') if isinstance(snapshot.get('balance'), dict) else {}
    value = balance_text(balance)
    lines.append((_pair('EVE Token', value, width),
                  'foreground' if balance.get('status') == 'available' else 'yellow'))

    _section(lines, 'Controlled & watched assemblies', width)
    if not assemblies:
        if snapshot.get('connected') and isinstance(count, int):
            lines.append(('No controlled or watched assemblies.', 'secondary'))
        else:
            lines.append(('Assemblies unavailable — collection incomplete.', 'yellow'))
    for item in assemblies[:8]:
        if not isinstance(item, dict):
            continue
        name = clean(item.get('name') or item.get('type_name') or 'Assembly')
        observed = clean(item.get('state') or 'UNKNOWN').upper()
        monitor = clean(item.get('monitor') or 'UNAVAILABLE').upper()
        if item.get('baseline_created') and monitor == 'UNCHANGED':
            monitor += ' · BASELINE CREATED'
        lines.append((_pair(name, observed, width), _observed_role(observed)))
        lines.append((_pair('  Monitor', monitor + ' · v' + clean(item.get('version') or '—'), width),
                      _monitor_role(monitor)))

    activity = snapshot.get('activity') if isinstance(snapshot.get('activity'), list) else []
    _section(lines, 'Recent changes', width)
    if not activity:
        lines.append(('No locally observed changes yet.', 'secondary'))
    for event in activity[:5]:
        if not isinstance(event, dict):
            continue
        evidence_role = clean(event.get('role') or 'unknown').upper()
        text = (f"{timestamp(event.get('timestamp'))}  [{evidence_role}] "
                f"{clean(event.get('title') or 'Observed change')}")
        event_role = {'observed': 'accent', 'derived': 'yellow'}.get(
            clean(event.get('role')).lower(), clean(event.get('role') or 'foreground'))
        lines.append((clip(text, width), event_role))
        if event.get('detail'):
            lines.append((clip('       ' + clean(event['detail']), width), 'secondary'))

    _section(lines, 'Source', width)
    lines.append((_pair('Chain', short(chain, 22), width), 'foreground'))
    checkpoint = snapshot.get('checkpoint')
    lines.append((_pair('Checkpoint', 'UNAVAILABLE' if checkpoint is None or checkpoint == '' else checkpoint, width), 'foreground'))
    lag = snapshot.get('indexer_lag')
    lines.append((_pair('Indexer checkpoint lag', f'{int(lag)}s' if isinstance(lag, (int, float)) else 'UNAVAILABLE', width),
                  'foreground'))
    lines.append((_pair('Endpoint', clean(snapshot.get('endpoint') or 'NOT CONFIGURED'), width), 'secondary'))
    return lines


def infrastructure(snapshot, width, now):
    lines = [(title('infrastructure', width), 'accent'),
             (_pair(clean(snapshot.get('environment') or 'NOT CONFIGURED').upper(),
                    f"RETRIEVED {age(snapshot.get('retrieved_at'), now)} AGO", width), 'secondary'),
             ('─' * width, 'muted'), ('', 'foreground')]
    assemblies = snapshot.get('assemblies') if isinstance(snapshot.get('assemblies'), list) else []
    if not assemblies:
        message = ('No controlled or watched assemblies.' if snapshot.get('connected')
                   and isinstance(snapshot.get('capabilities_count'), int)
                   else 'Assemblies unavailable — collection incomplete.')
        lines.extend([(message, 'secondary' if snapshot.get('connected') else 'yellow'),
                      ('Capability discovery must complete before', 'foreground'),
                      ('the monitor infers additions or removals.', 'foreground')])
        return lines
    for index, item in enumerate(assemblies, 1):
        if not isinstance(item, dict):
            continue
        flags = ' / '.join(value for value, enabled in
                           (('CONTROLLED', item.get('controlled')), ('WATCHED', item.get('watched')))
                           if enabled)
        _section(lines, f'{index}  {item.get("name") or item.get("type_name") or "Assembly"}', width)
        if flags:
            lines.append((flags, 'secondary'))
        lines.append((_pair('Observed', clean(item.get('state') or 'UNKNOWN').upper(), width),
                      _observed_role(item.get('state'))))
        monitor = clean(item.get('monitor') or 'UNAVAILABLE').upper()
        if item.get('baseline_created') and monitor == 'UNCHANGED':
            monitor += ' · BASELINE CREATED'
        lines.append((_pair('Monitor', monitor, width),
                      _monitor_role(item.get('monitor'))))
        cap_ids = item.get('cap_ids') if isinstance(item.get('cap_ids'), list) else []
        if len(cap_ids) > 1:
            capability = 'MULTIPLE — CONTROL AMBIGUOUS'
        elif len(cap_ids) == 1:
            capability = cap_ids[0]
        else:
            capability = item.get('cap_id') or 'NOT HELD'
        evidence = [('Version', item.get('version') or 'UNAVAILABLE'),
                    ('Object ID', item.get('id') or 'UNAVAILABLE'),
                    ('Move type', item.get('type') or 'UNAVAILABLE'),
                    ('Digest', item.get('digest') or 'UNAVAILABLE'),
                    ('Previous transaction', item.get('transaction') or 'UNAVAILABLE'),
                    ('Execution', item.get('execution_status') or 'UNAVAILABLE'),
                    ('Object checkpoint', 'UNAVAILABLE' if item.get('checkpoint') is None
                     or item.get('checkpoint') == '' else item.get('checkpoint')),
                    ('Capability', capability),
                    ('Custodian', item.get('custodian') or 'NOT APPLICABLE')]
        evidence.extend((f'Capability {index}', identifier)
                        for index, identifier in enumerate(cap_ids, 1) if len(cap_ids) > 1)
        safe_evidence = [(clean(label), clean(value)) for label, value in evidence]
        for text in field_rows(safe_evidence, width,
                               label_width=min(22, max(10, width // 3))):
            lines.append((text, 'foreground'))
        if item.get('timestamp'):
            lines.append((_pair('Last object change', timestamp(item['timestamp']), width), 'foreground'))
        if item.get('reason'):
            lines.append((clip('UNAVAILABLE — ' + clean(item['reason']), width), 'yellow'))
        if item.get('last_known'):
            known = item['last_known']
            lines.append((_pair('LAST KNOWN version', known.get('version') or '—', width), 'yellow'))
            lines.append((_pair('LAST KNOWN observed', timestamp(known.get('seen_at')), width), 'yellow'))
        facts = item.get('facts') if isinstance(item.get('facts'), dict) else {}
        for label, value in facts.items():
            for text in field_rows([(clean(label), clean(value))], width,
                                   label_width=min(22, max(10, width // 3))):
                lines.append((text, 'foreground'))
        lines.append((_pair('Retrieved', timestamp(snapshot.get('retrieved_at')), width), 'secondary'))
        lines.append((_pair('Chain', short(snapshot.get('chain_id') or 'UNAVAILABLE', 22), width), 'secondary'))
        lines.append((_pair('Source', clean(snapshot.get('endpoint') or 'UNAVAILABLE'), width), 'secondary'))
    return lines


def activity(snapshot, width, now):
    lines = [(title('activity', width), 'accent'),
             ('Local evidence history · newest first', 'secondary'),
             ('─' * width, 'muted'), ('', 'foreground')]
    events = snapshot.get('activity') if isinstance(snapshot.get('activity'), list) else []
    if not events:
        lines.extend([('No locally observed changes yet.', 'secondary'),
                      ('History begins after the first complete poll.', 'foreground')])
    for event in events[:100]:
        if not isinstance(event, dict):
            continue
        event_role = {'observed': 'accent', 'derived': 'yellow'}.get(
            clean(event.get('role')).lower(), clean(event.get('role') or 'foreground'))
        evidence_role = clean(event.get('role') or 'unknown').upper()
        prefix = f"{timestamp(event.get('timestamp'))}  [{evidence_role}] "
        lines.append((prefix + clip(clean(event.get('title') or 'Observed change'),
                                    max(1, width - cell_width(prefix))),
                      event_role))
        if event.get('detail'):
            lines.append((clip('       ' + clean(event['detail']), width), 'secondary'))
        lines.append(('', 'foreground'))
    return lines


def dashboard(snapshot, width, page=1, now=None):
    now = time.time() if now is None else now
    width = max(0, min(int(width), 4096))
    renderer = {1: overview, 2: infrastructure, 3: activity}.get(page, overview)
    return [(clip(text, width), role if role in read_palette() else 'foreground')
            for text, role in renderer(snapshot if isinstance(snapshot, dict) else {}, width, now)]


def _screen(screen, get_snapshot, palette_path, on_refresh):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.timeout(500)
    offset, page = 0, 1
    previous_palette = None
    style = {}
    snapshot = {'connected': False}
    next_update = 0
    while True:
        tick = time.monotonic()
        if tick >= next_update:
            try:
                snapshot = get_snapshot()
            except (OSError, ValueError) as error:
                snapshot = dict(snapshot, connected=False, error=f'Collector unavailable: {error}')
            next_update = tick + 1
        palette = read_palette(palette_path)
        if palette != previous_palette:
            style = styles(palette)
            screen.bkgd(' ', style['foreground'])
            previous_palette = palette
        height, columns = screen.getmaxyx()
        left, width = layout(columns)
        rows = dashboard(snapshot, width, page)
        fixed = min(4, max(0, height - 1))
        available = max(0, height - fixed - 1)
        body = rows[4:]
        offset = min(offset, max(0, len(body) - available))
        screen.erase()
        for row, (line, role) in enumerate(rows[:fixed]):
            if row == 0:
                draw_bar(screen, row, line, style['header'], columns,
                         prefix_style=style['header_prefix'])
            else:
                put(screen, row, line, style.get(role, style['foreground']), columns, left=left)
        for row, (line, role) in enumerate(body[offset:offset + available], fixed):
            put(screen, row, line, style.get(role, style['foreground']), columns, left=left)
        if height:
            footer = ('1 overview · 2 infrastructure · 3 activity · ↑↓ · r · q' if width >= 49
                      else '1 overview · 2 infra · 3 changes · ↑↓ · q' if width >= 42
                      else '1 overview · 2 infra · 3 changes · q')
            draw_bar(screen, height - 1, footer, style['footer'], columns)
        screen.refresh()
        key = screen.getch()
        if key in (ord('q'), ord('Q'), 27):
            return
        if key in (ord('1'), ord('2'), ord('3')):
            page, offset = key - ord('0'), 0
        elif key in (curses.KEY_DOWN, ord('j')):
            offset += 1
        elif key in (curses.KEY_UP, ord('k')):
            offset = max(0, offset - 1)
        elif key == curses.KEY_NPAGE:
            offset += max(1, available)
        elif key == curses.KEY_PPAGE:
            offset = max(0, offset - max(1, available))
        elif key in (ord('r'), ord('R')):
            if on_refresh is not None:
                on_refresh()
            next_update = 0


def run(get_snapshot, palette_path=None, on_refresh=None):
    curses.wrapper(_screen, get_snapshot, palette_path, on_refresh)
