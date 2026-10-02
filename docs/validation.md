# Validation

## Automated checks

```bash
python scripts/check_release.py
python -m pytest -q
```

The release check verifies the 213 task IDs, evaluation splits, anomaly-family
counts and environment package coverage. Tests cover agents, task inputs,
scoring, environment interfaces and archive integrity.

## Environment checks

See [environment validation](validation/2026-10-02/README.md) for task coverage,
rendering checks and unresolved visual issues.

The [2026-10-01 checks](runtime-validation.json) cover startup and camera movement
in the earlier compiled packages. They do not establish that every scene is free
of native rendering or collision defects.

Automated source tests do not run paid model evaluations or reproduce paper scores.
