# Medieval Village review workflow

Use `/home/ubuntu/unreal-auditor/medieval-workspace` on `lambda-unreal` for all Unreal editing, compiling, cooking and rendering. The Mac handles source transfer, scripts and browser QA. Preserve `source-original` and its verified 747-file manifest.

The user requested two small regions and 15–20 bugs, delivered through the existing A10 review service. The published package has 21 bugs and two baselines, including the car (MV18), desk lamp (MV19) and extinguisher (MV20), and modern apartment building (MV21). Read `docs/medieval-house-revision.md` for current release evidence and rebuild steps. Keep task taxonomy aligned with `user-2026-09-12-scene-semantics`; do not invent extra subtypes or force coverage.

Source actor labels are not unique. The map generator identifies actors by their unique object names and adds persistent `auditor_actor:` tags. Keep the original windmill Blueprint and its rotating component. The basket uses a physical horizontal E-key push; do not teleport or kick it upward in the baseline.

Use `-WaitMutex -MaxParallelActions=8 -NoUBA` for UnrealBuildTool. Build into a fresh output directory if any current launch profile references the prior binary. Never overwrite a published package. Other environment tasks share this server.

Before publication, verify native behavior, baseline interaction, traversal, boundaries, target/return-point reachability, rendered bug/baseline views, and baseline restoration. Visual support, collision and semantic claims need actual scene evidence. Automated QA does not count as human acceptance.

Prepare each service candidate from the current systemd WorkingDirectory. Preserve all other catalogs, launch profiles, participants, feedback, review history and evidence. Publish only after confirming no active/queued review sessions, backing up state, and verifying source/config hashes. If another environment publishes, rebase first. Preserve three shared FIFO slots, separate reviewer processes and same-family process reuse. Technical QA must use its own short-lived login and submit no feedback.

Each region has one shared bilingual scene introduction across all variants. Describe the setting and interactive objects only; omit WASD, mouse, E-key and other control instructions. Rubrics describe the observed anomaly and expected setting, never implementation actions such as replacing a source mesh or oil lamp. Bug rubrics show two concise sentences (anomaly then normal behavior); baseline rubrics remain hidden. Public IDs are `unreal_medieval_village_bug_01`–`21` and `unreal_medieval_village_baseline_01`–`02`.
