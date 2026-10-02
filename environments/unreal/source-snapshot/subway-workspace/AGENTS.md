# Subway on A10
The user requires Subway source edits, Unreal editor commandlets, compilation, tests and rendering to run on A10. This workspace and /home/ubuntu/unreal-auditor/projects/Subway are authoritative. The Mac is an SSH/browser client; do not build or render Subway on the Mac or push its stale snapshot over this project.

Project: /home/ubuntu/unreal-auditor/projects/Subway/Subway.uproject
Build: python3 scripts/build_subway_a10.py
Runtime: /home/ubuntu/unreal-auditor/review-service/releases/public-20260911, urban-review-pilot.service, shared HTTP 8092 and TURN TCP 23478. subway-review.service on 8093 is only a legacy redirect; its database is archived history.
Preserve the existing residential service and urban-review-pilot.service, their assets and feedback databases.
Use the current 19-task catalog in environments/subway/tasks.json. S19 is all 8 escalators running upwards. The deleted water equipment must remain absent. Three baselines are Concourse, Platform and Trackside.
After changing source or maps, rebuild on A10 and verify affected tasks. Refresh the manifest map hashes and runtime binary hash after a successful build without rotating credentials or discarding feedback. Stop an active Subway review session before replacing its running binary.

The user authorized unifying Subway, latest indoor H01-H13 and existing U018 in the 8092 UI. Preserve all identities and feedback. Every bug and baseline must have authored Chinese and English rubrics. Read review-service/HANDOFF-UNIFIED.md. Publish with scripts/publish_subway_a10.py after tests; it refreshes the unified manifest and profiles.

Public entry is https://review.150-230-45-149.sslip.io/ through review-web.service (Caddy). Participants use a shared team code and selected name. No reviewer SSH tunnel is needed. Public TURN uses TCP/3478 and relay UDP/25000-25031; retain per-project SM5/SM6 profiles. Preserve state/participants.json and the participants table; never put the group access code in source or URLs. Read review-service/releases/public-20260911/PUBLIC-HANDOFF.md for the current rollout.

## S20 update — 2026-09-13
S20 (platform private car, S1) is now published. Source catalog has S01–S20; S17 remains a retired backup and must not be republished. Active Subway review cases: S01–S16, S18–S20 plus B01–B03. Current package: subway-workspace/dist/subway-s20-20260913-v1. Read subway-workspace/s20/README.md and its reports. Current review release at publication: subway-s20-20260913-v2, based on ancient-indoor-cola-20260913-v3. Always resolve the live systemd WorkingDirectory for subsequent releases.

## S20 car replacement — 2026-09-13
User requested a different car because the original asset was reused. S20 now uses /Game/Auditor/Props/PrivateCoupe/SM_PrivateCoupe, a silver-blue modern coupe. Latest package: subway-workspace/dist/subway-s20-coupe-20260913-v1. Current review release at update: subway-s20-coupe-20260913-v1. Both bottom-left prop-credit links were removed from the internal UI at the user’s request; do not reintroduce them. Source attribution records remain in project files. Read subway-workspace/s20-car-replacement/README.md.

## Rubric presentation — 2026-09-13
Subway now uses the same concise bilingual paragraph (criteria + expected) as Ancient, Rural, Medieval and Industrial. This is a presentation-only change in the live static/app.js; keep authored expected/steps/criteria metadata intact. Baseline rubrics remain hidden. Do not reintroduce the old expandable format for Subway. Evidence: subway-workspace/s20-rubric/.

## Review continuity — 2026-09-13
Current release at update: review-continuity-20260913-v1. The coordinator accepts explicit review_compatible_versions for verified unchanged task content. Preserve and extend aliases with the previous exact version tuple when only an unrelated package/map rebuild changes hashes; clear aliases for actual behavior or judging-criterion changes. Never rewrite historical feedback versions. See review-continuity-workspace/README.md. Qiucheng’s 14 feedback records / 12 task statuses were restored. S19 rubric now says all escalators, without a numeric count; expected_count=8 remains an internal full-map test parameter, not reviewer copy.

## All-family rubric presentation — 2026-09-13
Supersedes the earlier per-family rendering exception: every Unreal and Three.js bug now uses one concise bilingual paragraph (criteria + expected), with class rubric-summary. No environment-specific old expandable rubric layout remains. Baseline rubric panels remain hidden. Content, task revisions and annotation compatibility are unchanged. Evidence: review-rubric-unification/report.json.

## Concourse lighting — 2026-09-13
S01 darkness/exposure instability fixed in package subway-lighting-20260913-v2; release subway-lighting-20260913-v1. Concourse now has fixed exposure and balanced inspection lighting. Preserve the S12 casting lamp at intensity 80 and its shadow behavior, and preserve explicit review compatibility aliases. Do not deploy calibration package v1. Read subway-workspace/lighting/README.md.
