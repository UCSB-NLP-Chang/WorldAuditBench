# H03 stove pot revision — 2026-09-13

Published release: `/home/ubuntu/unreal-auditor/review-service/releases/indoor-h03-pot-20260913-v1`.

H03 (revision 33) is now an oversized pot on the kitchen stove, classified as G3 / geometry.scale. The pot extends beyond one cooking position into neighboring burner space. Its base remains on the stovetop. The rejected giant-chair and wider-chair variants are superseded.

Authoritative source: `/home/ubuntu/unreal-auditor/indoor-workspace`. Actor `StaticMeshActor_299`, scale `[2.6, 2.6, 1.6]`, probe `[-65, -1005, 239]`. Bilingual criteria, instructions, and embedded runtime catalog are updated. All other task recipes are unchanged.

Verification passed: 26 paired native behavior checks, 2 visually inspected H03 packaged renders, 6 route checks, 13 same-process restoration cycles, and 141 service tests. The pot width/stove width ratio is 0.206 in control and 0.536 with the bug; base displacement is 0.000 cm in both.

Public browser verification passed for H03 and HB02 with live video and the same native process across task switches. Browser screenshots establish session rendering, not a close-up of the pot; the packaged render pair supplies visual geometry verification. The dedicated QA session was closed, its login revoked, and no feedback was submitted.

Deployment preserved all 256 entries, existing participants, feedback/history/evidence, other environment releases, and capacity 3. H03 no longer accepts compatibility aliases for its former chair behavior; unchanged indoor tasks retain their prior compatible tuples.

Remote evidence: `/home/ubuntu/unreal-auditor/indoor-h03-pot-workspace/out/` (`acceptance.json`, `validation.json`, `deployment-report.json`, `public-report.json`). New binary: `/home/ubuntu/unreal-auditor/indoor-workspace/dist/indoor-h03-pot-20260913-v1/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou`.
