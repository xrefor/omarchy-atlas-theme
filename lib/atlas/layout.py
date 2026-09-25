"""Reversible terminal layout preference, separate from pane lifecycle."""
import json
import shutil
import subprocess

from . import state

PREFERENCE = '.config/atlas/layout.json'
TMUX_PREFERENCE = '.config/atlas/layout.conf'
PRESETS = ('classic', 'framed')


def current(home):
    item = state.snapshot(state.target(home, PREFERENCE))
    if item['kind'] == 'absent':
        return 'classic'
    if item['kind'] != 'file':
        raise ValueError('Terminal layout preference must be a regular file')
    try:
        value = json.loads(state.text_value(item))
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid terminal layout preference') from error
    if not isinstance(value, dict) or value.get('style') not in PRESETS:
        raise ValueError('Terminal layout must be classic or framed')
    return value['style']


def values(preset):
    if preset not in PRESETS:
        raise ValueError('Choose classic or framed')
    return {
        PREFERENCE: state.value(json.dumps({'style': preset}) + '\n'),
        TMUX_PREFERENCE: state.value('set -g @atlas-layout ' + preset + '\n'),
    }


def server_available():
    if not shutil.which('tmux'):
        return False
    result = subprocess.run(['tmux', 'list-sessions'], capture_output=True,
                            text=True, timeout=10)
    if result.returncode == 0:
        return True
    if any(message in result.stderr.lower() for message in
           ('no server running', 'no such file or directory')):
        return False
    raise ValueError('Cannot refresh tmux: ' + result.stderr.strip())


def refresh(home, preset):
    # Set explicitly so rolling back an originally absent preference also
    # clears the framed option. Source appearance only, never pane bindings.
    subprocess.run(['tmux', 'set-option', '-g', '@atlas-layout', preset],
                   check=True, capture_output=True, text=True, timeout=10)
    subprocess.run(['tmux', 'source-file', str(home / '.config/atlas/tmux.conf')],
                   check=True, capture_output=True, text=True, timeout=10)


def select(home, preset, live=True):
    desired = values(preset)
    active = live and server_available()
    with state.lock(home):
        previous = current(home)
        before = {rel: state.snapshot(state.target(home, rel)) for rel in desired}
        if any(item['kind'] not in ('absent', 'file') for item in before.values()):
            raise ValueError('Terminal layout preferences must be regular files')
        state.transact(home, desired)
        try:
            if active:
                refresh(home, preset)
        except (ValueError, OSError, subprocess.SubprocessError):
            state.transact(home, before)
            refresh(home, previous)
            raise
    return preset
