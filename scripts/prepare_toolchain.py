"""Reproduce the private GCC toolchain from the audited MSYS2 package lock."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs/release-readiness/2026-09-20'
CACHE = ROOT / 'build/msys2-downloads'
STAGE = ROOT / 'build/msys2-toolchain'
TAR = Path(__import__('os').environ['SYSTEMROOT']) / 'System32/tar.exe'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare():
    packages = json.loads((DOCS / 'MSYS2_TOOLCHAIN_MANIFEST.json').read_text(encoding='utf-8'))
    installed = {p['name']: p['version'] for p in packages}
    provided = set(installed) | {name for p in packages for name in p.get('provides', [])}
    for package in packages:
        assert all(name in provided for name in package['dependencies']), package['name']
    CACHE.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    source_stage = ROOT / 'build/msys2-sources'
    source_stage.mkdir(parents=True, exist_ok=True)
    extracted_sources = set()
    for package in packages:
        for kind in ('binary', 'source'):
            url = package[kind + '_url']
            archive = CACHE / url.rsplit('/', 1)[-1]
            if not archive.exists():
                part = archive.with_suffix(archive.suffix + '.part')
                with urllib.request.urlopen(url.replace('mirror.msys2.org', 'repo.msys2.org'), timeout=60) as response, part.open('wb') as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
                part.replace(archive)
            assert sha256(archive) == package[kind + '_sha256'], archive.name
            names = subprocess.check_output([str(TAR), '-tf', str(archive)], encoding='utf-8').splitlines()
            assert all(not name.startswith(('/', '\\')) and ':' not in name and '..' not in Path(name).parts for name in names)
            if kind == 'binary':
                metadata = subprocess.check_output([str(TAR), '-xOf', str(archive), '.PKGINFO'], encoding='utf-8')
                assert 'pkgname = ' + package['name'] in metadata and 'pkgver = ' + package['version'] in metadata
                (DOCS / (package['name'] + '.PKGINFO')).write_text(metadata, encoding='utf-8')
                subprocess.run([str(TAR), '-xf', str(archive), '-C', str(STAGE), 'ucrt64/'], check=True)
            elif archive not in extracted_sources:
                subprocess.run([str(TAR), '-xf', str(archive), '-C', str(source_stage)], check=True)
                extracted_sources.add(archive)
        print(package['name'], package['version'], 'verified')
    assert (STAGE / 'ucrt64/bin/g++.exe').is_file()
    return STAGE / 'ucrt64'


if __name__ == '__main__':
    print(prepare())
