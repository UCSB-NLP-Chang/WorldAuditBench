# AWS code migration

Captured on 2026-09-30 into `UCSB-NLP-Chang/WorldAuditBench`.

## Branch layout

The original website commit, `75e8c0b5f638dbe3f9b826acad7bd8a71786565f`, is
preserved intact on `gh-pages`, including all 15 videos. `main` continues from that
commit with the website removed from its working tree and the paper code imported.
No history rewrite or force push is required.

The initial Pages setup returned HTTP 422 while the repository was private. The
repository was subsequently made public and the project page is now published
from `gh-pages` at https://ucsb-nlp-chang.github.io/WorldAuditBench/.

## Source selection

| Destination | Inspected source |
|---|---|
| Root agent, harness, evaluation and Three.js source | AWS `/home/ec2-user/game-auditing`, including its current working-tree judge changes |
| `services/review` | Actual `aws-unreal-audit.service` code directory |
| `services/explore` | Actual Explore and shared Review pool code directory |
| `services/evaluate` | Actual `aws-unreal-evaluate.service` code directory |
| `services/threejs` | Deployed `envs-2026-09-16c` server and packaging scripts |
| `unreal/source-snapshot` | Recovered 2026-09-14 source snapshot, upstream commit `fca8171a8478d04f9c19a38b22e0cb59cbe5af79` |
| `unreal/runtime-patches`, `unreal/urban-ipc` | Later AWS runtime/boundary and Urban IPC source |
| `experiments/ablations` | Selected AWS paper experiment drivers, with original paths retained |
| `benchmark/paper-tasks.json` | Exact 126 Unreal + 87 Three.js assigned tasks, cross-checked against the current preprint |

The preprint was inspected through Overleaf Git at revision
`c808f5f8e87dee47d4de9fb44c467edd5e287bb7`, using
`preprint/arxiv_preprint.tex` and its sections/tables. The Overleaf project was read
without editing or committing the manuscript.

`aws-source-files.json` records the source path, captured hash and size of each
imported file. `released_sha256` records the organized version; `adapted` identifies
changed files. Images are recorded as `pending_resource`. Historical development
plans were moved under `docs/history/`.

## Deliberate migration changes

- Added a paper-focused README, exact evaluation splits, resource manifest,
  reproduction guide, source validation, dependency lists and CI.
- Bundled the existing agent implementation and verified it against the pinned AWS
  dependency. Replaced the private clone step with checks against per-file hashes.
- Updated native test imports to the bundled package; updated outdated retired-case
  counts in the agent tests. Resource tests skip explicitly when images are absent.
- Preserved source attribution and historical Unreal notes. No unverified license
  was assigned to authored or third-party content.

AWS was accessed read-only for source and configuration metadata. No live service,
reviewer data, engine build, model job or source checkout was changed. Authentication
files, participant records, databases, raw review submissions, engine installations,
large runtime packages and experiment recordings are excluded from the Git commit.
See `../validation.md` for tested behavior and inherited service failures.

## Public repository organization

On 2026-09-30, 53 historical pilot, rerun, scheduling, and summary scripts were
moved to `scripts/legacy/`, and two experiment handoffs to `docs/history/`. Their
contents were preserved. The in-context metadata moved from
`output/icl-unreal-20260916/` to `examples/icl/`; current launcher defaults, tests,
and resource restore paths were updated together.

The manifest retains original AWS source paths and captured hashes. Moved rows
record `previous_release_path`; `path` and `released_sha256` describe the current
checkout. Pending images now restore under `examples/icl/images/`.
