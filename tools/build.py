#!/usr/bin/env python3
"""Create a deterministic release from tracked files in an explicit allowlist."""
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
FILES=('README.md','LICENSE','VERSION','colors.toml','icons.theme','keyboard.rgb',
       'chromium.theme','preview.png','unlock.png','screensaver-mark.png',
       'shell.toml','hyprland.lua','neovim.lua','gtk-3.0.css','gtk-4.0.css','install.py','install.sh','.gitignore')
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
        path=root/rel
        if path.is_symlink() or not path.is_file(): raise ValueError('Unsafe release entry: '+str(rel))
        if _private(rel): raise ValueError('Private/generated artifact in release: '+str(rel))
        result[str(rel)]=path
    return result


def main():
    version=(ROOT/'VERSION').read_text().strip()
    if not version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyz.-' for c in version): raise ValueError('Unsafe version')
    prefix='atlas-'+version
    entries=payload()
    hashes=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+name+'\n' for name,p in sorted(entries.items()))
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    archive=output/(prefix+'.tar.gz')
    with archive.open('wb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed, tarfile.open(fileobj=compressed,mode='w') as tar:
        for name,path in sorted(entries.items()):
            data=path.read_bytes();info=tarfile.TarInfo(prefix+'/'+name)
            info.size=len(data);info.mode=0o755 if path.stat().st_mode&0o111 else 0o644
            info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
            tar.addfile(info,io.BytesIO(data))
        data=hashes.encode();info=tarfile.TarInfo(prefix+'/SHA256SUMS');info.size=len(data);info.mode=0o644;info.mtime=0
        tar.addfile(info,io.BytesIO(data))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n')
    print(f'{len(entries)} files + SHA256SUMS; {archive.stat().st_size:,} bytes')
    print(archive)
    print(digest)

if __name__=='__main__': main()
