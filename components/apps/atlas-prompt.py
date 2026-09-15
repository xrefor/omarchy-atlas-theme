#!/usr/bin/env python3
"""Small, read-only information modules for the ATLAS Starship prompt."""
import os
import sys
import unicodedata
from collections import Counter


def clean(value):
    return ''.join(c for c in value if not unicodedata.category(c).startswith('C'))


mode = sys.argv[1]
if mode == 'header':
    path = os.environ.get('PWD') or os.getcwd()
    home_path = os.path.expanduser('~')
    if path == home_path:
        path = '~'
    elif path.startswith(home_path + '/'):
        path = '~' + path[len(home_path):]
    print('ATLAS :: ' + clean(path))
elif mode == 'separator':
    print('─' * 48)
elif mode == 'counts':
    files = folders = 0
    extensions = Counter()
    try:
        with os.scandir('.') as entries:
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    folders += 1
                else:
                    files += 1
                    extension = os.path.splitext(entry.name)[1].lower()
                    if extension and extension != '.':
                        extensions[extension] += 1
        summary = f'{files} {"file" if files == 1 else "files"} · {folders} {"folder" if folders == 1 else "folders"}'
        top = sorted(extensions.items(), key=lambda item: (-item[1], item[0]))[:3]
        if top:
            summary += ' · ' + '  '.join(f'{clean(ext)[:16]}:{count}' for ext, count in top)
        print(summary)
    except OSError:
        print('contents unavailable')
