# External resources: pending Hugging Face release

The current delivery contains code and metadata. Large resources remain pending,
with a Hugging Face release planned. Download links will be added when available.

| Resource | Status |
|---|---|
| Unreal packaged Linux environments | Pending |
| Editable Unreal scene assets (`.uasset`, `.umap`) | Pending; completeness must be checked against the recovered source |
| Six built Three.js environments | Pending; deployed filenames, sizes and SHA-256 recorded |
| ICL demonstration images | Pending; all 29 original images and their service copies have file hashes |
| Open-P2P 1.2B weights | Pending; use the upstream distribution/license |
| VLA trajectories and frozen ablation inputs | Pending |

`../resources/manifest.json` records known file identities. Null sizes or archive
hashes mean they have not yet been inventoried or packaged. A binary hash identifies
an executable only; it does not validate the whole Unreal package.

The agent demonstration pack belongs in `examples/icl/`; its images restore to
`examples/icl/images/`. Text and exclusion metadata are already included.

Once restored to the recorded relative paths, run:

```bash
python scripts/check_release.py --resources
```

That command fails explicitly while any listed resource is missing or awaiting
packaging. The source-only check omits `--resources`. The 10 ICL-dependent tests
are skipped in a source-only checkout and become available after restoring images
and running `scripts/native-agents/setup.py`.

The project-page videos already present in `gh-pages` are retained there. They are
independent of the benchmark runtime/resource release.
