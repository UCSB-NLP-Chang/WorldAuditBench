# Validation

## Automated checks

```bash
python scripts/check_release.py
python -m pytest -q
```

The release check verifies the 213 task IDs, evaluation splits, anomaly-family
counts and environment package coverage. Tests cover agents, task inputs,
scoring, environment interfaces and archive integrity.

## Installed environments

```bash
python scripts/check_release.py --resources
```

This verifies installed files against the published release checksums. Use
`--runtime-root /path/to/runtime` for a custom installation directory.

Source tests and file checks do not establish visual correctness or reproduce
paper scores. Rendering and collision behavior require running the environments.
