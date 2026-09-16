"""Native terminal caret, while Textual retains input and selection handling."""
import sys
from rich.style import Style
from textual.widgets import Input

SHOW_CARET = '\x1b[6 q\x1b]12;#f2ebe0\x1b\\\x1b[?25h'
RESTORE_CARET = '\x1b[0 q\x1b]112\x1b\\'


class AtlasInput(Input):
    def get_component_rich_style(self, *names, partial=False, default=None):
        if names == ('input--cursor',):
            return Style.null()  # Native caret replaces the painted character cell.
        return super().get_component_rich_style(*names, partial=partial, default=default)

    def on_focus(self):
        self.cursor_blink = False
        self.call_after_refresh(self.show_caret)

    def show_caret(self):
        if self.has_focus and not self.app.is_headless and self.app._driver:
            self.app.cursor_position = self.cursor_screen_offset
            self.app._driver.write(SHOW_CARET)

    def on_blur(self):
        if not self.app.is_headless and self.app._driver:
            self.app._driver.write('\x1b[?25l')


def restore_caret():
    if sys.__stdout__.isatty():
        sys.__stdout__.write(RESTORE_CARET)
        sys.__stdout__.flush()
