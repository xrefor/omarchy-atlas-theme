"""Read the ATLAS palette and prepare colors for a terminal preview."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Swatch:
    name: str
    color: str

    def rgb(self) -> tuple[int, int, int]:
        value = self.color.removeprefix("#")
        red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
        return red, green, blue


def load_palette(path: Path) -> list[Swatch]:
    """Keep the desktop and editor on the same palette."""
    with path.open("rb") as source:
        colors = tomllib.load(source)

    roles = ("background", "foreground", "accent", "green", "blue")
    return [Swatch(name, colors[name]) for name in roles]


if __name__ == "__main__":
    palette = load_palette(Path("colors.toml"))
    for swatch in palette:
        red, green, blue = swatch.rgb()
        sample = f"\033[38;2;{red};{green};{blue}m██\033[0m"
        print(f"{sample}  {swatch.name:<12} {swatch.color}")
