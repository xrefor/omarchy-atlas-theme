"""Palette-aware, read-only local ports and services panel."""
import curses
from datetime import datetime
import queue
import re
import signal
import threading
import time
import unicodedata

from atlas_panel import (clip, draw_panel_frame, field_rows, layout, read_layout_style,
                         read_palette, styles, title, card_rows)


_ANSI = re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)|'
                   r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]')
_SCOPE = {'loopback': 'LOOPBACK', 'wildcard': 'ALL INTERFACES',
          'interface': 'SPECIFIC ADDRESS', 'unknown': 'UNKNOWN BIND'}


def clean(value):
    value = _ANSI.sub('', str('' if value is None else value)[:4096])
    return ' '.join(''.join(char for char in value
                            if not unicodedata.category(char).startswith('C')
                            or char in '\n\r\t').split())


def _owners(listener):
    return [owner for owner in listener.get('owners', []) if isinstance(owner, dict)]


def _matches(listener, query):
    values = [listener.get(key) for key in ('protocol', 'address', 'port', 'endpoint', 'service', 'uid', 'account')]
    for owner in _owners(listener):
        values.extend(owner.get(key) for key in ('name', 'pid', 'service'))
    return query.casefold() in ' '.join(clean(value) for value in values).casefold()


def _listener_card(listener, width, elevated):
    """One socket card with complete, separately readable ownership fields."""
    inner = max(0, width - 4) if width >= 12 else width
    protocol = clean(listener.get('protocol')).upper() or '?'
    port = clean(listener.get('port')) or '?'
    rows = [(f'{protocol} · {port}', 'bright_foreground'), ('', 'foreground')]

    def fields(items, role='secondary'):
        rows.extend((line, role) for line in field_rows(items, inner))

    fields([('BIND', clean(listener.get('address')) or
             clean(listener.get('endpoint')) or 'UNKNOWN ADDRESS')], 'foreground')
    fields([('SCOPE', _SCOPE.get(listener.get('scope'), 'UNKNOWN BIND'))])
    rows.append(('', 'foreground'))
    owners = _owners(listener)
    if owners:
        for owner in owners:
            fields([('PROCESS', clean(owner.get('name')) or 'Unknown process'),
                    ('PID', clean(owner.get('pid')) or 'unavailable')], 'foreground')
    else:
        fields([('', 'Process/PID unavailable' if elevated else
                 'Process/PID restricted or unavailable')])
    account = clean(listener.get('account'))
    uid = listener.get('uid')
    fields([('ACCOUNT', account or 'Unavailable')])
    if isinstance(uid, int) and not isinstance(uid, bool):
        fields([('UID', uid)])
    services = list(dict.fromkeys(clean(service) for service in
                    [listener.get('service')] + [owner.get('service') for owner in owners]
                    if service))
    for service in services:
        fields([('SERVICE', service)], 'accent')
    return card_rows(rows, width)


def dashboard(snapshot, width, page=1, query='', *, style='classic'):
    width = max(0, min(int(width), 4096))
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    query = clean(query)
    protocol = {1: 'tcp', 2: 'udp'}.get(page)
    label = protocol.upper() if protocol else 'ALL'
    listeners = [item for item in snapshot.get('listeners', [])
                 if isinstance(item, dict) and (protocol is None or item.get('protocol') == protocol)]
    filtered = [item for item in listeners if _matches(item, query)]
    available = snapshot.get('available', False)
    partial = bool(snapshot.get('partial') or snapshot.get('errors') or snapshot.get('omitted'))
    status = f'{len(filtered)} shown' if available else 'UNAVAILABLE'
    if snapshot.get('authenticating'):
        status = 'AUTHENTICATING'
    elif snapshot.get('elevated'):
        status = 'ADMIN LIVE'
    elif snapshot.get('loading'):
        status = 'REFRESHING' if available else 'LOADING'
    if available and partial:
        status += ' · PARTIAL'
    if style == 'framed' and not snapshot.get('elevated') and not snapshot.get('authenticating'):
        status = 'USER · ' + status
    rows = [(title('ports & services', width), 'accent'),
            (f'{label} · {status}', 'secondary'),
            ('─' * width, 'muted'), ('', 'foreground')]
    if snapshot.get('authenticating'):
        rows.append(('Approve the desktop authentication dialog.', 'secondary'))
    if snapshot.get('elevated'):
        try:
            captured = datetime.fromtimestamp(float(snapshot.get('captured_at'))).strftime('%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError, OverflowError, OSError):
            captured = 'UNKNOWN'
        rows.append((f'Updated  {captured}', 'accent'))
        rows.append(('Refreshing · r returns to your account', 'secondary'))
        rows.append((f'{len(filtered)} shown', 'secondary'))
    for notice in snapshot.get('notices', [])[:6]:
        rows.append((clean(notice), 'yellow'))
    if query:
        rows.append((f'Filter: {query}', 'accent'))
        rows.append(('', 'foreground'))
    if not available:
        rows.append(('Reading local sockets…' if snapshot.get('loading') else
                     'Socket data unavailable.', 'secondary' if snapshot.get('loading') else 'yellow'))
    else:
        rows.append(('LOCAL SOCKETS', 'secondary'))
        rows.append(('Bind addresses · reachability not tested', 'muted'))
        if partial:
            rows.append(('Collection incomplete · see details below', 'yellow'))
        if style == 'framed' and filtered:
            if not snapshot.get('elevated') and any(not _owners(item) for item in filtered):
                rows.extend((line, 'secondary') for line in field_rows(
                    [('', 'a · Authenticate for restricted process details')], width))
        if not filtered:
            rows.append(('No matches in collected data.' if partial else
                         'No matching sockets.' if query else
                         'No UDP sockets.' if protocol == 'udp' else
                         'No listening sockets.', 'secondary'))
        for listener in filtered:
            rows.append(('', 'foreground'))
            if style == 'framed':
                rows.extend(_listener_card(listener, width, snapshot.get('elevated', False)))
                continue
            endpoint = clean(listener.get('endpoint') or 'UNKNOWN ADDRESS')
            rows.append((f'{clean(listener.get("protocol")).upper()}  {endpoint}', 'bright_foreground'))
            rows.append((_SCOPE.get(listener.get('scope'), 'UNKNOWN BIND'), 'secondary'))
            uid, account = listener.get('uid'), clean(listener.get('account'))
            if isinstance(uid, int) and not isinstance(uid, bool):
                rows.append((f'Account  {account} · UID {uid}' if account else
                             f'Account  UID {uid}', 'secondary'))
            elif account:
                rows.append((f'Account  {account}', 'secondary'))
            else:
                rows.append(('Account unavailable', 'muted'))
            owners = _owners(listener)
            if not owners:
                rows.append(('Process / PID unavailable' if snapshot.get('elevated') else
                             'Process / PID restricted or unavailable', 'muted'))
                if not snapshot.get('elevated'):
                    rows.append(('a · Authenticate for process details', 'muted'))
            for owner in owners:
                rows.append((f'{clean(owner.get("name") or "Unknown process")} · PID '
                             f'{clean(owner.get("pid") or "unavailable")}', 'foreground'))
            services = list(dict.fromkeys(clean(service) for service in
                            [listener.get('service')] + [owner.get('service') for owner in owners]
                            if service))
            for service in services:
                rows.append((f'Service  {service}', 'accent'))
    omitted = snapshot.get('omitted', 0)
    if isinstance(omitted, int) and omitted > 0:
        rows.append(('', 'foreground'))
        rows.append((f'{omitted} additional sockets omitted', 'yellow'))
    errors = snapshot.get('errors', [])
    if errors:
        rows.extend([('', 'foreground'), ('UNAVAILABLE', 'secondary')])
        rows.extend((clean(error), 'yellow') for error in errors[:6])
    return [(clip(text, width), role) for text, role in rows]


class _Worker:
    """A single cancellable collector, with no accumulation of refresh requests."""

    def __init__(self, collector):
        self.collector = collector
        self.results = queue.Queue()
        self.lock = threading.Lock()
        self.active = False
        self.closed = False
        self.thread = None
        self.epoch = 0

    def request(self):
        with self.lock:
            if self.closed or self.active:
                return
            self.active = True
            self.thread = threading.Thread(target=self._work, args=(self.epoch,), daemon=True)
            self.thread.start()

    def _work(self, epoch):
        try:
            result = self.collector.collect()
        except Exception as error:
            result = {'available': False, 'listeners': [],
                      'errors': [f'Collector unavailable: {clean(error)}'], 'omitted': 0}
        with self.lock:
            if not self.closed and epoch == self.epoch:
                self.results.put(result)
            self.active = False

    def poll(self):
        result = None
        while True:
            try:
                result = self.results.get_nowait()
            except queue.Empty:
                return result

    def invalidate(self):
        """Drop queued results and prevent an in-flight older result resurfacing."""
        with self.lock:
            self.epoch += 1
            self.poll()

    def wait_idle(self, timeout=3):
        """Quiesce live collection before starting graphical authorization."""
        with self.lock:
            thread = self.thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    def close(self):
        with self.lock:
            self.closed = True
        self.collector.cancel()


def _screen(screen, collector, palette_path, inspect_details=None, stop_admin=None, authenticate_on_open=False):
    worker = _Worker(collector)
    try:
        _screen_loop(screen, worker, palette_path, inspect_details, stop_admin, authenticate_on_open)
    finally:
        worker.close()


def _inspect_details(screen, inspect_details):
    """Let the desktop handle authentication; keep the terminal panel visible."""
    try:
        result = inspect_details()
        if not isinstance(result, dict):
            raise ValueError('Invalid socket snapshot')
        return result
    except KeyboardInterrupt:
        return {'available': False, 'errors': ['Administrator details cancelled.']}
    except Exception as error:
        return {'available': False, 'errors': [f'Administrator details unavailable: {clean(error)}']}
    finally:
        # Always restore curses, including cancellation and terminal signals.
        for restore in (lambda: curses.curs_set(0),
                        lambda: screen.keypad(True), lambda: screen.timeout(100),
                        lambda: screen.clearok(True)):
            try:
                restore()
            except curses.error:
                pass


def _screen_loop(screen, worker, palette_path, inspect_details=None, stop_admin=None, authenticate_on_open=False):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    screen.timeout(100)
    offset, page, next_update = 0, 1, 0
    snapshot, previous_palette, style = {}, None, {}
    query, draft, editing = '', '', False
    normal_snapshot, notices = {}, []
    opening = authenticate_on_open and inspect_details is not None
    while True:
        tick = time.monotonic()
        if not opening and tick >= next_update:
            worker.request()
            next_update = tick + 2
        result = worker.poll()
        if result is not None:
            if snapshot.get('elevated') and not result.get('elevated'):
                offset = 0
            snapshot = result
            notices = list(dict.fromkeys(notices + [clean(note) for note in result.get('notices', [])]))
            if not result.get('elevated'):
                normal_snapshot = dict(result, notices=[])
        palette = read_palette(palette_path)
        if palette != previous_palette:
            style = styles(palette)
            screen.bkgd(' ', style['foreground'])
            previous_palette = palette
        _, columns = screen.getmaxyx()
        _, width = layout(columns)
        presentation = read_layout_style()
        rows = dashboard(dict(snapshot, loading=worker.active,
                              notices=notices), width, page,
                         draft if editing else query, style=presentation)
        if presentation == 'framed':
            if editing:
                footer = ['/ ' + draft + '▏', 'Enter apply · Esc cancel · Ctrl+U clear']
            else:
                refresh = 'r user' if snapshot.get('elevated') else 'r refresh'
                admin = ' · a auth' if inspect_details is not None else ''
                footer = ['1 TCP · 2 UDP · 3 All · / filter',
                          f'↑↓{admin} · {refresh} · q close']
        elif editing:
            footer = '/ ' + draft + '▏ · Enter apply · Esc cancel'
        else:
            refresh = 'r user' if snapshot.get('elevated') else 'r'
            admin = ' · a auth' if inspect_details is not None else ''
            footer = f'1/2/3 · / filter{admin} · {refresh} · q'
            if width >= 55:
                footer = f'1 TCP · 2 UDP · 3 All · / filter{admin} · {refresh} · q'
        offset, available, body_length, width = draw_panel_frame(
            screen, rows, style, offset, footer)
        screen.refresh()
        if opening:
            opening = False
            key = 'a'
        else:
            try:
                key = screen.get_wch()
            except curses.error:
                continue
        if editing:
            if key in ('\n', '\r', curses.KEY_ENTER):
                query, editing, offset = draft, False, 0
            elif key == '\x1b':
                editing, offset = False, 0
            elif key in ('\b', '\x7f', curses.KEY_BACKSPACE):
                draft, offset = draft[:-1], 0
            elif key == '\x15':
                draft, offset = '', 0
            elif isinstance(key, str) and key.isprintable() and len(draft) < 256:
                draft, offset = draft + key, 0
            continue
        if key in ('q', 'Q', '\x1b'):
            return
        if key in ('1', '2', '3'):
            page, offset = int(key), 0
        elif key == '/':
            draft, editing, offset = query, True, 0
        elif key in (curses.KEY_DOWN, 'j'):
            offset += 1
        elif key in (curses.KEY_UP, 'k'):
            offset = max(0, offset - 1)
        elif key == curses.KEY_NPAGE:
            offset += max(1, available)
        elif key == curses.KEY_PPAGE:
            offset = max(0, offset - max(1, available))
        elif key == curses.KEY_HOME:
            offset = 0
        elif key == curses.KEY_END:
            offset = max(0, body_length - available)
        elif key in ('r', 'R'):
            worker.invalidate()
            if stop_admin is not None:
                stop_admin()
            worker.invalidate()
            snapshot, notices, next_update, offset = normal_snapshot, [], 0, 0
        elif key in ('a', 'A') and inspect_details is not None:
            notices, offset = [], 0
            if not worker.wait_idle():
                notices = ['Live collection is still finishing.', 'Press a to authenticate again.']
                continue
            result = worker.poll()
            if result is not None:
                snapshot = result
                if not result.get('elevated'):
                    normal_snapshot = dict(result, notices=[])
            rows = dashboard(dict(snapshot, authenticating=True), width, page, query)
            draw_panel_frame(screen, rows, style, 0, 'Waiting for desktop authentication…')
            screen.refresh()
            details = _inspect_details(screen, inspect_details)
            offset = 0
            if details.get('available') and details.get('elevated'):
                snapshot, notices = details, []
            else:
                worker.invalidate()
                if stop_admin is not None:
                    stop_admin()
                worker.invalidate()
                snapshot = normal_snapshot
                notices = details.get('errors') or ['Administrator details unavailable.']
            next_update = 0


def run(collector, palette_path=None, inspect_details=None, stop_admin=None, authenticate_on_open=False):
    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    previous = {}
    try:
        for signum in (signal.SIGHUP, signal.SIGTERM):
            previous[signum] = signal.signal(signum, terminate)
        curses.wrapper(_screen, collector, palette_path, inspect_details, stop_admin, authenticate_on_open)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
