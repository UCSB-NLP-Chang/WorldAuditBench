# In-context examples

[`icl/`](icl/) contains the demonstration text and task exclusions used by the
auditing agents:

- `context.json`: category definitions, example conversations, and relative image paths.
- `exclude_from_eval.json`: demonstration tasks and aliases excluded from evaluation.

The **29 demonstration images are pending release on Hugging Face**. Their
expected locations and hashes are recorded in
[`resources/manifest.json`](../resources/manifest.json), under `examples/icl/images/`.
The native launcher uses `examples/icl/` by default; `--icl-dir` can select a
different pack.

This directory contains benchmark inputs. Generated episodes, logs, and installed
runtimes go under ignored `out/` or `runs/` directories.
