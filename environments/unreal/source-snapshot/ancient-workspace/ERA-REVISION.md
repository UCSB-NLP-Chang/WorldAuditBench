# Ancient Chinese City: four era cases

Published to A10 on 2026-09-13 UTC (2026-09-12 Pacific) as `ancient-era-20260913-v1`, based on `semantic-compatibility-20260912-v1`.

| ID | Scene | Observable anomaly |
| --- | --- | --- |
| A21 | Tea house | A desktop computer and monitor on a wooden tea table |
| A22 | Market | A modern newspaper pasted to a brick wall, with a 2026 date, smartphone illustration and metro news |
| A23 | Residence entrance | A video camera on a tripod beside the stone lion |
| A24 | Tea house | A modern air-conditioning unit on clear floor beside a pillar |

Each is an independent S3 case. Ancient now has 24 bugs and 3 baselines; the site has 253 entries across 13 families. Existing task IDs, revisions and other families' profiles are preserved. The site retains the latest semantic compatibility taxonomy and ordering by bug type. Scene introductions contain no key or mouse instructions; bilingual rubrics describe the observed anomaly and normal expectation in two sentences.

The computer, camera and air conditioner use existing licensed assets on A10, copied with dependency checksums. The newspaper contains original fictional articles and original phone illustrations, typeset by `scripts/ancient/make_newspaper.py`. It is attached to a solid wall with nine surface samples and a verified capsule route to its reading position.

The authoritative project is `/home/ubuntu/unreal-auditor/ancient-workspace/project`. The new executable is `dist/ancient-era-20260913-v1/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity`, SHA256 `f727b9eaeaf707d747163a6d231c1f8f1609e435cd5791fd75345f5b91e8fdd0`. Executable and package hashes are recorded in `out/era-v1/acceptance.json`. The previous published package remains intact.

Validation: 34 native behavior, traversal, boundary and interaction checks; 24 same-process restoration cycles; 11 rendered bug, clean-reference and baseline views; an additional camera review render; 132 service tests; browser checks of all 13 families' ordering, 27 Ancient entries and bilingual copy; live streamed switches through all four additions and their baselines in one process. No review feedback was submitted. Sparse NPCs, 30 FPS streaming, independent door leaves, basket pushing and stair traversal are preserved.

Source and checks are in `scripts/ancient/` locally and `ancient-workspace/scripts/` on A10. `author_era.py` adds the four cases to existing authored maps without rebuilding the city. After intentionally regenerating the base regions, run it again, then `complete_rubrics.py`, and build into a fresh output directory. `native-wall-support.patch` records the bounded runtime change for wall-supported props; apply it only to the matching Ancient source, not wholesale to other worlds.

Deployment backup: `/home/ubuntu/unreal-auditor/review-service/backups/ancient-20260913-005202`. Existing participant and review records passed preservation checks. Evidence is under `out/ancient-a10/era-v1/` locally and `ancient-workspace/out/era-v1/` on A10.
