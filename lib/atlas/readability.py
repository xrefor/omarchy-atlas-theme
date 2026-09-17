"""Persist the optional Neovim comment preset through the restoration journal."""
from . import state

PREFERENCE = '.config/atlas/neovim-readability'
PRESETS = ('standard', 'readable')


def current(home):
    item = state.snapshot(state.target(home, PREFERENCE))
    if item['kind'] == 'absent':
        return 'standard'
    if item['kind'] != 'file':
        raise ValueError('Neovim readability preference must be a regular file')
    preset = state.text_value(item).strip()
    if preset not in PRESETS:
        raise ValueError('Neovim readability must be standard or readable')
    return preset


def select(home, preset):
    if preset not in PRESETS:
        raise ValueError('Choose standard or readable')
    with state.lock(home):
        current(home)  # Reject malformed files and symlinks before writing.
        state.transact(home, {PREFERENCE: state.value(preset + '\n')})
    return preset
