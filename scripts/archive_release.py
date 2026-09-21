"""Archive reviewable source and SHA256 after candidate verification."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/release-readiness/2026-09-20'
RELEASE=ROOT/'release'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    audit=json.loads((DOCS/'package-audit.json').read_text(encoding='utf-8'))
    assert audit['relocated_selftest']=='pass'
    assert sha(RELEASE/audit['asset'])==audit['sha256']
    patch=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','diff','--binary'],cwd=ROOT,stderr=subprocess.PIPE)
    (DOCS/'source.patch').write_bytes(patch)
    files=[ROOT/n for n in ('eojstart.py','eoj_auto_solver.py','eoj_portable.py','eoj_cli.py','README.md','LICENSE','requirements.txt','pytest.ini','.gitignore','.gitattributes','.env.example')]
    for directory in ('eojkit','tests','scripts'):
        files.extend((ROOT/directory).rglob('*.py'))
    files.extend(p for p in DOCS.rglob('*') if p.is_file() and (p.suffix in ('.md','.lock') or p.name in {'TOOLCHAIN_SOURCE.json','MSYS2_TOOLCHAIN_MANIFEST.json','MSYS2_SOURCE_VERIFICATION.json'} or 'third-party-licenses-msys2' in p.parts))
    files.extend((ROOT / "docs/release-readiness/2026-09-21").glob("*.md"))
    manifest=json.loads((RELEASE/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for relative,expected in manifest.items():
        assert sha(ROOT/relative)==expected,relative
    source=RELEASE/'EOJSolver-4.0.1-source.zip'
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as out:
        for p in sorted(set(files)):
            out.write(p,p.relative_to(ROOT))
    for name in ('USER_GUIDE.md','RELEASE_NOTES.md','THIRD_PARTY.md','VERIFICATION.md'):
        shutil.copy2(DOCS/name,RELEASE/name)
    items=sorted(p for p in RELEASE.iterdir() if p.is_file() and p.name!='SHA256SUMS')
    (RELEASE/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in items),encoding='utf-8')
    shutil.copy2(RELEASE/'SHA256SUMS',DOCS/'SHA256SUMS')
    print(json.dumps({'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in items]},indent=2))

if __name__=='__main__':
    main()
