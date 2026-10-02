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

## Website

The initial migration could not enable Pages while the repository was private.
The repository is now public and the project page is published from `gh-pages`.

## Runtime release validation — 2026-10-01

- The installer maps all 126 Unreal paper tasks to the exact executable hashes in
  the experiment profiles, including the later residential and Urban IPC builds.
- Four resource-installer tests cover archive/executable checksums, idempotent
  restoration, traversal/link rejection, and complete task-to-build mapping.
- Source suite after adding the resource installer: **177 passed, 13 skipped**.
  After restoring the ICL images through the public HF download: **187 passed,
  3 skipped**.
- All ten newly packaged Unreal archives were extracted and launched through
  `scripts/serve_unreal.py` on AWS A10G. One assigned task per archive returned a
  PNG on reset and a changed image after a 30-degree turn. See
  [runtime-validation.json](runtime-validation.json) for the exact tasks.
- Restoring the residential archive completes all 126 local Unreal task profiles.
- The separate HF Space passed rendering and movement checks for H01, H06, H07,
  H12 and H13 at 1920×1080 on T4. Its eight session/API/stream tests passed.
- These checks do not re-run the paper's paid model evaluations or establish that
  the archived editor source can reproduce every binary.
