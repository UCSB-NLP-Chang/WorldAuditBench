# Validation

## Automated checks

```bash
python scripts/check_release.py
python -m pytest -q -m 'not chromium and not live'
```

The release check verifies the 213 task IDs, evaluation splits, anomaly-family
counts and environment package coverage. Tests cover agents, task inputs,
scoring, environment interfaces and archive integrity.

CI also runs the Explore service tests:

```bash
cd demos/human/explore
PYTHONPATH=. python -m unittest discover -s tests
```

The older Review and Evaluate service suites require updates for retired task
IDs, private profiles and changed judgment payloads. They are not part of CI.

## Environment checks

See [environment validation](validation/2026-10-02/README.md) for task coverage,
rendering checks and unresolved visual issues.

The [2026-10-01 checks](runtime-validation.json) cover startup and camera movement
in the earlier compiled packages. They do not establish that every scene is free
of native rendering or collision defects.

Automated source tests do not run paid model evaluations or reproduce paper scores.
