# Indoor window flash repair — October 2, 2026

The rebuilt indoor candidate now replaces the house's unstable clean-window
material with its existing translucent cabinet-glass material. The original
material produced intermittent white rectangles in stationary views of the porch
windows. Removing only the glass in a diagnostic build removed those flashes;
replacing its material preserved the panes and frames while removing the observed
white flashes. Glass tint and reflections differ from the original material.

The [source patch](../../../native/patches/indoor-window-glass.patch) changes only
slots with the exact `M_WindowGlass_Clean` asset path. It replaces 35 slots in the
sampled maps. It leaves global rendering settings, lights, shadows, geometry,
collision, movement limits and task logic as configured by the original program.
It reuses cooked assets and requires a new executable, without a map recook.

## Candidate identity

- Original indoor executable: `f32877144f68bdc9f6da15492aca46003c80f2555e3dcb5877b1696ef09966c2`.
- Repaired executable: `2ea49098a467519e3749beecec714bae527d37c9de37991292b3d815ad1d5e90`.
- Build label: `2026-10-02 candidate · window glass fix`.
- The AWS viewer uses this executable for all 14 indoor tasks. Other environment
  packages keep their previous candidate executables. Public download artifacts
  have not been replaced by this candidate.

The recovered indoor runtime module compiled and linked successfully against its
existing UE 5.6 build objects. The source patch also passed a reverse dry-run
against the compiled source, confirming that the published patch matches it.

## Checks

The final executable was compared with itself using
`-AuditorOriginalWindowGlass` as the control. Both modes used the same map, pose,
action sequence and default rendering settings at 1280×720 on an A10G. Each run
settled for ten simulated seconds before capture. Frames were sampled after 0.1
seconds of simulated idle. The second view additionally moved 180 cm and turned
−15°, then settled for five seconds.

| Stationary view | Frames per mode | Window brightness range, original → repaired | Pixel temporal standard deviation, original → repaired |
| --- | ---: | ---: | ---: |
| H01 porch spawn | 160 | 22.79 → 2.63 | 10.26 → 2.18 |
| H01 oblique view | 120 | 6.03 → 1.93 | 3.26 → 1.60 |

Brightness is the mean RGB value in the window region, on a 0–255 scale. The
reported range is its maximum minus minimum across frames. Temporal standard
deviation is calculated per RGB channel and pixel, then averaged over the region.
Exact image coordinates, poses and results are in the
[measurement record](indoor-window-glass.json).

H01, H02, H11 and H12 covered LivingRoom, KitchenDining and BedroomSuite. Control
and repaired runs matched initial and final actor-state digests, camera poses and
simulated times. H02, H11 and H12 checks included startup, ten seconds of idle and
four additional sampled frames. These are limited regression checks; an actor
state digest does not establish material equivalence or every task trigger.

An independent Pixel Streaming session served the final executable at 1280×720.
Its stationary window was sampled 240 times over 25.91 seconds of advancing video.
The window's brightness range was 2.21, the original white flashes were not seen,
and the browser reported no JavaScript errors. The native repair log confirmed
35 changed material slots.

Earlier short tests of disabling screen-space reflections appeared better but
failed on longer repeats. Those settings were not adopted. The shipped repair
contains no global exposure, shadow, reflection or anti-aliasing overrides.

This clears the reproduced window flash on the sampled routes. Small temporal
noise remains, and other reported native scene defects require their own checks.
