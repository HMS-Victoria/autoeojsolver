"""Verify source members against official .SRCINFO; package source companions."""
import hashlib,json,re,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'docs/release-readiness/2026-09-20';C=ROOT/'build/msys2-downloads';S=ROOT/'build/msys2-sources';TAR=r'C:\Windows\System32\tar.exe'
def sha(p,algorithm='sha256'):
 with p.open('rb') as f:return hashlib.file_digest(f,algorithm).hexdigest()
def main():
 records=json.loads((D/'MSYS2_TOOLCHAIN_MANIFEST.json').read_text());seen=set();checks=[]
 for r in records:
  url=r['source_url']
  if url in seen:continue
  seen.add(url);a=C/url.rsplit('/',1)[-1];assert sha(a)==r['source_sha256']
  base=a.name.rsplit('-'+r['version']+'.src.tar.zst',1)[0]
  # Split packages (gcc/gcc-libs, mingw-w64 CRT/headers) use the source archive base.
  folders=[p for p in S.iterdir() if p.is_dir() and (p/'.SRCINFO').is_file() and p.name==base]
  assert len(folders)==1,(base,folders)
  folder=folders[0];fields={}
  for line in (folder/'.SRCINFO').read_text().splitlines():
   if ' = ' in line:
    k,v=line.strip().split(' = ',1);fields.setdefault(k,[]).append(v)
  assert fields['pkgver'][0]+'-'+fields['pkgrel'][0]==r['version'],r['name']
  algorithm=next(k for k in ('sha256','sha512','b2','md5') if k+'sums' in fields)
  sources=fields['source'];hashes=fields[algorithm+'sums'];assert len(sources)==len(hashes)
  for src,expected in zip(sources,hashes):
   name=src.split('::')[0] if '::' in src else src.split('/')[-1]
   target=folder/name
   if 'git+' in src:
    commit=src.split('#commit=')[-1];assert re.fullmatch('[0-9a-f]{40}',commit),src
    actual=subprocess.check_output(['git','-c',f'safe.directory={target.as_posix()}',f'--git-dir={target}','rev-parse',commit+'^{commit}'],text=True).strip();assert actual==commit
    result={'source':src,'verification':'included Git commit exists','commit':actual}
   else:
    assert target.is_file(),target
    actual=sha(target,'blake2b' if algorithm=='b2' else algorithm)
    if expected!='SKIP':assert actual==expected,(target,actual,expected)
    result={'source':src,'verification':'presence only (upstream SKIP)' if expected=='SKIP' else algorithm+' pass','actual_hash':actual}
   checks.append({'package':base,**result})
 report={'source_archives':len(seen),'source_members_checked':len(checks),'checks':checks,'pgp_signatures_verified':False,'basis':'Official HTTPS binary SHA256 and source metadata. No source package build script executed.'}
 (D/'MSYS2_SOURCE_VERIFICATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 out=ROOT/'release/EOJSolver-4.0.1-toolchain-sources.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED) as z:
  for url in sorted(seen):
   p=C/url.rsplit('/',1)[-1];z.write(p,'sources/'+p.name)
  for name in ('MSYS2_TOOLCHAIN_MANIFEST.json','MSYS2_SOURCE_VERIFICATION.json','TOOLCHAIN_SOURCE.json','THIRD_PARTY.md'):
   z.write(D/name,name)
  for p in D.glob('mingw-w64-ucrt-x86_64-*.PKGINFO'):z.write(p,'package-metadata/'+p.name)
 with zipfile.ZipFile(out) as z:assert z.testzip() is None
 print(json.dumps({'source_archives':len(seen),'source_members_checked':len(checks),'asset':out.name,'bytes':out.stat().st_size,'sha256':sha(out)},indent=2))
if __name__=='__main__':main()
