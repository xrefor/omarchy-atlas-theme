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
        if (ROOT/'.git').exists():
            output=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z'])
            files=[Path(raw.decode()) for raw in output.split(b'\0') if raw]
        else:
            files=[path.relative_to(ROOT) for path in ROOT.rglob('*')
                   if path.is_file() and not path.is_symlink()
                   and not any(part in ('dist','__pycache__','.pytest_cache')
                               for part in path.relative_to(ROOT).parts)]
        findings=[]
        for rel in files:
            path=ROOT/rel
            if not path.is_file() or path.is_symlink(): continue
            try: text=path.read_text()
            except UnicodeDecodeError: continue
            for label,pattern in PATTERNS.items():
                if pattern.search(text): findings.append(f'{rel}: {label}')
        self.assertEqual(findings,[],'\n'.join(findings))


if __name__=='__main__': unittest.main()
