"""Optional package selection never installs without a terminal and consent."""
import sys
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'lib'))
from atlas import optional


class OptionalTests(unittest.TestCase):
    def test_noninteractive_never_prompts_or_installs(self):
        with patch.object(optional.sys.stdin, 'isatty', return_value=False), patch('builtins.input') as prompt, patch.object(optional.subprocess, 'run') as run:
            optional.install()
        prompt.assert_not_called()
        run.assert_not_called()

    def test_defaults_decline(self):
        with patch.object(optional.sys.stdin, 'isatty', return_value=True), patch.object(optional, 'available', return_value=False), patch('builtins.input', return_value=''), patch.object(optional.subprocess, 'run') as run:
            optional.install()
        run.assert_not_called()

    def test_existing_apps_skipped(self):
        with patch.object(optional.sys.stdin, 'isatty', return_value=True), patch.object(optional, 'available', return_value=True), patch('builtins.input') as prompt, patch.object(optional.subprocess, 'run') as run:
            optional.install()
        prompt.assert_not_called()
        run.assert_not_called()

    def test_nym_opt_in_uses_aur_without_starting_service(self):
        with patch.object(optional.sys.stdin, 'isatty', return_value=True), patch.object(optional, 'available', return_value=False), patch('builtins.input', side_effect=['']*5+['yes']), patch.object(optional.subprocess, 'run') as run:
            optional.install()
        run.assert_called_once_with(['omarchy', 'pkg', 'aur', 'add', 'nym-vpnd-bin', 'nym-vpn-app-bin'], check=True)

    def test_package_failure_allows_remaining_choices(self):
        with patch.object(optional.sys.stdin, 'isatty', return_value=True), patch.object(optional, 'available', return_value=False), patch('builtins.input', side_effect=['yes']*2+['']*4), patch.object(optional.subprocess, 'run', side_effect=[subprocess.CalledProcessError(1, 'omarchy'), None]) as run:
            optional.install()
        self.assertEqual(run.call_count, 2)
