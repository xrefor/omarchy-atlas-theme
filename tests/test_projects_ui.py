"""Projects panel rendering and ATLAS layout invariants."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
from atlas_panel import cell_width
from atlas_projects import ui


SNAPSHOT = {
    'path': '/work/project/subdir', 'is_git': True, 'repo_root': '/work/project',
    'repo_name': 'project', 'branch': 'main', 'detached': False,
    'head': 'a' * 40, 'upstream': 'origin/main', 'ahead': 2, 'behind': 1,
    'counts': {'staged': 1, 'unstaged': 1, 'untracked': 1},
    'changes': [
        {'path': 'staged.txt', 'status': 'A.', 'staged': True,
         'unstaged': False, 'untracked': False},
        {'path': 'modified.txt', 'status': '.M', 'staged': False,
         'unstaged': True, 'untracked': False},
        {'path': 'new file.txt', 'status': '??', 'staged': False,
         'unstaged': False, 'untracked': True},
    ],
    'changes_total': 3, 'changes_omitted': 0,
    'commits': [{'hash': 'a' * 40, 'short_hash': 'aaaaaaa', 'timestamp': 1_700_000_000,
                 'subject': 'Keep project facts local'}],
    'worktrees': [{'path': '/work/project', 'head': 'a' * 40, 'branch': 'main'},
                  {'path': '/work/review', 'head': 'b' * 40, 'detached': True}],
    'errors': [],
}


class ProjectsUiTests(unittest.TestCase):
    def test_overview_shows_repository_status_and_changed_files(self):
        text = '\n'.join(line for line, _ in ui.dashboard(SNAPSHOT, 55, page=1))
        self.assertIn('// P R O J E C T S', text)
        self.assertIn('Local divergence', text)
        self.assertRegex(text, r'↑ 2\s+↓ 1')
        self.assertIn('staged.txt', text)
        self.assertIn('new file.txt', text)

    def test_history_keeps_projects_header_and_shows_local_sources(self):
        rows = ui.dashboard(SNAPSHOT, 60, page=2)
        text = '\n'.join(line for line, _ in rows)
        self.assertEqual(rows[0][0], '// P R O J E C T S')
        self.assertIn('HISTORY', rows[1][0])
        self.assertIn('/work/review', text)
        self.assertIn('Keep project facts local', text)
        self.assertIn('no fetch or network access', text)

    def test_non_git_state_is_functional_and_explicit(self):
        text = '\n'.join(line for line, _ in ui.dashboard(
            {'path': '/work/plain', 'repo_name': 'plain', 'is_git': False, 'errors': []},
            48, page=1))
        self.assertIn('NO GIT REPOSITORY', text)
        self.assertIn('/work/plain', text)

    def test_every_page_is_bounded_at_sidebar_and_narrow_widths(self):
        dirty = dict(SNAPSHOT, repo_name='\x1b[31mproject\x00')
        for page in (1, 2):
            for width in (1, 8, 24, 43, 55, 60, 100):
                with self.subTest(page=page, width=width):
                    rows = ui.dashboard(dirty, width, page=page)
                    self.assertTrue(all(cell_width(line) <= width for line, _ in rows))
                    self.assertNotIn('\x1b', '\n'.join(line for line, _ in rows))
                    self.assertNotIn('\x00', '\n'.join(line for line, _ in rows))


if __name__ == '__main__':
    unittest.main()
