# Section 6.2: Gemini nested multiple-bug experiment

Status: authorized 2026-09-22; environment preparation, no model episodes launched.

## Scope

Use Gemini 3.8 Flash / medium. Target seven Unreal environment families, three anchor tasks per family: 21 paired anchors. Reuse the existing selected single-bug A episodes where equivalence is verified; collect one new AB and one new ABC episode per anchor (42 new episodes). Each condition keeps 40 environment actions, 400 tool calls, original prompt, scene introduction, ICL, start pose, boundaries, observation policy, and model configuration. Do not change the original completed runs.

This supersedes the earlier GPT-6 24-block full-combination proposal. Seven families are not 21 independent environments. Anchors are selected without looking at scores, according to scene compatibility and available QA evidence. Candidate scope is not a claim that 21 compositions have passed QA.

## Composition and baseline reuse

A remains the original anomaly with its original rubric. Add B then C on distinct objects within the same playable region. Prefer the same subcategory as A so the original single-subcategory instruction and example remain appropriate. If an existing same-subcategory recipe cannot compose, a separately specified new instance may be authored on another suitable object; record its target, normal state, modification, and rubric before model execution. Do not substitute a different anomaly category while retaining a misleading single-category prompt.

Use an isolated experimental runtime with unchanged cooked content when possible. Keep published binaries immutable. QA must establish A is unchanged, each added anomaly exists, the inactive object has its normal state, all intended targets remain reachable, and no added anomaly hides another or changes a trigger. Check paired rendered observations and native target states. The A-only behavior of a rebuilt runtime must match the original reference before reusing that baseline. A changed prompt, spawn, trigger, target, or scene requires resolving equivalence rather than silently reusing the old score.

## Evaluation

Primary comparison: detection of the same anchor A in A, AB, and ABC. This holds target identity fixed. Also report all-bug success, per-target recall, and target-relative report precision, with one-to-one matching of atomic reported findings to frozen target rubrics. Pooled recall across nested conditions changes the target mix and cannot alone establish degradation on the same target. Preserve all judged findings and evidence; unmatched reports require checking for incidental real defects before calling them hallucinations. Undefined precision for no reports is not 100 percent.

Pair by anchor, report numerator and denominator, and retain per-family results. The sample is a small exploratory ablation over seven families; do not present correlated variants as independent environments or claim causal separation of exploration, recognition, and reporting.

## Execution

Freeze accepted selection, exclusions, rubrics, source/build hashes, original-baseline attempt provenance, prompts/ICL, and a randomized interleaved AB/ABC schedule before any paid run. Each new episode gets a fresh environment and context. Original dedicated Gemini credentials remain private and unchanged. Single-use admission verifies no new episode already has an attempt, all QA gates, source hashes and available GPU slots. Preserve all attempts and costs. Do not retry misses or auto-retry failed model runs. Keep 90-minute timeout, three-failure drain, and immediate auth/quota stop.

After real results arrive, update Section 6.2 and its table using the actual accepted cohort. Do not fill placeholders or imply execution while preparation is incomplete. Compile, visually verify, and push only relevant paper files to Overleaf.
