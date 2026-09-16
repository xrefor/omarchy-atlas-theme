"""Install the missing Nym CLI from the installed daemon's official release."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import Request, urlopen


RELEASES = 'https://github.com/nymtech/nym-vpn-client/releases/download'
API = 'https://api.github.com/repos/nymtech/nym-vpn-client/releases/tags'
VERSION = r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?'
MAX_ARCHIVE = 256*1024*1024
MAX_BINARY = 64*1024*1024


def release():
    daemon = shutil.which('nym-vpnd') or str(Path.home()/'.local/bin/nym-vpnd')
    output = subprocess.check_output([daemon, '--version'], text=True, timeout=10)
    match = re.search(r'^Build Version:\s*('+VERSION+r')\s*$', output, re.M)
    if not match:
        match = re.search(r'^nym-vpnd\s+('+VERSION+r')\s*$', output, re.M)
    if not match:
        raise ValueError('Cannot determine the installed Nym daemon version')
    arch = platform.machine()
    if platform.system() != 'Linux' or arch not in ('x86_64', 'aarch64'):
        raise ValueError('Automatic Nym CLI installation supports Linux x86_64 and aarch64')
    version = match.group(1)
    return version, f'nym-vpn-core-v{version}_linux_{arch}'


def fetch(url):
    return urlopen(Request(url, headers={'User-Agent': 'ATLAS-optional-installer'}), timeout=60)


def install(version, stem, destination):
    """Verify the archive before copying only its regular CLI member."""
    if not re.fullmatch(VERSION, version) or stem not in (
        f'nym-vpn-core-v{version}_linux_x86_64', f'nym-vpn-core-v{version}_linux_aarch64'
    ):
        raise ValueError('Invalid Nym release selection')
    destination = Path(destination)
    if os.path.lexists(destination):
        raise ValueError(f'Refusing to replace existing {destination}')
    tag = 'nym-vpn-v'+version
    with fetch(f'{API}/{tag}') as response:
        metadata = json.load(response)
    if not isinstance(metadata, dict) or metadata.get('tag_name') != tag or metadata.get('draft') is not False:
        raise ValueError('Nym release metadata does not match the requested release')
    assets = [a for a in metadata.get('assets', []) if a.get('name') == stem+'.tar.gz']
    if len(assets) != 1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', assets[0].get('digest') or ''):
        raise ValueError('Matching Nym release archive or SHA-256 digest is unavailable')
    expected = assets[0]['digest'].split(':')[1]
    size = assets[0].get('size')
    if type(size) is not int or not 0 < size <= MAX_ARCHIVE:
        raise ValueError('Invalid Nym archive size')
    # Construct the official URL instead of following URLs supplied by metadata.
    with tempfile.TemporaryDirectory(prefix='atlas-nym-cli-') as work:
        archive = Path(work)/'core.tar.gz'
        digest = hashlib.sha256()
        downloaded = 0
        with fetch(f'{RELEASES}/{tag}/{stem}.tar.gz') as response, archive.open('wb') as output:
            while chunk := response.read(1024*1024):
                downloaded += len(chunk)
                if downloaded > size:
                    raise ValueError('Nym archive exceeds its published size')
                digest.update(chunk)
                output.write(chunk)
        if downloaded != size or digest.hexdigest() != expected:
            raise ValueError('Nym archive SHA-256 verification failed')
        with tarfile.open(archive, 'r:gz') as bundle:
            members = [m for m in bundle.getmembers() if m.name == stem+'/nym-vpnc']
            if len(members) != 1 or not members[0].isfile() or not 0 < members[0].size <= MAX_BINARY:
                raise ValueError('Nym archive must contain one regular nym-vpnc binary')
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Publish a complete executable without overwriting an existing path.
            fd, temporary = tempfile.mkstemp(prefix='.nym-vpnc-', dir=destination.parent)
            try:
                with os.fdopen(fd, 'wb') as output, bundle.extractfile(members[0]) as source:
                    shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
                    os.fchmod(output.fileno(), 0o755)
                os.link(temporary, destination)
            finally:
                os.unlink(temporary)
    print(f'Installed nym-vpnc {version}: {destination}')


def offer():
    try:
        version, stem = release()
        destination = Path.home()/'.local/bin/nym-vpnc'
        print(f'\nNymVPN CLI {version} (matches installed daemon)\n'
              f'  Official Nym GitHub release → {destination}\n'
              '  Download verified against the release SHA-256 digest.')
        if input('Install nym-vpnc? [y/N] ').strip().lower() in ('y', 'yes'):
            install(version, stem, destination)
    except EOFError:
        return
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f'Optional Nym CLI install failed: {error}. Retry with python3 lib/atlas/optional.py.')
