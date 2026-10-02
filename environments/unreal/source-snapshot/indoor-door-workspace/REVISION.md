# Indoor H09 and H15 — published

Status: published after the user explicitly authorized ending active sessions and updating. Active release: review-service/releases/indoor-door-vase-20260913-v3. Publication preserved feedback, review history, evidence, logins and participants. Public browser verification passed for H15, H09 and HB03: live video and same-process switching work. The technical session is closed, no feedback was submitted, and the temporary login was revoked.

- H09 revision 33 replaces the hard-to-read displaced sofa shadow with a missing shadow on a large floor vase. A smaller adjacent vase retains a clear shadow under the same room light. Both are grounded and solid. The reviewed positions are in the lit area near the fireplace, not behind the sofa.
- H15 revision 1 is a new C1 / collision.missing task: the bedroom entrance door swings through a stationary storage box. Matched native control stops at 18.67 degrees; treatment crosses the box and opens fully. Opening, closing and reopening work with the actual player interaction.
- H06 is unchanged. H14 plumbing remains deleted. H03 remains the revision 33 oversized stove pot, not a chair.
- Generated ceramic vase geometry and material are authored assets under Content/Auditor/Props; no external asset or attribution dependency was added.

Final build: /home/ubuntu/unreal-auditor/indoor-workspace/dist/indoor-door-vase-20260913-v3
Candidate release: indoor-door-vase-20260913-v3 in this workspace.
Earlier v1 is door-only; v2 vase placement was rejected for poor shadow visibility. Do not publish them.

Validation: 28 paired native checks, 4 rendered cases, 6 region routes, 14 same-process reset cycles, real player door interaction, real player vase approach and collision, pixel comparison of missing versus retained floor shadows, and 142 service tests passed. 45 reviewer histories were checked in isolated database copies. Existing feedback is unmodified; unchanged tasks retain their compatible version aliases. H09 starts a new evaluation version but old history remains available.

Publication scripts: scripts/prepare.py resolves and copies the actual live release, scripts/verify.py validates the candidate and history compatibility, scripts/acceptance.py checks native evidence, and scripts/publish.py checks source/state/candidate hashes, creates a database/configuration backup, and supports rollback. It currently refuses to interrupt active sessions. Only end those sessions after explicit user authorization, then publish and run the public browser smoke test at scripts/indoor-door-public.cjs on the Mac. The public smoke test needs a dedicated short-lived technical login; submit no review feedback and revoke that login afterwards.

Final evidence: out/acceptance.json, out/validation.json, out/shadow-pixels.json, out/play-v3/report.json, out/vase-play/report.json, and the final distribution test directories. Private configuration and login files must not be printed or copied into documentation.
