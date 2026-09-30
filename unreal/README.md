# Unreal source and runtime integration

- `source-snapshot/`: recovered authoring source captured on 2026-09-14. Includes
  project configuration, authored C++ plugins, task recipes, generation scripts,
  and original workflow notes. It is an archival source snapshot.
- `runtime-patches/`: later AWS exploration and boundary changes, including
  `unreal-area-3x-20260918/source-after`.
- `urban-ipc/`: the AWS Urban IPC build source and related tools from 2026-09-20.
- `deployed-bridge/`: the latest dated bridge copy found in the AWS deployment.

Current runtime profile and policy snapshots are in `../benchmark/`. Each imported
file is traced to its original location in `../docs/migration/aws-source-files.json`.

These sources do not include Unreal Engine or editable `.uasset`/`.umap` content.
The 2026-09-14 recovery was explicitly recorded as an incomplete editor-asset
recovery; it must not be represented as a verified rebuild of every later binary.
Runtime packages and editable assets are pending Hugging Face packaging. Original
workflow files may describe superseded deployment paths and release procedures.
