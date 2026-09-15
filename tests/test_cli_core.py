import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "components/cli"
sys.path.insert(0, str(CLI))

from atlas_cli.palette import FALLBACK, load_theme, want_color
from atlas_cli.runner import colorize, passthrough

ANSI = re.compile(r"\x1b\[[0-9;]*m")


class CoreWrapperTests(unittest.TestCase):
    def test_colorization_preserves_text(self):
        samples = {
            "nmap": "Nmap scan report for localhost (127.0.0.1)\n22/tcp open ssh\n",
            "ping": "64 bytes from ::1: icmp_seq=1 ttl=64 time=0.031 ms\n0% packet loss\n",
            "ip": "2: eth0: <UP,LOWER_UP>\n    inet6 fe80::1234/64 scope link\n",
            "ss": "LISTEN 0 128 [::]:22 [::]:*\n",
            "dig": ";; ANSWER SECTION:\nexample.test. 60 IN A 192.0.2.1\n",
            "shodan": "IP 192.0.2.2\nPorts: 22/tcp open\n",
            "tcpdump": "12:34:56.100000 IP 192.0.2.1.443 > 198.51.100.2.50000\n",
        }
        for app, text in samples.items():
            with self.subTest(app=app):
                rendered = colorize(app, text, FALLBACK)
                self.assertIn("\x1b[", rendered)
                self.assertEqual(ANSI.sub("", rendered), text)

    def test_structured_and_binary_modes_bypass(self):
        cases = [
            ("nmap", ["-oX", "-"]),
            ("nmap", ["-oA/tmp/result"]),
            ("nmap", ["--resume=result.nmap"]),
            ("ip", ["-json", "addr"]),
            ("ip", ["-j", "-p", "addr"]),
            ("ss", ["-tnD", "-"]),
            ("dig", ["+sh"]),
            ("dig", ["+yaml"]),
            ("ping", ["-nf"]),
            ("shodan", ["host", "192.0.2.1", "--json"]),
            ("shodan", ["download", "output", "query"]),
            ("shodan", ["init"]),
        ]
        for app, args in cases:
            with self.subTest(app=app, args=args):
                self.assertTrue(passthrough(app, args))
        self.assertFalse(passthrough("nmap", ["-sV", "127.0.0.1"]))
        self.assertFalse(passthrough("ip", ["-br", "addr"]))

    def test_no_color_has_precedence(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(want_color("always"))

    def test_palette_reads_only_valid_literal_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            theme = home / ".local/state/omarchy/current/theme/colors.toml"
            theme.parent.mkdir(parents=True)
            theme.write_text('accent = "#123456"\nforeground = "#abcdef"\n', encoding="utf-8")
            self.assertEqual(load_theme(home)["accent"], "#123456")
            theme.write_text('accent = "rgb(ffffff)"\n', encoding="utf-8")
            self.assertEqual(load_theme(home)["accent"], FALLBACK["accent"])
            theme.write_text('accent = "unterminated\n', encoding="utf-8")
            self.assertEqual(load_theme(home), FALLBACK)

    def test_streams_bytes_and_exit_status(self):
        child = (
            "from atlas_cli.runner import run_colored; "
            "from atlas_cli.palette import FALLBACK; import os,sys; "
            "cmd=[sys.executable,'-c',\"import os; os.write(1,b'22/tcp open ssh\\\\n\\\\xff'); "
            "os.write(2,b'error\\\\n'); raise SystemExit(7)\"]; "
            "raise SystemExit(run_colored(cmd,'nmap',FALLBACK))"
        )
        env = dict(os.environ, PYTHONPATH=str(CLI), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-c", child], capture_output=True, env=env)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(result.stderr, b"error\n")
        self.assertEqual(re.sub(rb"\x1b\[[0-9;]*m", b"", result.stdout), b"22/tcp open ssh\n\xff")

    def test_signal_is_forwarded(self):
        child = (
            "from atlas_cli.runner import run_colored; "
            "from atlas_cli.palette import FALLBACK; "
            "run_colored(['/usr/bin/sleep','30'],'nmap',FALLBACK)"
        )
        env = dict(os.environ, PYTHONPATH=str(CLI), PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.Popen([sys.executable, "-c", child], env=env)
        try:
            time.sleep(0.2)
            process.terminate()
            self.assertEqual(process.wait(timeout=3), -signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


if __name__ == "__main__":
    unittest.main()
