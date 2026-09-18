"""Native QML process regression; popup geometry is stubbed for offscreen Qt."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL = Path('/usr/share/omarchy/shell')
QUICKSHELL = shutil.which('quickshell')


@unittest.skipUnless(QUICKSHELL and (SHELL / 'Ui/Panel.qml').is_file(),
                     'native monitor test requires Quickshell and Omarchy shell')
class MonitorNightlightTests(unittest.TestCase):
    def test_native_toggle_keyboard_and_status_with_restricted_shell(self):
        with tempfile.TemporaryDirectory(prefix='atlas-nightlight-') as temp:
            path = Path(temp)
            for name in ('bin', 'home', 'runtime'):
                (path / name).mkdir(mode=0o700)
            shutil.copytree(SHELL / 'Ui', path / 'Ui')
            (path / 'Commons').symlink_to(SHELL / 'Commons', target_is_directory=True)
            shutil.copytree(ROOT / 'components/desktop/plugins/atlas.monitor', path / 'Monitor')
            # Quickshell has no PanelWindow backend on Qt's offscreen platform.
            # Keep production panel logic/controls, replacing only its popup window.
            (path / 'Ui/KeyboardPanel.qml').write_text('''import QtQuick
Item {
  property var anchorItem
  property var owner
  property var bar
  property bool open: false
  property var focusTarget
  property int contentWidth: 0
  property int contentHeight: 0
  width: contentWidth
  height: contentHeight
  function fittedContentWidth(value) { return value }
  function fittedContentHeight(value, maximum) { return Math.min(value, maximum) }
}
''')
            (path / 'status.json').write_text('{"enabled":false,"temperature":6000}')
            fake = '''import json, os, pathlib, sys
root = pathlib.Path(os.environ['ATLAS_NIGHTLIGHT_FIXTURE'])
args = sys.argv[1:]
name = pathlib.Path(sys.argv[0]).name
if name in ('omarchy', 'omarchy-shell'):
    with (root / 'calls.jsonl').open('a') as output:
        output.write(json.dumps([name] + args) + '\\n')
if name == 'omarchy' and args == ['toggle', 'nightlight', '--status']:
    pending = root / 'pending.json'
    if pending.exists():
        target = json.loads(pending.read_text())
        target['reads'] -= 1
        if target['reads'] == 0:
            enabled = target['enabled']
            (root / 'status.json').write_text(json.dumps({'enabled': enabled, 'temperature': 4000 if enabled else 6500}))
            pending.unlink()
        else:
            pending.write_text(json.dumps(target))
    print((root / 'status.json').read_text())
elif name == 'omarchy-shell' and args in (['nightlight', 'enable'], ['nightlight', 'disable']):
    if json.loads((root / 'status.json').read_text()).get('failCommand'):
        sys.exit(7)
    enabled = args[1] == 'enable'
    # Match IPC: return before the daemon applies temperature; readback must retry.
    (root / 'pending.json').write_text(json.dumps({'enabled': enabled, 'reads': 3}))
elif name == 'fixture-status':
    (root / 'status.json').write_text(args[0])
elif name == 'omarchy-monitor-state':
    print('unavailable\\n\\n\\n\\n\\n\\n1\\n[]')
elif name == 'hyprctl':
    print('{"int": 0}')
elif name == 'fc-match':
    print('monospace')
else:
    sys.exit(91)
'''
            for name in ('omarchy', 'omarchy-shell', 'fixture-status',
                         'omarchy-monitor-state', 'hyprctl', 'fc-match'):
                script = path / 'bin' / name
                script.write_text('#!' + sys.executable + '\n' + fake)
                script.chmod(0o755)
            (path / 'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import "Monitor" as Monitor

ShellRoot {
  id: test
  property int phase: 0
  property int ticks: 0
  function setStatus(text) {
    fixture.command = ["fixture-status", text]
    fixture.running = true
  }
  QtObject {
    id: restrictedShell
    function firstPartyServiceFor(id) { return null }
    function summon(id, payload) { return false }
  }
  PluginBarApi {
    id: restrictedBar
    pluginId: "atlas.monitor"
    moduleName: "atlas.monitor"
    shell: restrictedShell
    fontFamily: "monospace"
    position: "top"
    barSize: 24
  }
  Monitor.Panel { id: monitor; bar: restrictedBar }
  Process {
    id: fixture
    onExited: {
      monitor.refreshNightlight()
      monitor.refreshNightlight() // Queue a refresh behind an in-flight read.
    }
  }
  Timer {
    interval: 40
    repeat: true
    running: true
    onTriggered: {
      if (++test.ticks > 250) {
        console.error("NIGHTLIGHT_FAILED phase=" + test.phase + " enabled=" + monitor.nightlightEnabled
          + " known=" + monitor.nightlightStatusKnown + " error=" + monitor.nightlightError)
        Qt.quit()
      }
      if (fixture.running || monitor.nightlightPending) return
      if (test.phase === 0 && monitor.nightlightStatusKnown && !monitor.nightlightEnabled) {
        test.phase = 1
        monitor.toggleNightlight()
        monitor.toggleNightlight() // An in-flight click must not submit a duplicate.
      } else if (test.phase === 1 && monitor.nightlightEnabled) {
        test.phase = 2
        monitor.focusSection = "nightlight"
        monitor.cursorActive = true
        monitor.activateCursor()
      } else if (test.phase === 2 && monitor.nightlightStatusKnown && !monitor.nightlightEnabled) {
        test.phase = 3
        test.setStatus('{"enabled":true,"temperature":4500}')
      } else if (test.phase === 3 && monitor.nightlightEnabled) {
        test.phase = 4
        test.setStatus('{"enabled":false,"temperature":null}')
      } else if (test.phase === 4 && monitor.nightlightStatusKnown && !monitor.nightlightEnabled) {
        test.phase = 5
        test.setStatus('{"enabled":true,"temperature":4000}')
      } else if (test.phase === 5 && monitor.nightlightEnabled) {
        test.phase = 6
        test.setStatus('not json')
      } else if (test.phase === 6 && !monitor.nightlightStatusKnown && monitor.nightlightEnabled) {
        test.phase = 7
        test.setStatus('{"enabled":false,"temperature":6500,"failCommand":true}')
      } else if (test.phase === 7 && monitor.nightlightStatusKnown && !monitor.nightlightEnabled) {
        test.phase = 8
        monitor.toggleNightlight()
      } else if (test.phase === 8 && monitor.nightlightError && !monitor.nightlightEnabled) {
        console.log("NIGHTLIGHT_PASSED")
        Qt.quit()
      }
    }
  }
}
''')
            env = os.environ.copy()
            env.update({
                'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
                'QT_QPA_PLATFORMTHEME': 'basic', 'QT_STYLE_OVERRIDE': 'Fusion',
                'HOME': str(path / 'home'), 'XDG_CONFIG_HOME': str(path / 'home/.config'),
                'XDG_RUNTIME_DIR': str(path / 'runtime'),
                # No host commands are reachable from the panel under test.
                'PATH': str(path / 'bin'), 'ATLAS_NIGHTLIGHT_FIXTURE': str(path),
            })
            env.pop('WAYLAND_DISPLAY', None)
            env.pop('DISPLAY', None)
            result = subprocess.run([QUICKSHELL, '--no-color', '-p', str(path)], env=env,
                                    capture_output=True, text=True, timeout=20)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('NIGHTLIGHT_PASSED', output)
            self.assertNotIn('TypeError:', output)
            self.assertNotIn('ReferenceError:', output)
            calls = [json.loads(line) for line in (path / 'calls.jsonl').read_text().splitlines()]
            self.assertEqual([call for call in calls if call[0] == 'omarchy-shell'],
                             [['omarchy-shell', 'nightlight', 'enable'],
                              ['omarchy-shell', 'nightlight', 'disable'],
                              ['omarchy-shell', 'nightlight', 'enable']])
            self.assertGreaterEqual(calls.count(['omarchy', 'toggle', 'nightlight', '--status']), 12)


if __name__ == '__main__':
    unittest.main()
