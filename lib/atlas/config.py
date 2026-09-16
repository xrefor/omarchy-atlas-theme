"""Small configuration editors used by the explicit component installer."""
import json
import re


def jsonc_clean(text):
    # Match quoted strings first so URLs and escaped quotes survive comments.
    return re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else ' ' * len(m[0]), text)


def jsonc(text):
    clean = jsonc_clean(text)
    clean = re.sub(r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])',
                   lambda m: m[0] if m[0].startswith('"') else '', clean)
    return json.loads(clean or '{}')


def menu_extension(text, entries):
    """Own only a marked block; retain other entries and the user's comments."""
    text = re.sub(r'// BEGIN ATLAS MENU\n.*?// END ATLAS MENU\n?', '', text, flags=re.S)
    if not text.strip(): text = '{}\n'
    existing = jsonc(text)
    if not isinstance(existing, dict): raise ValueError('Omarchy menu must be an object')
    if existing.keys() & entries.keys():
        raise ValueError('An unmarked ATLAS menu entry already exists; reconcile it before installing')
    clean = jsonc_clean(text)
    end = clean.rfind('}')
    comma = ',' if existing and not clean[:end].rstrip().endswith(',') else ''
    body = json.dumps(entries, indent=2, ensure_ascii=False)[1:-1].strip('\n')
    result = text[:end] + '// BEGIN ATLAS MENU\n' + comma + '\n' + body + '\n// END ATLAS MENU\n' + text[end:]
    jsonc(result)
    return result


def block(text, name, body, comment='#'):
    start, end = f'{comment} BEGIN ATLAS {name}', f'{comment} END ATLAS {name}'
    pattern = re.compile(r'\n*' + re.escape(start) + r'.*?' + re.escape(end) + r'\n*', re.S)
    text = pattern.sub('\n\n', text).strip('\n')
    return (text + '\n\n' if text else '') + start + '\n' + body.strip() + '\n' + end + '\n'


def setting(text, key, val):
    pattern = rf'(?m)^{re.escape(key)}\s*=.*$'
    if re.search(pattern, text):
        return re.sub(pattern, lambda _: f'{key} = {val}', text, count=1)
    return f'{key} = {val}\n' + text


def merge(base, overlay):
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            merge(base[key], val)
        else:
            base[key] = val
    return base


def toml(data):
    """Serialize the value types accepted by these app config files."""
    def atom(val):
        if isinstance(val, str): return json.dumps(val, ensure_ascii=False)
        if isinstance(val, bool): return str(val).lower()
        if isinstance(val, (int, float)): return repr(val)
        if isinstance(val, list): return '[' + ', '.join(atom(x) for x in val) + ']'
        if isinstance(val, dict): return '{ ' + ', '.join(json.dumps(k) + ' = ' + atom(v) for k, v in val.items()) + ' }'
        if hasattr(val, 'isoformat'): return val.isoformat()
        raise ValueError(f'Unsupported TOML value: {type(val).__name__}')
    lines=[]
    def table(item, path=()):
        if path: lines.extend(['', '[' + '.'.join(json.dumps(k) for k in path) + ']'])
        for key, val in item.items():
            if not isinstance(val, dict): lines.append(json.dumps(key) + ' = ' + atom(val))
        for key, val in item.items():
            if isinstance(val, dict): table(val, path + (key,))
    table(data)
    return '\n'.join(lines) + '\n'
