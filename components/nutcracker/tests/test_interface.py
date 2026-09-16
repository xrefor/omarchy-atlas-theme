"""Offline frontend regressions; no APK installation or device action."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas_nutcracker import backend
from atlas_nutcracker.app import NutcrackerApp, FilePicker
from atlas_nutcracker import input as atlas_input
from textual.widgets import Button, Input, TabbedContent, DataTable


def fixture_apk(path):
    with zipfile.ZipFile(path, 'w') as bundle:
        bundle.writestr('AndroidManifest.xml', '<manifest/>')
    return path


def test_native_thin_ivory_caret_and_terminal_restore(monkeypatch):
    from atlas_nutcracker import __main__ as cli
    assert atlas_input.SHOW_CARET == '\x1b[6 q\x1b]12;#f2ebe0\x1b\\\x1b[?25h'
    assert atlas_input.RESTORE_CARET == '\x1b[0 q\x1b]112\x1b\\'
    restored = []
    monkeypatch.setattr(cli.sys, 'argv', ['nutcracker', 'tui'])
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli.sys, 'stdout', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli.backend, 'environment', lambda: {})
    monkeypatch.setattr(cli.backend, 'setup', lambda: None)
    monkeypatch.setattr(NutcrackerApp, 'run', lambda self: None)
    monkeypatch.setattr(atlas_input, 'restore_caret', lambda: restored.append(True))
    assert cli.main() == 0
    assert restored == [True]


def test_command_preserves_filename_as_one_argument(tmp_path):
    path = fixture_apk(tmp_path / 'app ; $(touch PWNED) [test].apk')
    command = backend.analysis_command(path)
    assert command[command.index('analyze') + 1] == str(path)
    assert '--static-only' in command
    assert not (tmp_path / 'PWNED').exists()


def test_reject_invalid_apk(tmp_path):
    with pytest.raises(ValueError): backend.apk_path(str(tmp_path / 'missing.apk'))
    path = tmp_path / 'bad.apk'; path.write_text('not a zip')
    with pytest.raises(ValueError): backend.apk_path(str(path))
    with zipfile.ZipFile(path, 'w') as bundle: bundle.writestr('other', '')
    with pytest.raises(ValueError): backend.apk_path(str(path))


def test_stream_and_exit_status(tmp_path):
    async def check():
        runner = backend.ProcessRunner(); output = []
        code = await runner.run(
            [sys.executable, '-c', "print('hello');raise SystemExit(7)"],
            output.append, cwd=tmp_path, logfile=tmp_path / 'run.log')
        assert code == 7
        assert 'hello' in ''.join(output)
        assert (tmp_path / 'run.log').stat().st_mode & 0o777 == 0o600
    asyncio.run(check())


def test_cancel_entire_process_group(tmp_path):
    async def check():
        runner = backend.ProcessRunner(); ready = asyncio.Event(); output = []
        script = ("import subprocess,sys,time; "
                  "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                  "print(p.pid,flush=True);time.sleep(30)")
        def receive(text): output.append(text); ready.set()
        task = asyncio.create_task(runner.run([sys.executable, '-c', script], receive, cwd=tmp_path))
        await asyncio.wait_for(ready.wait(), 5)
        pid = int(''.join(output).strip())
        await runner.stop(); await asyncio.wait_for(task, 5)
        assert runner.cancelled
        proc = Path(f'/proc/{pid}/stat')
        assert not proc.exists() or proc.read_text().split()[2] == 'Z'
    asyncio.run(check())


def test_tui_navigation_and_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'CONFIG', tmp_path / 'config.yaml')
    monkeypatch.setattr(backend, 'DATA', tmp_path)
    async def check():
        app = NutcrackerApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            assert app.query_one('#tools', DataTable).row_count == 8
            await pilot.click('#analyze'); assert not app.busy
            await pilot.click('#browse'); assert isinstance(app.screen, FilePicker)
            await pilot.press('escape')
            app.query_one(TabbedContent).active = 'reports-tab'; await pilot.pause()
            assert app.query_one('#reports', DataTable).row_count == 0
            await pilot.resize_terminal(80, 24); await pilot.pause()
            app.query_one(TabbedContent).active = 'analyze-tab'; await pilot.pause()
            assert app.query_one('#analyze', Button).region.y < 24
    asyncio.run(check())


def test_tui_run_and_reenable_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA', tmp_path)
    monkeypatch.setattr(backend, 'CONFIG', tmp_path / 'config.yaml')
    (tmp_path / 'logs').mkdir()
    monkeypatch.setattr(backend, 'analysis_command',
                        lambda value: [sys.executable, '-c', "print('[red]literal output[/red]')"])
    monkeypatch.setattr(backend, 'tool_status',
                        lambda: [('jadx', 'decompile', '/jadx'), ('java', 'runtime', '/java')])
    async def check():
        app = NutcrackerApp()
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click('#analyze'); await app.workers.wait_for_complete()
            assert not app.busy
            assert not app.query_one('#analyze', Button).disabled
            assert app.query_one('#stop', Button).disabled
            assert len(list((tmp_path / 'logs').glob('*.log'))) == 1
    asyncio.run(check())


def test_reports_config_validation(tmp_path, monkeypatch):
    config = tmp_path / 'config.yaml'
    monkeypatch.setattr(backend, 'CONFIG', config)
    monkeypatch.setattr(backend, 'DATA', tmp_path)
    for content in ('', 'reports:\n  output_dir: null\n'):
        config.write_text(content); assert backend.reports() == []
    for content in ('[one, two]', 'reports: [one]', 'broken: ['):
        config.write_text(content)
        with pytest.raises(ValueError): backend.reports()


def test_log_strips_split_escape_sequences(tmp_path):
    async def check():
        runner = backend.ProcessRunner(); output = []
        code = ("import sys,time;sys.stdout.write('before\\x1b]52;c;');sys.stdout.flush();"
                "time.sleep(.1);sys.stdout.write('payload\\x07after\\x1b[31m red\\x1b[0m');sys.stdout.flush()")
        await runner.run([sys.executable, '-c', code], output.append,
                         cwd=tmp_path, logfile=tmp_path / 'clean.log')
        assert (tmp_path / 'clean.log').read_text() == 'beforeafter red'
        assert ''.join(output) == 'beforeafter red'
    asyncio.run(check())


def test_native_resolves_input_then_changes_to_workspace(tmp_path, monkeypatch):
    from atlas_nutcracker import native
    import nutcracker_core.orchestrator as orchestrator
    data = tmp_path / 'workspace'; data.mkdir()
    config = tmp_path / 'config.yaml'; config.write_text('features:\n  report_pdf: false\n')
    apk = fixture_apk(tmp_path / 'relative.apk')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(native, 'DATA', data); monkeypatch.setattr(native, 'CONFIG', config)
    seen = []
    monkeypatch.setattr(orchestrator, '_run_analysis',
                        lambda path, *args, **kwargs: seen.append((path, Path.cwd())))
    with pytest.raises(SystemExit) as exit_info:
        native.run(['analyze', 'relative.apk', '--static-only'])
    assert exit_info.value.code == 0
    assert seen == [(apk, data)]
    assert Path.cwd() == tmp_path


def test_unterminated_escape_does_not_hide_following_lines():
    cleaner = backend.OutputCleaner()
    assert cleaner.feed('header\x1b]bad') == 'header'
    assert cleaner.feed('\nreal findings\rnext') == '\nreal findings\nnext'


def test_stop_requested_before_worker_starts(tmp_path):
    async def check():
        runner = backend.ProcessRunner(); await runner.stop()
        code = await asyncio.wait_for(runner.run(
            [sys.executable, '-c', 'import time;time.sleep(30)'], lambda text: None, cwd=tmp_path), 3)
        assert code != 0
        assert runner.cancelled
    asyncio.run(check())
