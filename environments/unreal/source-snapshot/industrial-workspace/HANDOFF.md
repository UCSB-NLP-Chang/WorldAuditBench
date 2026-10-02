# Industrial factory — A10 review deployment

Published 2026-09-12 at [the review workbench](https://review.150-230-45-149.sslip.io/). Select **Industrial**. The existing review workflow, bilingual rubrics, difficulty/quality fields, and task navigation are shared with the other environments.

There are **18 independent bugs and 3 clean baselines**: six bugs each in the robot assembly hall, vehicle test/loading bay, and elevated control room. Public IDs are `unreal_industrial_bug_01`–`18` and `unreal_industrial_baseline_01`–`03`. Definitions and the full task table are in [industrial-tasks.md](industrial-tasks.md).

## Deployment

- A10 workspace: `/home/ubuntu/unreal-auditor/industrial-workspace`.
- Project: `project/FactoryEnvironmentCollect.uproject`.
- Published package: `dist/industrial-linux/Linux/FactoryEnvironmentCollect`.
- Review release: `/home/ubuntu/unreal-auditor/review-service/releases/industrial-20260912`.
- Unreal 5.6.1, Linux Vulkan SM5, PixelStreaming2, 30 FPS cap.
- Binary SHA-256: `45fc5714d31cd1394be38d490e8656544303a3fc311503f9c1d88343bf48ed52`.

The release extends the then-current live catalog from 79 to 100 entries. Existing environments, capacity of three simultaneous sessions, identities, and review records were preserved. Publication verified live source/configuration hashes, required idle sessions, backed up SQLite/configuration, and verified protected record fingerprints and database integrity after restarting. Backup: `/home/ubuntu/unreal-auditor/review-service/backups/industrial-20260912-203208`.

## Verification

- All six region boundary/traversal checks passed.
- All 18 native bug behavior tests passed, including collision, view/distance triggers, and persistent state changes.
- All 18 rendered cases passed with clean baseline restoration in one process. Captures were visually inspected; overlap placement and chair movement were corrected before final packaging.
- All 119 review service regression tests passed.
- Candidate browser checks passed for 21 industrial entries, 36 bilingual bug views, three baseline views, and desktop/mobile layout.
- Public HTTPS browser QA passed: live decoded video, keyboard movement and mouse look, all three region baselines, and I01/I13. Four task/map switches retained native PID 505081 and the existing player frame. The mobile page had no horizontal overflow.
- Technical QA submitted no feedback. Its sessions were closed and temporary login removed.

A10 evidence: `out/pipeline-visual-final.log`, `out/review-regressions.log`, `out/render-review/results.json`, `out/public-report.json`, and package `runtime-verification.json` / `behavior-tests/results.json`. Candidate acceptance and deployment reports are under the review service's `staging/industrial-20260912`. Local copies and browser captures are under `out/industrial-a10/`.

For revisions, follow `environments/industrial-factory/AGENTS.md`. Build into a fresh output directory; never overwrite the published package. Always prepare the review candidate from the actual current systemd release, because other environment work can publish independently.
