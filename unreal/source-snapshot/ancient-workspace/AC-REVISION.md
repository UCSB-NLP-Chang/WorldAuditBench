# Ancient A24 household air conditioner

The user requested a more recognizable air-conditioner model. A24 now uses the free [MAR – Low Poly Outdoor AC Unit by MAR0237](https://www.fab.com/listings/b785c519-5e47-48a8-937e-d318aa58645c), downloaded from Fab under its Standard License.

The unit, cooling fan and two concrete supports are assembled into `/Game/Auditor/AncientCity/EraProps/HouseholdAC/SM_SM_HouseholdCondenser`. The white unit is 96 cm wide at scale 0.8. It remains beside the original tea-house brick pillar at XY (-1900, 5550), on the 20 cm floor, facing the passage. The outdoor placement trial was rejected because a capsule route from the tea-house spawn could not reach it. The final indoor position is reachable and preserves the current scene boundary and furnishings.

A24 keeps subtype S3 and advances to revision 2. English and Chinese rubrics describe the visible white air-conditioning unit and the historical expectation, without implementation or replacement wording. The other Ancient tasks were not edited by the AC work.

A10 sources and checks are under `ancient-workspace/source-additions/ac-v2` and `ancient-workspace/out/ac-v2`. `scripts/author_ac.py` applies only A24; `scripts/author_era.py` reapplies it after map regeneration. Import archive and attribution are recorded in `source-additions/ac-v2/manifest.json`.

The isolated `dist/ancient-ac-20260913-v2` candidate passed 34 native checks, 24 restoration cycles, 3 rendered views and 132 service tests. It was not published: the configuration task updated the shared Ancient source during publication preparation, and the source integrity check correctly stopped that attempt. Its staging directory is superseded by the combined release.

The combined `dist/ancient-configuration-20260913-v3` package also passed A24 and tea-house traversal checks, plus visual review of A24 and its clean reference. Evidence with immutable package hashes: `out/ac-v2/configuration-v3-verification.json`. The combined package was published in review-service release `configuration-tasks-20260913-v2`. A24 remains revision 2. Live browser verification passed: two bilingual A24 rubric views and four A24/AB02 switches, with live video and the same PID/iframe retained. The technical session was closed and its login revoked; no feedback, history or evidence records were submitted. Browser evidence: `out/ancient-a10/ac-v2/public-final/public-report.json` and A10 `out/ac-v2/public-report.json`; cleanup: `out/ac-v2/cleanup.json`.
