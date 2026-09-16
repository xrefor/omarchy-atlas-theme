#!/usr/bin/env python3
"""Stage the ATLAS showcase and its referenced media for GitHub Pages."""
from html.parser import HTMLParser
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/site"


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()
        self.anchors = set()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                raise ValueError("Duplicate anchor: " + attrs["id"])
            self.ids.add(attrs["id"])
        for attr in ("src", "href", "poster"):
            if attr not in attrs:
                continue
            url = urlsplit(attrs[attr])
            if url.scheme or url.netloc:
                continue
            if url.path:
                path = Path(unquote(url.path))
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Asset must be relative to the site: " + str(path))
                self.paths.add(path)
            elif url.fragment:
                self.anchors.add(unquote(url.fragment))


def main():
    html = (ROOT / "index.html").read_text()
    page = PageAssets()
    page.feed(html)
    missing = page.anchors - page.ids
    if missing:
        raise ValueError("Missing page anchors: " + ", ".join(sorted(missing)))
    files = sorted(page.paths | {Path("index.html")})
    for rel in files:
        source = ROOT / rel
        if not source.is_file() or source.resolve() != source or source.is_symlink():
            raise ValueError("Missing or linked site asset: " + str(rel))
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    for rel in files:
        target = OUTPUT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    (OUTPUT / ".nojekyll").touch()
    size = sum((OUTPUT / rel).stat().st_size for rel in files)
    print(f"Staged {len(files)} site files ({size:,} bytes) in {OUTPUT}")
    print("All local links, images, videos, and page anchors resolve.")


if __name__ == "__main__":
    main()
