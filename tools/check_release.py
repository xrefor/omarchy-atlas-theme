#!/usr/bin/env python3
"""Check deterministic packaging, payload hashes and a staged release install."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')


def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, env=ENV, check=True)


def main():
    archive = ROOT / 'dist' / ('atlas-' + (ROOT / 'VERSION').read_text().strip() + '.tar.gz')
    digests = []
    for _ in range(2):
        run(sys.executable, 'tools/build.py')
        digests.append(hashlib.sha256(archive.read_bytes()).hexdigest())
    if digests[0] != digests[1]:
        raise ValueError('Release builds were not byte-identical')
    if archive.with_name(archive.name + '.sha256').read_text().split()[0] != digests[0]:
        raise ValueError('Archive checksum file does not match')
    print('PASS: byte-identical release builds and archive checksum', flush=True)

    with tempfile.TemporaryDirectory(prefix='atlas-release-check-') as directory:
        temporary = Path(directory)
        extracted = temporary / 'extracted'
        with tarfile.open(archive) as bundle:
            bundle.extractall(extracted, filter='data')
        release = extracted / archive.name.removesuffix('.tar.gz')
        manifest = {}
        for line in (release / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            if name in manifest or not (release / name).resolve().is_relative_to(release):
                raise ValueError('Invalid or duplicate checksum entry: ' + name)
            if hashlib.sha256((release / name).read_bytes()).hexdigest() != digest:
                raise ValueError('Release file checksum mismatch: ' + name)
            if (release / name).read_bytes() != (ROOT / name).read_bytes():
                raise ValueError('Release file differs from source: ' + name)
            manifest[name] = digest
        actual = {str(path.relative_to(release)) for path in release.rglob('*') if path.is_file()}
        if actual != set(manifest) | {'SHA256SUMS'}:
            raise ValueError('Release payload differs from its checksum manifest')
        print(f'PASS: {len(manifest)} extracted payload files and internal checksums', flush=True)

        run(sys.executable, 'tools/build_site.py', cwd=release)
        print('PASS: showcase builder and assets from the extracted release', flush=True)

        # Execute the shipped tests so omissions from the build allowlist fail.
        for model in ('idle', 'matrix', 'monitor', 'polkit'):
            run('node', f'tests/{model}_model_test.cjs', cwd=release)

        staging = temporary / 'home'
        staging.mkdir()
        original = '# recipient shell configuration\n'
        (staging / '.bashrc').write_text(original)
        manifest_path = staging / '.local/state/atlas-bundle/manifest.json'
        stamp = None
        for args in (('--all', '--offline'), ('--all', '--offline'),
                     ('sync', '--palette', str(release / 'colors.toml')),
                     ('check', '--palette', str(release / 'colors.toml'))):
            run(sys.executable, str(release / 'install.py'), *args,
                '--home', str(staging), '--no-refresh', cwd=release)
            current = manifest_path.stat()
            current_stamp = (current.st_ino, current.st_mtime_ns, current.st_mode)
            if stamp is not None and current_stamp != stamp:
                raise ValueError('An unchanged release operation rewrote the manifest')
            if (manifest_path.parent / 'pending.json').exists():
                raise ValueError('Release operation left a pending transaction')
            stamp = current_stamp
        run(sys.executable, str(release / 'install.py'), 'restore', '--home', str(staging), cwd=release)
        if (staging / '.bashrc').read_text() != original or manifest_path.exists():
            raise ValueError('Release restoration failed to preserve the original configuration')
        print('PASS: extracted installation, unchanged repeat/sync/check and restoration', flush=True)


if __name__ == '__main__':
    main()
