# Rendered Unreal environment service

Verified with the residential Linux release on 2026-09-09: 17 rendered operator
checks and 16 external checks through an SSH tunnel passed, alongside six region
checks and all 20 authored task checks. This is the environment server; it does
not implement agent inference. Existing Mac applications have not been rebuilt
with this interface.

The Python service starts one packaged Unreal process. It binds HTTP to
`127.0.0.1:9100`; callers on a different machine use an SSH tunnel. A private local
directory carries commands between Python and the native `AuditorRemote`
subsystem. PNG image bytes are returned over HTTP, so callers do not need access
to the environment server's filesystem or assets.

## Start and connect

Run on the environment host, using the paths of the operator's restored project:

```sh
python3 -m auditor.environment_server \
  --binary /path/to/dist/residential-regions-linux/Linux/AtmosphericResidentialHou.sh \
  --regions environments/residential-house/regions.json \
  --tasks environments/residential-house/tasks.json \
  --state-directory /path/to/private/runtime-state
```

On the agent host, use its own authorized SSH key:

```sh
ssh -N -L 9100:127.0.0.1:9100 USER@UNREAL_SERVER_IP
```

The agent host then calls `http://127.0.0.1:9100`. This initial instance runs one
episode at a time. Independent simultaneous agents require separate instances
or processes, ports and state directories.

## Browser controls

After opening the SSH tunnel, visit `http://127.0.0.1:9100/` for the manual
viewer. Select a region and task, then enter the environment. Movement buttons
advance 50 cm; turns use 30 degrees and pitch uses 15 degrees. The page displays
the returned observation and pauses between actions. Reloading the same tab
resumes its episode. The viewer shares the single episode with API clients; use
one controller at a time. The root page requires `environment_viewer.html` next
to the Python server module.

## Requests

- `GET /health`: process liveness and whether an action is in progress.
- `GET /tasks`: baseline names and task IDs with region names. No bug answers.
- `POST /reset`: `{"request_id":"reset-1","task_id":"living_room","seed":123}`.
  Baselines are `living_room`, `kitchen_dining`, `bedroom_suite`; bugs are H01–H20.
  Returns an `episode_id`. Later resets must include the active `episode_id`.
- `POST /observe`: `{"episode_id":"..."}` returns the cached observation without
  advancing simulation. Returns 409 during an in-progress action.
- `POST /step`: `{"episode_id":"...","request_id":"step-1","action":{"name":"turn","degree":45}}`.
- `POST /state`: `{"episode_id":"...","request_id":"state-1"}` is an operator
  diagnostic. Reads the paused simulation clock, pose and actor transform digest
  without requesting a new render or advancing time. Disabled by default (403);
  operators can temporarily start the service with `--enable-diagnostics`.

| Action object | Behavior |
| --- | --- |
| `{"name":"move_up","distance":100}` | Forward 100 cm with character collision; integer 1–2000 cm |
| `{"name":"move_down","distance":100}` | Backward, same units and bounds |
| `{"name":"turn","degree":45}` | Relative yaw; right positive; integer −360 to 360 |
| `{"name":"look","degree":15}` | Relative pitch; down positive; resulting pitch clamped to ±80° |
| `{"name":"interact"}` | Attempt the existing reachable interaction |
| `{"name":"idle","time":"1s"}` | Advance the stationary world; 1/30 to 10 seconds |
| `{"name":"flag","bug":"description"}` | Attach a report to the current observation and pose; no world advancement |
| `{"name":"done"}` | Finish the episode and return its flags; no world advancement |

A response contains an observation ID, base64 PNG in `rgb`, camera and character
pose in centimeters, yaw/pitch in degrees, simulated time, pause state, actual
travel distance and an action outcome. `frames` contains timestamped intermediate
PNGs, sampled about every 0.5 simulation seconds during longer actions. The main
PNG includes the region HUD. No target actor names or correctness labels are
included. `actor_state_digest` is available only through the optional operator
diagnostic endpoint and is omitted from agent observations.

Movement uses the existing 30 cm radius/180 cm tall character capsule and
220 cm/s walking speed. Turning uses 90°/s and one final tick to update camera and
view-dependent task behavior. Simulation uses 30 Hz fixed steps. Requested idle
time is rounded up to a whole step; responses report the actual simulated time.
Gameplay pauses during image capture and while the caller reasons. Pausing is
validated against the current scene; newly added assets that tick while paused
or use real-time material animation require their own audit.

## Retries and failures

Use a unique `request_id` for each mutation. Retrying the identical request
returns its original response. Reusing the ID with different data returns 409.
Requests that conflict with an in-progress action return 409 and can retry later.
The service caches 256 mutation responses; an older executed request returns 410
rather than executing again. A timed-out backend action stops the Unreal process
so a delayed command cannot race another action. Restart the service after a
backend failure. Episode state and retry history do not survive service restart.

## Verification

```sh
python3 -m unittest tests.test_environment_server
python3 scripts/test_environment_http.py --output /path/to/http-test-results
```

The first command verifies request handling using a fake backend. Only the
second command requires Pillow and temporarily enabled operator diagnostics. It
checks real rendered observations, movement, angle signs,
intermediate frames, frozen world state, retries, flags, done and a bug reset.
Its `--fixture` option explicitly labels a synthetic probe; it does not establish
that the residential Linux release works. Existing boundary/traversal and all
20 authored bug checks remain required against the packaged Linux executable.
After disabling diagnostics and restarting, use `--public-only` for the external
client check; this mode checks cached observations but cannot independently
inspect the live simulation clock or actor transform digest.
