"""ATLAS HUD skin reference for kimocoder wifite2 2.9.9-beta.

This module changes presentation only. It must be imported and ``apply()``
called before Wifite starts. The bundle does not install a privileged launcher.
"""

from __future__ import annotations

import os

from atlas_cli.palette import RESET, fg, load_theme

_palette = load_theme(home=os.environ.get("ATLAS_THEME_HOME"))
ACCENT = fg(_palette, "accent")
FG = fg(_palette, "foreground")
MUTED = fg(_palette, "dark_foreground")
DIM_LINE = fg(_palette, "muted")
WARN = fg(_palette, "yellow")
ALERT = fg(_palette, "red")
WPA3 = fg(_palette, "magenta")
COOL = fg(_palette, "blue")
CYAN = fg(_palette, "cyan")
BRIGHT = fg(_palette, "bright_foreground")


def _enc_label() -> str:
    from wifite.config import Configuration

    selected = list(getattr(Configuration, "encryption_filter", None) or [])
    known = {"WEP", "WPA", "WPA3", "OWE", "WPS"}
    if not selected or known.issubset(set(selected)):
        return "ALL"
    return "/".join(selected)


def _telemetry(iface_count: int | None = None, mode: str | None = None, radio: str | None = None) -> None:
    from wifite.config import Configuration
    from wifite.util.color import Color

    if iface_count is None:
        iface_count = 1 if getattr(Configuration, "interface", None) else 0
    if mode is None or radio is None:
        interface = getattr(Configuration, "interface", None) or ""
        if interface.endswith("mon"):
            mode, radio = "MONITOR", "LIVE"
        else:
            mode, radio = "MANAGED", "STANDBY"
    Color.pl(
        f" {MUTED}IFACE{RESET}{FG}  {ACCENT}{iface_count}{RESET}{FG}"
        f"    {MUTED}RADIO{RESET}{FG}  {radio}"
        f"    {MUTED}MODE{RESET}{FG}  {mode}"
        f"    {MUTED}ENC{RESET}{FG}  {_enc_label()}"
    )
    Color.pl(f" {DIM_LINE}{'─' * 44}{RESET}{FG}")


def apply() -> None:
    """Apply visual monkeypatches without changing Wifite attack logic."""
    from wifite.config import Configuration
    from wifite.tools.airmon import Airmon
    from wifite.util.color import Color
    from wifite.util.scanner import Scanner
    from wifite.wifite import Wifite

    Color.colors = {
        "W": RESET + FG,
        "R": ALERT,
        "G": ACCENT,
        "O": WARN,
        "B": COOL,
        "P": WPA3,
        "C": CYAN,
        "GR": MUTED,
        "D": "\033[2m",
    }
    Color.replacements = {
        "{+}": f" {DIM_LINE}[{ACCENT}▸{DIM_LINE}]{RESET}{FG}",
        "{!}": f" {WARN}[{ALERT}!{WARN}]{RESET}{FG}",
        "{?}": f" {DIM_LINE}[{CYAN}?{DIM_LINE}]{RESET}{FG}",
    }

    original_print = Color.p
    original_printline = Color.pl

    def rewrite(text: str):
        if "Select wireless interface" in text:
            return f" {MUTED}IFACE{RESET}{FG} {ACCENT}▸ {RESET}{FG}"
        if "{C}option:" not in text and "option:{W}" not in text and "option: {O}" not in text:
            return text
        if "all known encryption types" in text or "all specified encrypted" in text:
            return None
        if "targeting" in text and "-encrypted" in text:
            return None
        text = text.replace("{+} {C}option:{W}", f" {MUTED}SET{RESET}{FG} ")
        text = text.replace("{+} {C}option: {O}", f" {MUTED}SET{RESET}{FG} ")
        return text.replace("{+} {C}option:{O}", f" {MUTED}SET{RESET}{FG} ")

    def print_same_line(text):
        rendered = rewrite(text)
        if rendered is not None:
            original_print(rendered)

    def print_line(text):
        rendered = rewrite(text)
        if rendered is None:
            Color.last_sameline_length = 0
        else:
            original_printline(rendered)

    Color.p = staticmethod(print_same_line)
    Color.pl = staticmethod(print_line)

    def print_banner() -> None:
        version = getattr(Configuration, "version", "")
        Color.pl("")
        Color.pl(f" {ACCENT}ATLAS{MUTED}  ·  RF CONSOLE{RESET}{FG}")
        Color.pl(f" {BRIGHT}WIFITE{MUTED}  {version}{RESET}{FG}")
        Color.pl(f" {DIM_LINE}{'─' * 44}{RESET}{FG}")
        Color.pl(f" {MUTED}spectrum audit  ·  derv82 / kimocoder{RESET}{FG}")
        Color.pl("")

    Wifite.print_banner = staticmethod(print_banner)

    def print_menu(self):
        from wifite.tools.iw import Iw

        try:
            monitor_interfaces = Iw.get_interfaces(mode="monitor")
        except Exception:
            monitor_interfaces = []
        names = [interface.interface for interface in self.interfaces]
        if any(name in monitor_interfaces or name.endswith("mon") for name in names):
            mode, radio = "MONITOR", "LIVE"
        else:
            mode, radio = "MANAGED", "STANDBY"
        Color.pl("")
        _telemetry(len(self.interfaces), mode, radio)
        width = max(10, max((len(interface.interface) for interface in self.interfaces), default=10))
        for index, interface in enumerate(self.interfaces, start=1):
            driver = (interface.driver or "").strip()
            chipset = (getattr(interface, "chipset", None) or "").strip()
            extra = driver or chipset
            if len(extra) > 22:
                extra = extra[:20] + ".."
            Color.pl(
                f" {ACCENT}{index:02d}{RESET}{FG}  {interface.interface.ljust(width)}"
                f"  {MUTED}·{RESET}{FG}  {extra}"
            )

    Airmon.print_menu = print_menu

    original_clear = Scanner.clr_scr

    @staticmethod
    def clear_screen():
        original_clear()
        print_banner()
        interface = getattr(Configuration, "interface", None) or ""
        try:
            from wifite.tools.iw import Iw

            monitor_interfaces = Iw.get_interfaces(mode="monitor")
        except Exception:
            monitor_interfaces = []
        if interface in monitor_interfaces or interface.endswith("mon"):
            _telemetry(1, "MONITOR", "LIVE")
        else:
            _telemetry(1 if interface else 0, "MANAGED", "STANDBY")

    Scanner.clr_scr = clear_screen
