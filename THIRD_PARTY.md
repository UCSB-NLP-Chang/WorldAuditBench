# Third-party sources

The AWS migration combines authored benchmark code with environment source and
integration code from earlier project repositories. Original attribution files,
source comments, and environment READMEs are retained. No new blanket license is
assigned to third-party content by this migration.

- Agent/harness code: `KimperYang/game-auditing`; exact captured revision is in
  `docs/migration/aws-source-files.json`. The historical agent dependency is
  recorded in `scripts/native-agents/upstream.json`.
- Unreal authoring source: recovered `XMHZZ2018/3d-world-auditor` snapshot
  `fca8171a8478d04f9c19a38b22e0cb59cbe5af79`, plus the later AWS patches identified
  in the migration receipt.
- Three.js scenes: source copies and attribution under
  `candidate_environments/src/*/README.md` and their upstream directories.
- Additional prop attribution: `services/review/static/*-prop-attributions.md`.
- Unreal Engine, UnrealCV, Pixel Streaming, Open-P2P, and model clients retain
  their respective upstream licenses. Engine source, weights, scene asset packs,
  and third-party runtime installations are not included here.

Hugging Face asset packaging is pending. Preserve each asset's attribution and
redistribution terms when assembling that release.
