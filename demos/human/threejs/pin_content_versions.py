#!/usr/bin/env python3
"""Pin every three.js task's review version to its LAST CONTENT CHANGE.

The review site labels a review "Current version" only when its (revision, sha256, build_sha256) equals the task's
current tuple; anything else is "Previous versions" (earlier build, still counting, or an older revision).  Our page
rebuilds (envs-2026-09-15 / 16 / 16b / 16c) gave every task a new tuple each time although most tasks' content did not
change, so almost every review ended up labelled "earlier build".  Content changes always come with a revision bump,
therefore the earliest known tuple carrying the task's current revision is its content version: revision-1 tasks point
at the 2026-09-12 build, tasks revised on 2026-09-15 at that build, tasks revised on 2026-09-16 at that one.  Every
other known tuple (later rebuilds) stays a compatibility alias, so acceptance does not change; only the labels do:
reviews made on any build since the task's last content change are "Current version" again.

Also: content_update.version points at the pinned tuple, package_id stays 16c, and the hash of the page actually
served is recorded in the informational field page_sha256.  Output: staging/tasks.json + staging/manifest-report.json
for publish_pinned.py (manifest only; the static site keeps serving the 16c pages).  Rule for future publications:
a page-only rebuild keeps the content version; only a content change (revision bump) moves it.
"""
import hashlib, json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path('/home/ubuntu/unreal-auditor')
RELEASE = pathlib.Path(__file__).resolve().parent
STATE = ROOT / 'review-service/state'
LIVE = pathlib.Path(subprocess.check_output(['systemctl', 'show', 'urban-review-pilot.service', '-p', 'WorkingDirectory', '--value'], text=True).strip())
sys.path.insert(0, str(LIVE))
from browser_runtime import validate_browser_task, SUITES  # noqa: E402

PAGE_OF = {p: f for p, (_, f, _) in SUITES.items()}
KEYS = ('revision', 'sha256', 'build_sha256')


def main():
    live_p = STATE / 'tasks.json'
    live = json.loads(live_p.read_text())
    page_sha = {l.split()[1]: l.split()[0] for l in (RELEASE / 'site/SHA256SUMS').read_text().splitlines()}
    out, pinned, moved = [], [], {}
    for t in live['tasks']:
        if t.get('runtime_kind') != 'browser':
            out.append(t); continue
        e = json.loads(json.dumps(t, ensure_ascii=False))
        known = list(dict.fromkeys([tuple(v[k] for k in KEYS) for v in e.get('review_compatible_versions', [])] + [tuple(e[k] for k in KEYS)]))   # chronological, deduplicated
        current = next(c for c in known if c[0] == e['revision'])          # earliest tuple with the current revision
        e['page_sha256'] = page_sha[PAGE_OF[t['id'][3:5]]]                  # the page that is actually served (16c)
        e['revision'], e['sha256'], e['build_sha256'] = current
        e['review_compatible_versions'] = [dict(zip(KEYS, c)) for c in known if c != current]
        if e.get('content_update'):
            e['content_update'] = dict(e['content_update'], version=dict(zip(KEYS, current)))
        e['case_id'] = f"{t['id']}-R{e['revision']:02d}"
        validate_browser_task(e)
        out.append(e); pinned.append(t['id'])
        if current != tuple(t[k] for k in KEYS): moved[t['id']] = current[2][:12]
    staged = dict(live, tasks=out)
    (RELEASE / 'staging').mkdir(exist_ok=True)
    keep = RELEASE / 'staging/tasks-16c-filehash-versions.json'
    if not keep.exists(): shutil.copy2(RELEASE / 'staging/tasks.json', keep)
    (RELEASE / 'staging/tasks.json').write_text(json.dumps(staged, ensure_ascii=False, indent=2) + '\n')
    report = {'mode': 'pin review versions to each task\'s last content change', 'pinned': pinned, 'moved': moved, 'live_release': str(LIVE),
              'live_tasks_sha256': hashlib.sha256(live_p.read_bytes()).hexdigest(), 'entries_before': len(live['tasks']), 'entries_after': len(out),
              'browser_entries': len(pinned), 'page_sha256': page_sha}
    (RELEASE / 'staging/manifest-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in report.items() if k != 'page_sha256'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
