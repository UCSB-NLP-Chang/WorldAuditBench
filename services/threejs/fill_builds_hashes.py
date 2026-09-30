#!/usr/bin/env python3
"""Write the release file table (sha256 from site/SHA256SUMS) into candidate_environments/BUILDS.md (re-runnable)."""
import pathlib, re
RELEASE = pathlib.Path(__file__).resolve().parent
BUILDS = pathlib.Path('/home/ubuntu/game-auditing/candidate_environments/BUILDS.md')
NOTES = {
    '00_sponza_constrained.html': 'Sponza atrium, the SP suite (15 cases; sp03 retired) - packed harness page (`tools/pack_harness_page.py --family sponza`)',
    '01_mistwood_cottage_constrained.html': 'Mistwood Cottage (CT suite, 17 cases; ct16 retired) - `relayer.py cottage` over the 2026-09-12 build',
    '03_sketchbook_airfield_constrained.html': 'Sketchbook airfield (AF suite, 19 cases) - `relayer.py sketch` over the 2026-09-12 build',
    '09_sims_house_builder_constrained.html': 'Family house (HS suite, 16 cases) - packed harness page (`tools/pack_harness_page.py --family house`)',
    '10_beautiful_water_clean_constrained.html': 'Reef dive (WT suite, 13 cases; wt03/wt04/wt06/wt10/wt13 retired) - `relayer.py water` over the 2026-09-12 build',
    '13_beyond_fable_wilderness_constrained.html': 'Beyond Fable wilderness (WL suite, 16 cases; wl04/wl13 retired) - `python3 src/fable/build.py` (vite)',
    'bugs.html': 'one card per case of every environment (`tools/make_bug_index.py`)',
}
rows = []
for line in (RELEASE / 'site/SHA256SUMS').read_text().splitlines():
    digest, name = line.split()
    size = (RELEASE / 'site' / name).stat().st_size / 1e6
    rows.append(f'| `{name}` | {size:.1f} MB | `{digest[:16]}...` | {NOTES.get(name, "")} |')
table = '| file | size | sha256 | notes |\n|---|---|---|---|\n' + '\n'.join(rows)
s = BUILDS.read_text()
s = re.sub(r'\| file \| sha256 \| notes \|\n\|---\|---\|---\|\n<!--HASHES-->', table, s, count=1) if '<!--HASHES-->' in s else re.sub(r'\| file \| size \| sha256 \| notes \|\n\|---\|---\|---\|---\|\n(?:\| `.*?\n)+?(?=\nSuperseded: \*\*envs-2026-09-15\*\*)', table + '\n', s, count=1)
BUILDS.write_text(s)
print(table)
