"""Tracked text must not disclose personal filesystem or email identifiers."""
from pathlib import Path
import re
import subprocess
import unittest


ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
    'Linux home path':re.compile(r'/home/[A-Za-z0-9._-]+'),
    'macOS home path':re.compile(r'/Users/[A-Za-z0-9._-]+'),
    'email address':re.compile(r'(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])'),
}


class PrivacyTests(unittest.TestCase):
    def test_tracked_text_has_no_personal_identifiers(self):
        output=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z'])
        findings=[]
        for raw in output.split(b'\0'):
            if not raw: continue
            rel=Path(raw.decode());path=ROOT/rel
            if not path.is_file() or path.is_symlink(): continue
            try: text=path.read_text()
            except UnicodeDecodeError: continue
            for label,pattern in PATTERNS.items():
                if pattern.search(text): findings.append(f'{rel}: {label}')
        self.assertEqual(findings,[],'\n'.join(findings))


if __name__=='__main__': unittest.main()
