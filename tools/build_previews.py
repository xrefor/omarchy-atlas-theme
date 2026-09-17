#!/usr/bin/env python3
"""Regenerate committed showcase previews from the original wallpapers."""
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (160, 320, 640, 1080, 2160)


def main():
    output = ROOT / 'docs/media/previews'
    output.mkdir(parents=True, exist_ok=True)
    count = total = 0
    for source in sorted((ROOT / 'backgrounds').glob('*.png')):
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            # Keep native resolution as the largest candidate for smaller art.
            for width in sorted({min(width, image.width) for width in WIDTHS}):
                height = round(image.height * width / image.width)
                preview = image.resize((width, height), Image.Resampling.LANCZOS)
                target = output / f'{source.stem}-{width}.webp'
                preview.save(target, 'WEBP', quality=85, method=6)
                total += target.stat().st_size
                count += 1
    print(f'Generated {count} WebP previews ({total:,} bytes); original wallpapers unchanged.')


if __name__ == '__main__':
    main()
