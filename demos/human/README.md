# Human evaluation services

These directories preserve the code used by the AWS deployment:

- `review/`: task review, rubrics, participant sessions and streaming integration.
- `explore/`: exploration UI, submission collection, scheduling and shared GPU runtime.
- `evaluate/`: human evaluation UI and current binary judgment protocol.
- `threejs/`: static environment serving and original packaging helpers.

Run each Python service from its own directory: Explore and Evaluate intentionally
contain separate versions of the `bf` package. Their imported READMEs include
historical Lambda addresses; the migration receipt identifies the inspected AWS
source. Original one-time deployment scripts need a reviewed path/config mapping
before reuse. No live service or private database was changed during migration.

The full service test results, including inherited failures, are listed in
`../docs/validation.md`. Runtime binaries, streaming infrastructure, private
configuration, user identities and review databases are separate from this source.
