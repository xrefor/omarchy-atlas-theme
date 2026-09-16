"""Build a tiny resource-only APK owned by this test suite (no device install)."""
from pathlib import Path
import struct as s
import zipfile


def build(path):
    strings = ['manifest', 'package', 'dev.atlas.fixture', 'application']
    encoded = [s.pack('<H', len(item)) + item.encode('utf-16le') + b'\0\0' for item in strings]
    offsets = []
    blob = b''
    for part in encoded:
        offsets.append(len(blob)); blob += part
    blob += b'\0' * ((-len(blob)) % 4)
    pool = (s.pack('<HHIIIIII', 1, 28, 28 + len(offsets) * 4 + len(blob),
                   len(strings), 0, 0, 28 + len(offsets) * 4, 0)
            + s.pack('<' + 'I' * len(offsets), *offsets) + blob)

    def start(name, attrs=b'', count=0):
        return (s.pack('<HHIII', 0x102, 16, 36 + len(attrs), 1, 0xffffffff)
                + s.pack('<IIHHHHHH', 0xffffffff, name, 20, 20, count, 0, 0, 0) + attrs)

    def end(name): return s.pack('<HHIIIII', 0x103, 16, 24, 1, 0xffffffff, 0xffffffff, name)

    attr = s.pack('<IIIHBBI', 0xffffffff, 1, 2, 8, 0, 3, 2)
    body = pool + start(0, attr, 1) + start(3) + end(3) + end(0)
    xml = s.pack('<HHI', 3, 8, 8 + len(body)) + body
    with zipfile.ZipFile(path, 'w') as bundle: bundle.writestr('AndroidManifest.xml', xml)


if __name__ == '__main__':
    import sys
    build(Path(sys.argv[1]))
