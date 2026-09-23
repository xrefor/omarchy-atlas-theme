from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'components/apps'))
import atlas_panel
from atlas_projects import ui as projects_ui


class PanelSuiteStyleTests(unittest.TestCase):
    def test_local_panels_share_the_pinned_header_contract(self):
        panels = (
            ('git status', projects_ui, (1, 2)),
        )
        for name, module, pages in panels:
            self.assertIs(module.draw_panel_frame, atlas_panel.draw_panel_frame)
            for width in (48, 60):
                for page in pages:
                    with self.subTest(panel=name, width=width, page=page):
                        rows = module.dashboard({}, width, page)
                        self.assertEqual(rows[0], (atlas_panel.title(name, width), 'accent'))
                        self.assertEqual(rows[2], ('─' * width, 'muted'))
                        self.assertEqual(rows[3], ('', 'foreground'))


if __name__ == '__main__':
    unittest.main()
