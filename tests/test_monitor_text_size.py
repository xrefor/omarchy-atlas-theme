"""Production monitor processes with fake commands and controlled font updates."""
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


@unittest.skipIf(os.environ.get('ATLAS_TEST_PORTABLE') == '1',
                 'native monitor test is excluded from portable checks')
@unittest.skipUnless(QUICKSHELL and (SHELL / 'Ui/Panel.qml').is_file(),
                     'native monitor test requires Quickshell and Omarchy shell')
class MonitorTextSizeTests(unittest.TestCase):
    def test_latest_request_survives_slow_commands_and_failure_resets_preview(self):
        with tempfile.TemporaryDirectory(prefix='atlas-text-size-') as temporary:
            path = Path(temporary)
            for name in ('bin', 'home', 'runtime'):
                (path / name).mkdir(mode=0o700)
            shutil.copytree(SHELL / 'Ui', path / 'Ui')
            (path / 'Commons').symlink_to(SHELL / 'Commons', target_is_directory=True)
            shutil.copytree(ROOT / 'components/desktop/plugins/atlas.monitor', path / 'Monitor')
            # Offscreen Quickshell has no popup-window backend. Keep the real
            # controls and process logic, stubbing only their enclosing window.
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
            (path / 'font-size').write_text('12')
            fake = '''import json, os, pathlib, sys, time
root = pathlib.Path(os.environ['ATLAS_TEXT_SIZE_FIXTURE'])
name = pathlib.Path(sys.argv[0]).name
if name == 'omarchy-display-text-size':
    size = int(sys.argv[1])
    with (root / 'calls.jsonl').open('a') as output:
        output.write(json.dumps(size) + '\\n')
    time.sleep(.2)
    if size == 20:
        sys.exit(7)
    (root / 'font-size').write_text(str(size))
elif name == 'omarchy-monitor-state':
    print('unavailable\\n\\n\\n\\n\\n\\n1\\n[]')
elif name == 'omarchy':
    print('{"enabled":false,"temperature":6500}')
elif name == 'hyprctl':
    print('{"int":0}')
elif name == 'fc-match':
    print('monospace')
else:
    sys.exit(91)
'''
            for name in ('omarchy-display-text-size', 'omarchy-monitor-state',
                         'omarchy', 'hyprctl', 'fc-match'):
                command = path / 'bin' / name
                command.write_text('#!' + sys.executable + '\n' + fake)
                command.chmod(0o755)
            (path / 'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons
import "Monitor" as Monitor

ShellRoot {
  id: test
  property int phase: 0
  property int ticks: 0
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
  FileView {
    path: Quickshell.env("ATLAS_TEXT_SIZE_FIXTURE") + "/font-size"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: Style.fontBaseSize = parseInt(text(), 10)
  }
  Timer {
    interval: 30
    repeat: true
    running: true
    onTriggered: {
      if (++test.ticks > 180) {
        console.error("TEXT_SIZE_FAILED phase=" + test.phase + " actual=" + Style.font.baseSize
          + " preview=" + monitor.displayedTextPx())
        Qt.quit()
        return
      }
      if (test.phase === 0) {
        test.phase = 1
        monitor.adjustTextSize(1)  // 12 -> 14 starts a slow command.
        monitor.adjustTextSize(1)  // 16 queues behind it.
        monitor.adjustTextSize(-3) // 11 replaces the queued request.
      } else if (test.phase === 1 && Style.font.baseSize === 11
                 && monitor.textSizePreviewIndex === -1) {
        test.phase = 2
        monitor.setTextSize(11) // Same size: no font-change signal will clear it.
      } else if (test.phase === 2 && monitor.textSizePreviewIndex === -1) {
        test.phase = 3
        monitor.setTextSize(20) // A failed final command must restore actual size.
      } else if (test.phase === 3 && monitor.textSizePreviewIndex === -1) {
        if (monitor.displayedTextPx() !== 11) {
          console.error("TEXT_SIZE_FAILED failure left a stale preview")
          Qt.quit()
          return
        }
        test.phase = 4
        monitor.setTextSize(20) // Failure must still drain a newer queued choice.
        monitor.setTextSize(9)
        monitor.setTextSize(10)
      } else if (test.phase === 4 && Style.font.baseSize === 10
                 && monitor.textSizePreviewIndex === -1) {
        console.log("TEXT_SIZE_PASSED")
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
                # The fixture cannot invoke commands that touch the live desktop.
                'PATH': str(path / 'bin'), 'ATLAS_TEXT_SIZE_FIXTURE': str(path),
            })
            env.pop('WAYLAND_DISPLAY', None)
            env.pop('DISPLAY', None)
            result = subprocess.run([QUICKSHELL, '--no-color', '-p', str(path)], env=env,
                                    capture_output=True, text=True, timeout=15)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('TEXT_SIZE_PASSED', output)
            self.assertNotIn('TypeError:', output)
            self.assertNotIn('ReferenceError:', output)
            calls = [json.loads(line) for line in (path / 'calls.jsonl').read_text().splitlines()]
            self.assertEqual(calls, [14, 11, 11, 20, 20, 10])


if __name__ == '__main__':
    unittest.main()
