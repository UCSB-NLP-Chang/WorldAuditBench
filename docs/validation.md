# Migration validation — 2026-09-30

## Paper code

- With the original AWS ICL image pack and native-client runtime present:
  **183 passed, 3 skipped** across `agent/tests` and `tests`.
- Source-only checkout: **173 passed, 13 skipped**. Ten additional skips require
  the pending ICL images/native runtime. The other three are existing browser/live
  integration tests. No model API calls or Unreal sessions were started.
- Every imported Python file was parsed successfully during migration.
- `scripts/check_release.py` verifies the exact 213-task cohort, engine/family
  totals, split lists, and released hashes of the imported source files.
- The source scan checks the exact staged text for recognizable credential formats,
  credential-bearing URLs, private keys and unexpected database/credential files.

The only agent test correction updates the expected Sponza and Cottage counts to
reflect cases already retired in the imported task lists. Runtime code was not
changed to make those counts pass. Native setup now uses the bundled, hash-pinned
`agent/` source instead of cloning a second private repository.

## Imported human services

Commands were run separately from each service directory:

```bash
PYTHONPATH=. ../../.venv/bin/python -m unittest discover -s tests
```

| Service | Outcome |
|---|---|
| Explore | 70 tests passed |
| Review | 156 tests ran: 147 passed, 5 failed, 4 errored |
| Evaluate | 51 tests ran: 44 passed, 7 errored |

The Review failures refer to the retired S1 taxonomy, an older task catalog, and
S22 becoming valid after an older rejection test was written. Three errors require
the old Lambda Ancient workspace; another requires a private runtime profile.
The Evaluate errors submit the old judgment payload to the newer version-2 binary
judgment API. These tests and production service implementations are preserved as
received; the migration does not claim those suites pass. CI runs the paper source
suite and passing Explore contracts; it does not hide these other results.

## Not verified

- Full benchmark execution, GPU rendering, native navigation, or reproduction of
  paper scores after relocating runtime resources.
- Rebuilding every Unreal binary from the recovered source snapshot.
- Hugging Face downloads; that release is pending.
- A live GitHub Pages site: branch preservation succeeded, but GitHub returned
  HTTP 422 because the private repository's current plan does not support Pages.
