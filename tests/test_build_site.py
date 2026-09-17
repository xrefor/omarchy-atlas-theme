"""Responsive media and wallpaper selection must survive site staging."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('atlas_site', ROOT / 'tools/build_site.py')
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


class SiteAssetsTests(unittest.TestCase):
    def test_stages_responsive_candidates_and_dynamic_wallpaper_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text(
                '<img src="small.webp" srcset="small.webp 160w, medium.webp 320w">'
                '<button data-full="original.png" data-preview="hero.webp" '
                'data-srcset="hero.webp 1080w, large.webp 1672w"></button>')
            assets = {'small.webp', 'medium.webp', 'hero.webp', 'large.webp', 'original.png'}
            for name in assets:
                (root / name).write_bytes(name.encode())
            output = root / 'dist/site'
            with patch.object(site, 'ROOT', root), patch.object(site, 'OUTPUT', output), contextlib.redirect_stdout(io.StringIO()):
                site.main()
            self.assertEqual({p.name for p in output.iterdir()}, assets | {'index.html', '.nojekyll'})
            for name in assets:
                self.assertEqual((output / name).read_bytes(), (root / name).read_bytes())

    def test_missing_responsive_candidate_fails_before_replacing_staged_site(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<img src="small.webp" srcset="missing.webp 640w">')
            (root / 'small.webp').touch()
            output = root / 'dist/site'
            output.mkdir(parents=True)
            sentinel = output / 'previous.html'
            sentinel.write_text('previous build')
            with patch.object(site, 'ROOT', root), patch.object(site, 'OUTPUT', output):
                with self.assertRaisesRegex(ValueError, 'Missing or linked site asset: missing.webp'):
                    site.main()
            self.assertEqual(sentinel.read_text(), 'previous build')

    def test_responsive_and_dynamic_paths_keep_validation_guards(self):
        for html in (
            '<img srcset="../outside.webp 640w">',
            '<button data-full="%2e%2e/outside.png"></button>',
            '<button data-preview="/outside.webp"></button>',
            '<button data-srcset="../outside.webp 1080w"></button>',
            '<img srcset="a.webp 640w, b.webp 640w">',
            '<img srcset="a.webp 0w">',
            '<img srcset="a.webp">',
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                site.PageAssets().feed(html)


if __name__ == '__main__':
    unittest.main()
