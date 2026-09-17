"""Codex shell integration keeps argument, override and terminal behavior intact."""
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / 'components/apps/shell.bash'
BASH = shutil.which('bash')
ARGUMENTS = ['--profile', 'two words', '', 'line one\nline two', '$(touch unwanted)', '*?[a]', '--x=a=b']


@unittest.skipUnless(BASH, 'Bash is required for shell integration checks')
class AgentsShellTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'commands with spaces'
        self.bin.mkdir()
        self.calls = self.root / 'calls.jsonl'
        fixture_home = self.root / 'home'
        atlas_config = fixture_home / '.config/atlas'
        atlas_config.mkdir(parents=True)
        (atlas_config / 'revision').write_text('fixture\n')
        (atlas_config / 'terminal-colors.bash').write_text('')
        (atlas_config / 'palette.bash').write_text('')
        self.env = {
            'HOME': str(fixture_home), 'PATH': str(self.bin), 'TERM': 'xterm-256color',
            'TMUX': 'isolated-fixture,1,0', 'ATLAS_TEST_CALLS': str(self.calls),
            'ATLAS_TEST_SHELL': str(SHELL), 'ATLAS_TEST_EXIT': '37',
            'ATLAS_TEST_CUSTOM': str(self.bin / 'custom-codex'),
        }
        for name in ('codex', 'atlas-agents', 'custom-codex'):
            path = self.bin / name
            path.write_text(f'#!{sys.executable}\n' + '''
import json
import os
from pathlib import Path
import sys
with open(os.environ['ATLAS_TEST_CALLS'], 'a') as output:
    output.write(json.dumps(sys.argv) + '\\n')
if Path(sys.argv[0]).name == 'atlas-agents':
    assert sys.argv[1:3] == ['launch', '--']
    os.execv(sys.argv[3], sys.argv[3:])
raise SystemExit(int(os.environ['ATLAS_TEST_EXIT']))
''')
            path.chmod(0o755)

    def run_shell(self, invocation='codex "$@"', before='', terminal=False, env=None):
        script = before + '\nsource "$ATLAS_TEST_SHELL"\n' + invocation
        arguments = [BASH, '--noprofile', '--norc']
        if terminal:
            arguments.append('-i')
        arguments += ['-c', script, 'agents-shell-test', *ARGUMENTS]
        environment = dict(self.env)
        environment.update(env or {})
        if terminal:
            master, slave = pty.openpty()
            try:
                with subprocess.Popen(arguments, env=environment, cwd=self.root,
                                      stdin=slave, stdout=slave, stderr=subprocess.PIPE) as process:
                    try:
                        _, errors = process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                        raise
                    code = process.returncode
            finally:
                os.close(slave)
                os.close(master)
        else:
            process = subprocess.run(arguments, env=environment, cwd=self.root,
                                     input=b'', stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            code, errors = process.returncode, process.stderr
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        self.assertFalse((self.root / 'unwanted').exists(), 'An argument was evaluated as shell code')
        return code, calls, errors.decode(errors='replace')

    def assert_direct(self, result):
        code, calls, errors = result
        self.assertEqual(code, 37, errors)
        self.assertEqual(calls, [[str(self.bin / 'codex'), *ARGUMENTS]])

    def test_noninteractive_pipe_preserves_exact_arguments_and_exit(self):
        self.assert_direct(self.run_shell())

    def test_terminal_session_launches_observer_with_exact_binary_and_arguments(self):
        code, calls, errors = self.run_shell(terminal=True)
        self.assertEqual(code, 37, errors)
        self.assertEqual(calls, [
            [str(self.bin / 'atlas-agents'), 'launch', '--', str(self.bin / 'codex'), *ARGUMENTS],
            [str(self.bin / 'codex'), *ARGUMENTS],
        ])

    def test_command_codex_is_explicit_bypass_even_in_terminal(self):
        self.assert_direct(self.run_shell('command codex "$@"', terminal=True))

    def test_automatic_panel_opt_out_preserves_direct_terminal_launch(self):
        self.assert_direct(self.run_shell(terminal=True, env={'ATLAS_AGENTS_AUTO': '0'}))

    def test_terminal_outside_tmux_preserves_direct_launch(self):
        self.assert_direct(self.run_shell(terminal=True, env={'TMUX': ''}))

    def test_existing_custom_function_is_preserved(self):
        code, calls, errors = self.run_shell(
            before='codex() { command "$ATLAS_TEST_CUSTOM" "$@"; }', terminal=True)
        self.assertEqual(code, 37, errors)
        self.assertEqual(calls, [[str(self.bin / 'custom-codex'), *ARGUMENTS]])

    def test_existing_custom_alias_is_preserved(self):
        code, calls, errors = self.run_shell(
            before='shopt -s expand_aliases\nalias codex=\'command "$ATLAS_TEST_CUSTOM"\'', terminal=True)
        self.assertEqual(code, 37, errors)
        self.assertEqual(calls, [[str(self.bin / 'custom-codex'), *ARGUMENTS]])

    def test_unavailable_launcher_leaves_codex_unwrapped(self):
        (self.bin / 'atlas-agents').unlink()
        self.assert_direct(self.run_shell('declare -F codex >/dev/null && exit 98\ncodex "$@"', terminal=True))

    def test_sourcing_twice_does_not_nest_launchers(self):
        code, calls, errors = self.run_shell('source "$ATLAS_TEST_SHELL"\ncodex "$@"', terminal=True)
        self.assertEqual(code, 37, errors)
        self.assertEqual([Path(call[0]).name for call in calls], ['atlas-agents', 'codex'])


if __name__ == '__main__':
    unittest.main()
