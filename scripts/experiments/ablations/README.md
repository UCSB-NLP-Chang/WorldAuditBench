# Paper ablation reference code

These source files were collected from AWS experiment workspaces on 2026-09-30.
Use `../../docs/reproduction.md` for the paper protocol and the source receipt for
original locations. The names retain experiment dates so that different versions
are distinguishable.

| Directory | Role |
|---|---|
| `gemini-unreal-budget20-20260921` | VLM half-budget condition |
| `gemini-unreal-distance-ablation-20260921` | Near-spawn preparation and validation |
| `gemini-unreal-noicl-remaining-20260921` | Remove examples while retaining type guidance |
| `gemini-unreal-noicl-notype-20260924` | Remove examples and type guidance for VLM |
| `gemini-vla-noicl-notype-20260924` | Remove both forms of guidance for VLA–VLM |
| `section61-gemini-unreal-20260923` | VLA budget/distance/guidance and VLM 60-action conditions |
| `section62-gemini-random-types-20260924` | Final randomized multi-anomaly compositions |
| `gemini-unreal-multibug-20260922` | Multi-anomaly construction, native QA and anchor cohort |

These are reference drivers with original AWS paths and frozen-batch dependencies.
Operational restart/monitor processes and private run state were not imported.
Full reruns await the external environment packages, frozen run inputs and profile
path mapping. Source transfer did not start experiments or call paid model APIs.
