from __future__ import annotations
import asyncio
from datetime import datetime
from pathlib import Path
import re
import shlex
import subprocess
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Button, DataTable, Footer, Input, Label, RichLog, Static, TabbedContent, TabPane
from . import backend
from .input import AtlasInput


class FilePicker(ModalScreen[Path | None]):
    BINDINGS = [('escape', 'dismiss(None)', 'Cancel')]

    def compose(self):
        with Vertical(id='picker'):
            yield Label('SELECT APK', classes='section-title')
            yield AtlasInput(str(Path.home()), id='folder', placeholder='Folder path · Enter to browse')
            yield DataTable(id='file-tree', cursor_type='row')
            yield Button('Cancel', id='close-picker')

    def on_mount(self):
        self.query_one(DataTable).add_columns('Name', 'Type')
        self.load_folder(Path.home())

    def load_folder(self, path):
        try:
            path = path.expanduser().resolve()
            entries = sorted((p for p in path.iterdir() if not p.name.startswith('.')
                              and (p.is_dir() or p.suffix.lower() == '.apk')),
                             key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError as exc:
            self.notify(str(exc), severity='error')
            return
        self.paths = [path.parent] + entries
        self.query_one('#folder', Input).value = str(path)
        table = self.query_one(DataTable)
        table.clear()
        table.add_row('..', 'Parent folder')
        for p in entries:
            table.add_row(Text(p.name), 'Folder' if p.is_dir() else 'APK')

    @on(Input.Submitted, '#folder')
    def change_folder(self, event):
        self.load_folder(Path(event.value))

    @on(DataTable.RowSelected)
    def choose(self, event):
        path = self.paths[event.cursor_row]
        if path.is_dir(): self.load_folder(path)
        else: self.dismiss(path)

    @on(Button.Pressed, '#close-picker')
    def close_picker(self):
        self.dismiss(None)


class NutcrackerApp(App):
    TITLE = 'ATLAS / NUTCRACKER'
    CSS_PATH = 'atlas.tcss'
    BINDINGS = [Binding('ctrl+q', 'leave', 'Quit', priority=True),
                Binding('ctrl+o', 'browse', 'Choose APK'),
                Binding('ctrl+r', 'refresh', 'Refresh'),
                Binding('ctrl+x', 'stop', 'Stop analysis')]

    def __init__(self):
        super().__init__()
        self.register_theme(Theme(name='atlas', primary='#ff5a12', secondary='#a69b8c',
            accent='#ff5a12', foreground='#d6cfc4', background='#100e0c', surface='#100e0c',
            panel='#1c1814', success='#8a9a4a', warning='#f0a202', error='#e84528', dark=True))
        self.theme = 'atlas'
        self.runner = backend.ProcessRunner()
        self.busy = False
        self.analysis_task = None
        self.report_paths = []
        self.pending_output = ''

    def compose(self) -> ComposeResult:
        yield Static('[bold #ff5a12]A T L A S[/]  [#6e675c]/[/]  [bold #f2ebe0]NUTCRACKER[/]', id='brand')
        yield Static('ANDROID APPLICATION ANALYSIS', id='subtitle')
        with TabbedContent(initial='analyze-tab'):
            with TabPane('Analyze', id='analyze-tab'):
                yield Static('LOCAL APK', classes='section-title')
                with Horizontal(id='file-row'):
                    yield AtlasInput(placeholder='/path/to/application.apk', id='apk')
                    yield Button('Browse', id='browse')
                yield Static('Static analysis · protections, manifest, source, secrets and PDF / JSON reports', id='scope')
                with Horizontal(classes='actions'):
                    yield Button('Analyze', id='analyze', variant='primary')
                    yield Button('Stop', id='stop', disabled=True)
                    yield Static('Ready', id='status', markup=False)
                yield RichLog(id='output', wrap=True, highlight=False, markup=False, max_lines=5000)
            with TabPane('Reports', id='reports-tab'):
                yield Static('SAVED REPORTS', classes='section-title')
                yield DataTable(id='reports', cursor_type='row', zebra_stripes=False)
                with Horizontal(classes='actions'):
                    yield Button('Open selected', id='open-report')
                    yield Button('Refresh', id='refresh-reports')
                    yield Static('Enter opens a report in its default viewer.', classes='hint')
            with TabPane('Tools', id='tools-tab'):
                yield Static('ANALYSIS TOOLCHAIN', classes='section-title')
                yield DataTable(id='tools', cursor_type='row')
                with VerticalScroll(id='details'):
                    yield Static('Built-in regex SAST and secret scanning are enabled. Optional tools extend the native CLI.', markup=False)
                    yield Static(str(backend.CONFIG), id='config-path', markup=False)
                    yield Static(str(backend.DATA), id='data-path', markup=False)
                    yield Static('CLI: nutcracker --help  ·  nutcracker analyze app.apk --static-only\nNative command options remain available, including scan, queue, schedule and launch.', markup=False)
        yield Footer()

    def on_mount(self):
        self.query_one('#output', RichLog).border_title = 'OUTPUT'
        self.query_one('#reports', DataTable).add_columns('Report', 'Type', 'Updated', 'Size')
        self.query_one('#tools', DataTable).add_columns('Tool', 'Use', 'Status')
        self.action_refresh()
        self.query_one('#output', RichLog).write(Text('Choose an APK to begin. Results appear here and are saved under Reports.', style='#a69b8c'))
        self.query_one('#apk', Input).focus()

    def action_refresh(self):
        table = self.query_one('#tools', DataTable)
        table.clear()
        for name, purpose, path in backend.tool_status():
            table.add_row(name, purpose, Text('Ready' if path else 'Not installed', style='#8a9a4a' if path else '#6e675c'))
        table = self.query_one('#reports', DataTable)
        table.clear()
        try:
            self.report_paths = backend.reports()
            for idx, path in enumerate(self.report_paths):
                st = path.stat()
                table.add_row(Text(f'{path.parent.name}/{path.name}'), path.suffix[1:].upper(),
                    datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'), f'{st.st_size / 1024:.1f} KB', key=str(idx))
            table.border_title = f'{len(self.report_paths)} reports'
        except (OSError, ValueError) as exc:
            self.notify(str(exc), severity='error')

    @on(Button.Pressed, '#browse')
    def action_browse(self):
        if not self.busy:
            self.push_screen(FilePicker(), self.set_apk)

    def set_apk(self, path):
        if path:
            self.query_one('#apk', Input).value = str(path)
            self.query_one('#apk', Input).focus()

    @on(Button.Pressed, '#analyze')
    @on(Input.Submitted, '#apk')
    def start_analysis(self):
        if self.busy: return
        try:
            command = backend.analysis_command(self.query_one('#apk', Input).value)
            missing = [name for name, _, path in backend.tool_status() if name in ('jadx', 'java') and not path]
            if missing: raise ValueError('Missing required tools: ' + ', '.join(missing))
        except (ValueError, OSError) as exc:
            self.notify(str(exc), severity='error')
            return
        self.runner = backend.ProcessRunner()
        self.busy = True
        self.query_one('#analyze', Button).disabled = True
        self.query_one('#browse', Button).disabled = True
        self.query_one('#apk', Input).disabled = True
        self.query_one('#stop', Button).disabled = False
        self.query_one('#status', Static).update('Analyzing…')
        self.query_one('#output', RichLog).clear()
        self.pending_output = ''
        self.analysis_task = self.run_worker(self.run_analysis(command), exit_on_error=False)

    def show_output(self, text):
        self.pending_output += text.replace('\r', '\n')
        lines = self.pending_output.split('\n')
        self.pending_output = lines.pop()
        # Bound a child process emitting an unusually long line.
        if len(self.pending_output) > 16384:
            lines.append(self.pending_output[:16384])
            self.pending_output = ''
        log = self.query_one('#output', RichLog)
        for line in lines:
            # No markup or terminal controls from filenames / analysis output.
            line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line)
            line = ''.join(c for c in line if c == '\t' or ord(c) >= 32 and ord(c) != 127)
            log.write(Text(line))

    async def run_analysis(self, command):
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        logfile = backend.DATA / 'logs' / f'{stamp}.log'
        try:
            code = await self.runner.run(command, self.show_output, logfile=logfile)
            self.show_output('\n')
            result = 'Stopped' if self.runner.cancelled else 'Finished · inspect output and reports' if code == 0 else f'Failed · exit {code}'
            self.query_one('#status', Static).update(result)
            self.query_one('#output', RichLog).write(Text(f'\n{result}\nLog: {logfile}', style='#a69b8c'))
        except asyncio.CancelledError:
            await self.runner.stop()
            raise
        except Exception as exc:
            self.query_one('#status', Static).update('Failed')
            self.show_output(f'\n{exc}\n')
        finally:
            self.busy = False
            self.query_one('#analyze', Button).disabled = False
            self.query_one('#browse', Button).disabled = False
            self.query_one('#apk', Input).disabled = False
            self.query_one('#stop', Button).disabled = True
            self.action_refresh()

    @on(Button.Pressed, '#stop')
    async def action_stop(self):
        if self.busy:
            self.query_one('#status', Static).update('Stopping…')
            await self.runner.stop()

    async def action_leave(self):
        if self.busy:
            await self.runner.stop()
            if self.analysis_task:
                await self.analysis_task.wait()
        self.exit()

    @on(Button.Pressed, '#refresh-reports')
    def refresh_reports(self):
        self.action_refresh()

    @on(Button.Pressed, '#open-report')
    @on(DataTable.RowSelected, '#reports')
    def open_report(self):
        table = self.query_one('#reports', DataTable)
        if not self.report_paths:
            self.notify('No reports yet. Analyze an APK first.')
            return
        idx = table.cursor_row
        if 0 <= idx < len(self.report_paths):
            self.open_file(self.report_paths[idx])

    @work(exclusive=True, group='open-report')
    async def open_file(self, path):
        try:
            proc = await asyncio.create_subprocess_exec('xdg-open', str(path),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            if await proc.wait(): self.notify('No viewer available for this report.', severity='error')
        except OSError as exc:
            self.notify(str(exc), severity='error')
