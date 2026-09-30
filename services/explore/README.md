# Blind bug finding: single-case pilot

Two independent Python applications for blind exploration and human evaluation.
The pilot imports an existing Unreal review case and reuses its packaged binary.
It does not copy the legacy review coordinator or use its database.

## Deployment

- Exploration: `https://explore.150-230-45-149.sslip.io`
- Evaluation: `https://evaluate.150-230-45-149.sslip.io`
- Remote root: `/home/ubuntu/unreal-auditor/bug-finding-pilot`
- Source release: `releases/pilot-v1`
- Case is selected by `ops/prepare_pilot.py --case`; current pilot uses S01.
- Credentials are provisioned separately, never checked into this source tree.

| Component | Port / state |
| --- | --- |
| Exploration API | loopback 8102; `exploration-state/exploration.sqlite3` |
| Evaluation API | loopback 8103; `evaluation-state/evaluation.sqlite3` |
| Isolated supervisor | loopback 19092 |
| Player / streamer / SFU | 18182 / 18982 / 19992 |
| Unreal writes | `runtime-state/sessions/<id>/user/`, explicit absolute logs and IPC |
| Evidence | each application's own `state/evidence` directory |

Both applications have independent systemd units, cookies, credentials, database
connections, schema migrations and evidence directories. Systemd makes the rest
of the filesystem read-only and hides the other application's private state and
configuration, operational backups, and the legacy review state/release directories.

The existing Caddy and TURN are shared transport dependencies. Two new host routes
are added with graceful Caddy reload after checking that the existing review route
is byte-for-byte equivalent as a JSON object. Legacy application processes, systemd
units, task manifests and databases are not modified. No firewall change is required.

## Application boundaries

- `bf/exploration.py`: allowlisted public tasks, attempts, optimistic-versioned
  drafts, image ownership, immutable submissions and transactional outbox.
- `bf/evaluation.py`: immutable reference versions, independent answer/evidence
  copies, leases, human judgments and append-only judgment history.
- `bf/contracts.py`: version 1 HTTP transfer envelope and judgments vocabulary.
- `bf/delivery.py`: bounded internal HTTP import, retry and acknowledgment.
- `bf/runtime.py`: start/status/stop adapter, session ownership, cleanup and priority.
- `bf/runtime_supervisor.py`: compatibility snapshot of the previously running
  review supervisor, with a dedicated Unreal UserDir. Its source was the deployed
  `subway-s16-poster-hide-20260915-v2` release. It has no review database dependency.
- `bf/http.py`: explicit per-application routes, authentication, CSRF origin checks,
  static-file allowlists and authenticated streaming.
- `web/exploration`: native video-frame Flag capture, IndexedDB upload retry,
  saved draft restoration and final answer UI.
- `web/evaluation`: query/reference/answer comparison and human judgment UI.

`Database` contains only shared infrastructure and per-service auth tables. It never
connects to another service's database. Database schema version 2 adds a server-set
QA cohort; normal evaluators cannot list or claim QA submissions.

## Data flow

1. Import a source manifest entry and its matching launch profile. Bind query,
   map SHA256, binary SHA256 and rubric to an immutable opaque task version.
2. Store only the public task in Exploration; register the private reference in
   Evaluation. Runtime config contains map/binary routing, never rubric text.
3. On final submission, save an immutable envelope and outbox row in one SQLite
   transaction. Technical issues remain operational records and are not graded.
4. Evaluation validates the envelope, fetches evidence from a fixed internal
   endpoint, validates PNG contents and hashes, and saves its own copies. Only
   complete imports enter the review queue. Submission ID/content hash make retries
   idempotent; conflicting contents are rejected.
5. Human evaluators claim a five-minute renewable lease and grade every report.
   Updates require the current judgment revision and append to history.

Final reports require a description and at least one saved image. A `none` outcome
has no reports and is evaluated separately. Evidence not selected in a report is not
transferred. No automatic score or model judge is included.

## Reusing existing review environments

The importer accepts `--review-root` and `--case`, reads the existing `tasks.json`
and `runtime.json`, and selects the matching `launch_profiles[map]`. It preserves
the packaged binary path and verifies its SHA256 before launch; it does not edit
the package, maps or source project. Old rendering controls and task-switch IPC
remain supported. All game writes go to the new runtime's writable directory.

For the next case, publish a new immutable task/reference and add its launch profile
through this same boundary. The current UI assigns one configured case; batch
assignment and task selection are intentionally not part of the single-case pilot.
The adapter currently supports Unreal Pixel Streaming. Browser/Three.js adapters
are a separate future implementation, not advertised as working by this pilot.

## Legacy-serving priority

The pilot admits only one exploration runtime. It refuses to start while any old
review player port is listening, or when free VRAM is below 12 GB or GPU utilization
exceeds 25%. During exploration it checks legacy player ports every two seconds and
stops only its own game if old review work starts. Drafts/evidence are preserved.
Session expiry: two minutes without heartbeat; maximum runtime: thirty minutes.

This is a conservative pilot admission policy, not a global GPU scheduler. Both
systems share the physical GPU and relay, so zero transient hardware contention is
not a mathematical guarantee. Before allowing simultaneous larger-scale sessions,
replace this adapter with a shared resource allocator or use another GPU machine.

## Verification and operations

```sh
python3 -m unittest discover -s tests -v
BF_HEADED=1 node ops/browser_acceptance.cjs /path/to/private-accounts.json /path/to/evidence
```

Use visible Chrome for pointer-lock acceptance: macOS headless Chrome can reject
pointer lock with `WrongDocumentError` despite successfully streaming video.
The browser test uses its own QA accounts. It exercises real HTTPS, real streamed
Unreal video, movement keys, pointer lock, F capture, draft recovery, independent
evidence transfer and human judgment. It does not submit legacy review feedback.

Back up each service independently, without stopping it:

```sh
python3 ops/backup.py /path/to/exploration-state /path/to/backups --app exploration
python3 ops/backup.py /path/to/evaluation-state /path/to/backups --app evaluation
```

Each backup uses SQLite's online backup API, checks integrity and copies exactly
the evidence referenced in that snapshot. Restore only with the corresponding new
service stopped; retain its current directory before replacing it. Configuration
and credentials require separate private backups; never put them in source control.

To stop the pilot, stop only `bug-finding-exploration` and `bug-finding-evaluation`.
To remove public access, remove only the marked pilot host blocks and gracefully
reload Caddy after checking its current configuration. Do not restore a stale whole
Caddy configuration over changes made by other work.

Known pilot limits: one case, one runtime, manually provisioned accounts, one primary
rubric item and one evaluator per answer. Flag images are browser-captured evidence,
not cryptographic proof of an uncompromised client. History is retained; administration
and adjudication UIs are follow-up work.

### Viewer alignment correction

Exploration `input-bridge.js` now follows the deployed auditing bridge: the Epic
player owns pointer lock on its video parent. Do not globally override
`requestPointerLock` or lock the VIDEO directly. Capture remains a separate bridge.
The desktop workspace fixes the game area to the viewport and scrolls evidence
and reports in the sidebar; narrow screens retain a stacked layout. Launch profiles
inherit the auditing frame rate/bitrate. Runtime storage, DBs and legacy priority
remain isolated. Signalling reconnect has a 10-second disconnect grace period;
video readiness in the UI requires recently decoded frames.

Regression: `node tests/test_pointer_lock.cjs` exercises actual deployed Epic
lock callbacks, including release and recapture; `PYTHONPATH=. python3 -m unittest
discover -s tests -v` covers data boundaries and reconnect cleanup. The native UI
smoke test confirmed live video and Flag upload. Continuous physical mouse-look
still requires manual acceptance; a non-null pointer lock alone is insufficient.

### Screenshot deletion and report categories (feedback-v3)

`POST /api/attempts/{id}/delete-flag` accepts `{id, version}` for an owned draft.
Deletion removes the flag and its report references in one transaction and advances
`draft_version`. A `deleted_flags` tombstone prevents delayed/retried uploads from
resurrecting it; archived bytes remain on disk for operator recovery but cannot be
fetched through the evidence API. Submitted answers cannot be edited or deleted.

`bf/taxonomy.json` contains only the shared public taxonomy (5 groups / 16 subtypes),
without case mappings. `/api/taxonomy` provides the same definitions to both apps.
Reports store a category code plus description and evidence IDs. Missing category
on older drafts/envelopes remains compatible as `unsure`; `other` is also allowed.
The exploration guide explains all subtypes and does not select a case's category.
Evaluation labels the category as the explorer's own selection.

Validation: 27 Python tests including category delivery, delete ownership, stale
versions, final-answer protection and cancelled upload retry. Native Chrome QA
confirmed the complete menu, expandable guidance, screenshot removal and unlinking.

### Bilingual instructions and type picker (instructions-v4)

The exploration report uses category buttons followed by only that group's
3–4 subtype buttons. Existing subtype codes remain unchanged. Selecting a broad
group without a subtype saves `unsure`, explicitly shown in the UI. The guide
language also switches picker labels, subtype explanations and description
placeholders; existing report text and selected subtype are preserved.

`bf/instructions.json` and `bf/taxonomy.json` are the sources for the in-page guide
and authenticated `/api/instructions/{zh,en}.md` downloads. `bf.instructions.markdown`
generates complete plain Markdown, including all taxonomy definitions and a report
template; exported copies are in `docs/exploration-instructions.{zh,en}.md`.
This switch localizes the instructions and report classification, not the whole app.

28 Python regression tests passed, plus pointer-lock regression. Native Chrome QA
verified group filtering, subtype selection, English switching, saved selection
and expanded English instructions. Only exploration was restarted; review and
evaluation service fingerprints were unchanged.

### Authoritative taxonomy (taxonomy-v5; supersedes the earlier subtype picker)

New reports select one of the five categories from game-auditing's
`agent/prompts.py::TAXONOMY` at commit d59b663ddb210414bc0cd5ce66cab0f0fd04f76a.
English names, descriptions and the normal-content principle reproduce that text
verbatim; Chinese is a corresponding translation. The page, selected-category
explanations and Markdown instructions share `bf/taxonomy.json`. There is no new
16-subtype classification step. Other/Unsure remain reporting fallback options.

Existing subtype codes are accepted and displayed as historical labels, without
rewriting saved drafts or immutable submissions. Selecting a category explicitly
updates a draft to a five-category code. The evaluator accepts both generations.
29 regression tests cover exact source text, new category delivery, legacy codes
and existing workflows. `tests/prompt-taxonomy.txt` is the pinned upstream fixture.

### Evaluation review (evaluation-v6)

Evaluation shows the same bilingual taxonomy and a reviewer guide, each reported
category with its definition, numbered evidence, and separate bug-validity and
category judgments. Category verdicts: correct, incorrect, uncertain, not_applicable.
An incorrect category requires a suggested five-category code (or other). This
never mutates the explorer's submission. Older judgments remain readable with
not_reviewed; the UI requires completing category review when saving report judgments.
No-bug submissions do not require category review. Existing judgment revisions and
history store the additional fields without a database schema migration.

31 tests passed, including valid bug + wrong category, correction validation,
unchanged submissions and revision history. Only the evaluation unit is updated;
exploration remains on taxonomy-v5 and legacy auditing remains untouched.

### Accounts, task access and progress (progress-v7)

Schema v3 adds administrator/test identity flags and per-case task access in each
independent database. A synchronized offline access plan assigns one role per case:
the five new accounts explore; the seven existing audit accounts review. Accounts
are created in both apps, but an account without the relevant case role cannot
start that case, claim its submissions, read its rubric or evidence. Same-case
role conflicts and self-review are blocked. Login names are case-insensitive.

Run ops/provision_access.py only during a coordinated maintenance window; it reads
the audit roster/shared access code without writing legacy files, hashes passwords
into both new databases, synchronizes identical case roles, and validates both
copies. config/access-plan.json records the role plan. There is no public signup,
password editor, permission editor or bulk assignment endpoint.

testuser is an administrator in both apps and belongs to the QA/acceptance cohort;
the existing password and account ID are preserved. It has the explorer role for
the pilot case; management progress does not bypass rubric/answer access checks.
qa-explorer and qa-evaluator remain separate identities. Historical testuser
submissions retain their immutable envelope: submission_authors metadata records
identity/cohort for queue and progress filtering.

GET /api/progress supports assigned, mine, and admin-only all scopes. Formal and
QA cohorts are isolated. Exploration counts assigned cases once even after repeat
attempts, and lists attempt history. Evaluation counts received submissions,
normalizes active leases, and uses only the latest saved judgment for distributions.
Progress projections never include rubric, report descriptions or judgment reasons.
Ordinary reviewers see their assigned case queue; My reviews counts their own claimed answers; case progress aggregates all authorized cases. Admin people views include assigned-case counts and workload;
unclaimed group work is not multiplied across reviewers.

The frontend opens on tasks/queue, so login no longer creates an attempt. Opening
an assigned task explicitly starts or resumes it. Multiple cases can have separate
drafts; the runtime remains a single isolated pilot slot. Task catalog and explicit
task IDs support additional cases, while importing their builds/references remains
a separate controlled operation. Historical activity timestamps fall back to
attempt creation time when no saved timestamp previously existed.

### Audit-aligned interface (audit-ui-v8)

Both sites use the deployed Auditor's light header, minimal sign-in and Overview / Task progress / task workspace navigation. The shared UI foundation lives in `web/shared/style.css` and navigation in `web/shared/progress.js`. Overview contains summary cards; task progress contains filterable history with expandable judgment distributions. Admin progress remains role-gated. This release changes only frontend assets; databases, access rules and the old Auditor serving are unchanged.

### Full audit catalog (all-tasks-v9)

Imported 258 current cases (153 Unreal, 105 Three.js), including clean controls. Each formal explorer receives all cases; reviewers receive the matching case permissions in their separate database. Case IDs, bug titles, control labels and reference rubrics stay out of public task metadata. Existing task versions/submissions remain immutable.

`ops/import_audit_tasks.py prepare` stages configs and independent browser assets from read-only audit files. `apply` registers versions and mirrors role assignments while services are stopped; `ops/deploy_all_tasks.py` backs up configs/databases and restores them on failure. The staged private configs/catalog are inaccessible to application units.

Unreal reuses all audited launch profiles with independent writable state and continues yielding GPU priority to auditing. Browser sessions use the client's GPU, have per-user authorization and do not reserve the Unreal slot. Sponza/Family House use an exploration-only entry with only the current config and no answers files; the other native bundles retain their game entry with informed-review overlays disabled/removed. Browser simulation code necessarily runs on the client; this does not provide server-side secrecy of game mechanics. No ground-truth rubric is sent to the exploration app.

### Per-case participation and team overview (group-progress-v10)

The overview shows team totals for the selected cohort; testuser defaults to formal data. Each case shows distinct completed explorers / assigned explorers, distinct reviewers who saved a judgment, and completed / received answers. Retries, repeated submissions and judgment revisions do not inflate person counts. Claims and page views do not count as completed reviews. Case identity is used internally to deduplicate versions; public exploration projections contain only opaque IDs and numeric counts. No reviewer opinions, names or reference text are shared with explorers.

`bf/group_progress.py` computes local aggregates and retrieves the other app's count-only snapshot through the authenticated loopback `/internal/progress` endpoint. Each service reads only its own database. Peer aggregates are cached in memory for 10 seconds; unavailable metrics remain unknown rather than becoming zero. Existing UI refresh runs every 30 seconds. No review quota or automatic acceptance threshold was introduced.

The release also removes creation of the obsolete one-draft-per-owner index during schema initialization. The existing per-owner/per-task draft constraint remains in place, allowing restart with multiple task drafts. Regression coverage includes restart preserving drafts, people/revision/version deduplication, cohort boundaries, private-data projection and unavailable-peer behavior.

### Case-first progress (case-progress-v11)

Task progress has one row per case, including cases with no answers. Columns distinguish completed/assigned explorers, submitted answers, reviewed/received answers, and distinct reviewers. Expand a case to see authorized records: explorers see only their own attempts, while reviewers see permitted answer metadata and existing open/claim actions. Personal task actions and the admin people view remain separate.

A case is complete only when all assigned explorers have submitted and every submitted answer has reached evaluation and been reviewed. Missing peer statistics remain unknown. Grouping uses canonical case IDs across task versions. The pure grouping/status module is tested with `node tests/test_case_progress.mjs`; this release does not change database schemas.

### Participation without quotas (participation-progress-v12)

Supersedes the v11 all-assigned completion rule: assignments grant access, not a per-case participation quota. Exploration coverage counts cases with at least one final submission / accessible cases. Explorer participation counts distinct person-case submissions without an assigned-person denominator. Case status describes outstanding submitted answers; all delivered answers reviewed is labeled “当前答案已复核”, and further exploration/submission remains allowed. `fully_reviewed_cases` requires at least one submission and no delivery or review backlog.

### Explicit sessions and FIFO admission (session-controls-v13)

Exploration uses Start session / End session independently from answer submission. One account can hold one queued or active session across both engines. Repeated Start is idempotent for the same attempt. Unreal enters a FIFO queue, shows its position, and is admitted only when the independent single slot and GPU guard allow it; legacy audit retains priority. Starting and closing sessions occupy the slot until teardown is confirmed. Three.js runs on the client and does not consume that GPU slot.

The default heartbeat timeout is 180 seconds and maximum session age is 3600 seconds, matching audit's defaults. Existing streaming disconnect grace is 10 seconds. Expired queues, logout, final submission and End session release the account's reservation. Queue dispatch rechecks task permissions. Queue/session ownership remains process-local: service restart ends sessions and waiting users must Start again; durable attempts, screenshots and submissions remain intact. No audit DB, limits, units, ports or task configuration are changed.

### Explorer onboarding (explorer-onboarding-v14)

Explorer overview begins with a four-step bilingual guide and task selection button. Team statistics are collapsed below the guide. Personal task lists explain selection and repeat attempts, prioritize actions, and become labeled cards below 700px. This release changes only exploration frontend assets; roles, databases, runtime controls and evaluation serving remain unchanged.

### Account selector (login-select-v15)

Both login forms use a required name selector populated from their own service database through public GET /api/login-users. The endpoint returns account names only; password verification, rate limits and task permissions are unchanged. Loading failures leave sign-in disabled with a refresh prompt. Exploration stages from explorer-onboarding-v14b; evaluation stages from participation-progress-v12. Activated exploration from `releases/login-select-explore-v15` and evaluation from `releases/login-select-evaluate-v15`. Exploration passed 59 tests; evaluation passed 51 tests with its original runtime expectations retained. Public checks verify each selector against its own database, valid login, rejected incorrect passwords, and preservation of business data.

### Category-guided human allocation (guided-exploration-v17)

Human tasks expose only the allowlisted ground-truth category and the existing bilingual generic category definition, never specific rubric text. Immutable task/reference versions remain unchanged. Category guidance is a separate configuration projection derived from the original matching audit release. New claims exclude controls and unmapped categories; old attempts and evidence remain readable.

`bf/allocation.py` persists one claim per person and per case/cohort, with a 180-second renewable lease and 60-minute maximum age. Next resumes an existing claim; otherwise it ranks authorized bug cases by global terminal participation count, then last attempt time and ID. Submitted, skipped and technical attempts count toward exposure balancing; own previously handled cases are excluded. Concurrent claim selection/draft/reservation writes are serialized under the store lock and SQL transaction. Manual task starts and runtime starts respect the same claims.

Normal report submission remains immutable and is delivered to the independent evaluation DB with category-guided protocol metadata. Giving up uses `skipped`, retains drafts/evidence, produces no report/outbox message, and does not inflate successful-report coverage. Next runs after submission or giving up; it allocates a task but still requires explicit Start session for the environment. Cohorts remain separate; no five-person completion quota exists.
