"""Choose the lock-screen appearance using the ATLAS restoration journal."""
import argparse
from pathlib import Path
import sys

if __package__:
    from . import state
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from atlas import state

PREFERENCE = '.config/atlas/lock-style'
STYLES = ('classic', 'terminal')


def current(home):
    item = state.snapshot(state.target(home, PREFERENCE))
    if item['kind'] == 'absent':
        return 'classic'
    if item['kind'] != 'file':
        raise ValueError('Lock-style preference must be a regular file')
    style = state.text_value(item).strip()
    if style not in STYLES:
        raise ValueError('Lock style must be classic or terminal')
    return style


def select(home, style):
    if style not in (*STYLES, 'toggle'):
        raise ValueError('Choose classic, terminal or toggle')
    with state.lock(home):
        before = current(home)
        selected = ('terminal' if before == 'classic' else 'classic') if style == 'toggle' else style
        state.transact(home, {PREFERENCE: state.value(selected+'\n')})
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='toggle', choices=[*STYLES, 'toggle', 'current', 'is'])
    parser.add_argument('style', nargs='?', choices=STYLES)
    parser.add_argument('--home', type=Path, default=Path.home())
    args = parser.parse_args()
    if (args.action == 'is') != (args.style is not None):
        parser.error('Use is STYLE, or a single action such as terminal')
    try:
        home = args.home.resolve()
        if args.action == 'is': return int(current(home) != args.style)
        if args.action == 'current': print(current(home)); return 0
        print('ATLAS lock screen: ' + select(home, args.action))
        return 0
    except (ValueError, OSError) as error:
        print(f'ATLAS: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
