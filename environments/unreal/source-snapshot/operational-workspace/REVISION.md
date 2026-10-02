# Operational-state additions — A10
Published review release: operational-states-20260913-v1, rebased on subway-lighting-20260913-v1. 256 entries, 13 families, capacity 3.

- A17 (revision 7): the initially open residence door leaf closes on its own after five seconds of continuous observation. The other leaf remains closed. Walk/turn first to arm observation; distance under five metres, facing and unobstructed sight required. No leave-and-return requirement. E still operates each leaf independently.
- I20 (revision 1): the control-room wall lamp above the notice board switches off after six seconds of observation; both lamp emission and its actual light go off.
- I21 (revision 1): the control console's operating displays and indicator emission switch off together after six seconds of observation. Hardware stays in place.
- IB03 is revision 3 because its previously blank control-console displays now show an original operations dashboard. The same authored display is shared by the other control-room cases.
All three bugs use T3 / state.operational_state, with concise bilingual anomaly/expected rubrics and existing bug-type ordering. Moving/turning arms observation so initial stream loading cannot consume the transition. Reset reloads original state and timers.

Authoritative Unreal source and assets remain on A10:
- ancient-workspace/project/Plugins/AuditorRuntime/Source/AuditorRuntime/{Private/AncientInteractions.cpp,Public/AncientInteractions.h}
- industrial-workspace/project/Plugins/AuditorRuntime/Source/AuditorRuntime/{Private/IndustrialOperational.cpp,Public/IndustrialOperational.h}
- industrial-workspace/scripts/author_operational.py embeds the controller, shared original display texture/material, off material and light tag. The main industrial author script invokes it.
- ancient-workspace/scripts/author_operational.py refreshes only embedded catalogs; it does not regenerate or replace geometry.
- Immutable final binaries: ancient-workspace/dist/ancient-operational-20260913-v1 and industrial-workspace/dist/industrial-operational-20260913-v1.
Retain existing SM6 ancient and SM5 industrial launch arguments.

Validated: 34 ancient native checks, 24 ancient restoration cycles, paired open/closed door renders; 21 industrial behavior checks, six route/boundary checks, four rendered operational bug/control runs and 21 same-process rendered restoration cycles. 141 service checks passed. Data-copy verification retained applicable previous reviews for all 41 existing identities without rewriting feedback.

Only A17 and IB03 invalidate their earlier current-version judgments; old feedback/history remains. Verified unchanged cases retain earlier compatible version tuples. All unrelated families, the concurrent subway release, participants, evidence and history were preserved. Publication used fresh source/state hash guards, idle-reviewer checks, SQLite backup and rollback.

Proofs: operational-workspace/out/{acceptance.json,validation.json,deployment-report.json}; industrial-workspace/out/operational; ancient-workspace/out/operational-v1. Public browser QA report is in the local out/operational-public directory.

