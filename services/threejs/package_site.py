#!/usr/bin/env python3
"""Assemble site/ for the envs-2026-09-16c three.js release (clean review view) from the freshly built pages in the benchmark repo:
the six environment files, bugs.html (tools/make_bug_index.py), index.html, SHA256SUMS and gzip twins (serve.py
serves the .gz when the browser accepts it).  The previous release directory (envs-2026-09-16b) is left untouched.
"""
import gzip, hashlib, pathlib, shutil, subprocess

REPO = pathlib.Path('/home/ubuntu/game-auditing')
RELEASE = pathlib.Path(__file__).resolve().parent
SITE = RELEASE / 'site'
PREV = RELEASE.parent / 'envs-2026-09-16b'
FILES = ['00_sponza_constrained.html', '01_mistwood_cottage_constrained.html', '03_sketchbook_airfield_constrained.html',
         '09_sims_house_builder_constrained.html', '10_beautiful_water_clean_constrained.html', '13_beyond_fable_wilderness_constrained.html']


def main():
    SITE.mkdir(exist_ok=True)
    subprocess.run([str(REPO / '.venv/bin/python'), str(REPO / 'tools/make_bug_index.py'), '--out', str(REPO / 'candidate_environments/bugs.html')], check=True, cwd=REPO)
    for name in FILES + ['bugs.html']:
        shutil.copy2(REPO / 'candidate_environments' / name, SITE / name)
    shutil.copy2(PREV / 'site/index.html', SITE / 'index.html')
    shutil.copy2(PREV / 'serve.py', RELEASE / 'serve.py')
    lines = []
    for name in FILES + ['bugs.html']:
        p = SITE / name
        lines.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {name}')
    (SITE / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    for p in list(SITE.glob('*.html')):
        with p.open('rb') as src, gzip.open(p.with_suffix(p.suffix + '.gz'), 'wb', compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
    print('\n'.join(lines))
    print('site files:', sorted(q.name for q in SITE.iterdir()))


if __name__ == '__main__':
    main()
