#!/usr/bin/env python3
"""Create a deterministic release from tracked files in an explicit allowlist."""
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FILES=('README.md','CONTRIBUTING.md','index.html','LICENSE','VERSION','colors.toml','icons.theme','keyboard.rgb',
       'chromium.theme','preview.png','unlock.png','screensaver-mark.png',
       'shell.toml','hyprland.lua','neovim.lua','gtk-3.0.css','gtk-4.0.css','install.py','settings.py','install.sh','.gitignore')
DIRS=('lib','components','backgrounds','assets','LICENSES','docs','tests','tools')
PRIVATE_PARTS={'__pycache__','.git','.pytest_cache','.ssh','backups','preview-home','profiles'}
PRIVATE_NAMES={'.env','credentials','credentials.json','secrets.json','id_rsa','id_ed25519'}
PRIVATE_SUFFIXES={'.bak','.db','.key','.log','.p12','.p7b','.pem','.pfx','.pcap','.pcapng','.sqlite'}


def _allowed(rel,files,dirs):
    return str(rel) in files or (rel.parts and rel.parts[0] in dirs)


def _private(rel):
    parts={part.lower() for part in rel.parts}
    name=rel.name.lower()
    return (bool(parts & PRIVATE_PARTS) or name in PRIVATE_NAMES or name.startswith('.env.')
            or name.startswith('screenshot') or rel.suffix.lower() in PRIVATE_SUFFIXES)


def payload(root=ROOT,files=FILES,dirs=DIRS):
    result=subprocess.run(['git','-C',str(root),'ls-files','-z'],capture_output=True)
    if result.returncode:
        raise ValueError('Release builds require a Git checkout')
    tracked={Path(raw.decode()) for raw in result.stdout.split(b'\0') if raw}
    required={Path(name) for name in files}
    missing=required-tracked
    if missing: raise ValueError('Required release file is not tracked: '+', '.join(map(str,sorted(missing))))
    result={}
    for rel in sorted(tracked):
        if not _allowed(rel,files,dirs): continue
        if any(ord(c)<32 or ord(c)==127 or c=='\\' for c in str(rel)):
            raise ValueError('Unsafe release filename: '+repr(str(rel)))
        path=root/rel
        if any((root/parent).is_symlink() for parent in (rel,*rel.parents)) or not path.is_file():
            raise ValueError('Unsafe release entry: '+str(rel))
        if _private(rel): raise ValueError('Private/generated artifact in release: '+str(rel))
        result[str(rel)]=path
    return result


def write_archive(archive,prefix,entries):
    # Hash the exact bytes being archived and replace a prior build only after
    # the complete archive has been written successfully.
    hashes=[]
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.'+archive.name+'.',dir=archive.parent,delete=False) as raw:
            temporary=Path(raw.name)
            with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed, tarfile.open(fileobj=compressed,mode='w') as tar:
                for name,path in sorted(entries.items()):
                    data=path.read_bytes();info=tarfile.TarInfo(prefix+'/'+name)
                    hashes.append(hashlib.sha256(data).hexdigest()+'  '+name+'\n')
                    info.size=len(data);info.mode=0o755 if path.stat().st_mode&0o111 else 0o644
                    info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                    tar.addfile(info,io.BytesIO(data))
                data=''.join(hashes).encode();info=tarfile.TarInfo(prefix+'/SHA256SUMS');info.size=len(data);info.mode=0o644;info.mtime=0
                tar.addfile(info,io.BytesIO(data))
        temporary.chmod(0o644)
        temporary.replace(archive)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def main():
    version=(ROOT/'VERSION').read_text().strip()
    if not version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyz.-' for c in version): raise ValueError('Unsafe version')
    prefix='atlas-'+version
    entries=payload()
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    archive=output/(prefix+'.tar.gz')
    write_archive(archive,prefix,entries)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n')
    print(f'{len(entries)} files + SHA256SUMS; {archive.stat().st_size:,} bytes')
    print(archive)
    print(digest)

if __name__=='__main__': main()
