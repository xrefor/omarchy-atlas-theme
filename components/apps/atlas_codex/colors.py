"""Streaming SGR adaptation; terminal control strings are opaque byte streams."""
import re


class Colors:
    names = ('background', 'red', 'green', 'yellow', 'accent', 'magenta',
             'accent', 'foreground', 'muted', 'bright_red', 'bright_green',
             'bright_yellow', 'bright_yellow', 'bright_magenta', 'bright_yellow',
             'bright_foreground')
    max_sequence = 4096

    def __init__(self, palette):
        self.rgb = {}
        for key in (*self.names, 'lighter_background'):
            value = palette[key]
            if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                raise ValueError(f'Invalid color for {key}')
            self.rgb[key] = [str(int(value[i:i + 2], 16)) for i in (1, 3, 5)]
        self.pending = bytearray()
        self.state = 'text'
        self.osc = False
        self.string_escape = False
        self.utf8_remaining = 0

    def sgr(self, sequence):
        params = sequence[2:-1]
        if not re.fullmatch(rb'[0-9;]*', params):
            return sequence
        values = params.decode('ascii').split(';')
        result, i = [], 0
        while i < len(values):
            # Huge numeric parameters are invalid; don't feed them to int().
            if len(values[i]) > 5:
                return sequence
            value = int(values[i] or 0)
            if value in (38, 48, 58):
                if i + 1 >= len(values):
                    return sequence
                mode = values[i + 1]
                size = 3 if mode == '5' else 5 if mode == '2' else 0
                if not size or i + size > len(values):
                    return sequence
                group = values[i:i + size]
                if not all(x.isdigit() and len(x) <= 3 and int(x) <= 255 for x in group[2:]):
                    return sequence
                if mode == '5' and int(group[2]) < 16:
                    group = [str(value), '2', *self.rgb[self.names[int(group[2])]]]
                elif value == 48 and mode == '2':
                    rgb = list(map(int, group[2:]))
                    if max(rgb) <= 80 and max(rgb) - min(rgb) <= 8:
                        group = ['48', '2', *self.rgb['lighter_background']]
                result.extend(group)
                i += size
                continue
            index = value - 30 if 30 <= value <= 37 else value - 90 + 8 if 90 <= value <= 97 else None
            if index is None:
                result.append(values[i])
            else:
                result.extend(['38', '2', *self.rgb[self.names[index]]])
            i += 1
        return b'\x1b[' + ';'.join(result).encode('ascii') + b'm'

    def feed(self, data):
        out = bytearray()
        for byte in data:
            continuation = bool(self.utf8_remaining and 0x80 <= byte <= 0xbf)
            if continuation:
                self.utf8_remaining -= 1
            else:
                self.utf8_remaining = (1 if 0xc2 <= byte <= 0xdf else
                                       2 if 0xe0 <= byte <= 0xef else
                                       3 if 0xf0 <= byte <= 0xf4 else 0)
            if self.state == 'string':
                out.append(byte)
                if ((self.osc and byte == 7) or (self.string_escape and byte == 92)
                        or (byte == 0x9c and not continuation)):
                    self.state = 'text'
                self.string_escape = byte == 27
            elif self.state == 'overflow':
                out.append(byte)
                if 0x40 <= byte <= 0x7e:
                    self.state = 'text'
            elif self.state == 'csi':
                self.pending.append(byte)
                if 0x40 <= byte <= 0x7e:
                    seq = bytes(self.pending)
                    out.extend(self.sgr(seq) if byte == 109 else seq)
                    self.pending.clear()
                    self.state = 'text'
                elif len(self.pending) >= self.max_sequence:
                    out.extend(self.pending)
                    self.pending.clear()
                    self.state = 'overflow'
            elif self.state == 'escape':
                self.pending.append(byte)
                if byte == 91:
                    self.state = 'csi'
                elif byte in b']P^_X':
                    out.extend(self.pending)
                    self.pending.clear()
                    self.state = 'string'
                    self.osc = byte == 93
                    self.string_escape = False
                else:
                    out.extend(self.pending)
                    self.pending.clear()
                    self.state = 'text'
            elif not continuation and byte in (0x90, 0x98, 0x9d, 0x9e, 0x9f):
                out.append(byte)
                self.state = 'string'
                self.osc = byte == 0x9d
                self.string_escape = False
            elif not continuation and byte == 0x9b:
                out.append(byte)
                self.state = 'overflow'  # Preserve 8-bit CSI without rewriting.
            elif byte == 27:
                self.pending.append(byte)
                self.state = 'escape'
            else:
                out.append(byte)
        return bytes(out)

    def finish(self):
        pending = bytes(self.pending)
        self.pending.clear()
        self.state = 'text'
        self.utf8_remaining = 0
        return pending
