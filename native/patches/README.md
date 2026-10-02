# Native runtime repairs

## Indoor window glass

`indoor-window-glass.patch` repairs the white flashes observed on the house windows
with the October 2 Unreal 5.6 SM5 candidate. At character startup it replaces only
material slots using `M_WindowGlass_Clean` with the same house's existing translucent
cabinet material, `M_Glass_A`. Window frames, geometry, collisions, lights, shadows
and task logic retain their existing settings. Glass tint and reflections change
with the replacement material.

The patch uses assets already cooked into the indoor package. It requires rebuilding
the indoor executable; it does not require recooking the maps or changing the viewer.
The same repair therefore runs in the standalone package, agent runtime and Pixel
Streaming viewer. A missing or non-translucent replacement leaves the original
material in place and logs a warning.

Apply the patch from the recovered indoor Unreal project's root, then build its
`AtmosphericResidentialHou` Linux Development target with Unreal 5.6:

```bash
patch --dry-run -p1 < /path/to/WorldAuditBench/native/patches/indoor-window-glass.patch
patch -p1 < /path/to/WorldAuditBench/native/patches/indoor-window-glass.patch
/path/to/UnrealEngine/Engine/Build/BatchFiles/Linux/Build.sh \
  AtmosphericResidentialHou Linux Development \
  /path/to/project/AtmosphericResidentialHou.uproject
```

The patch is based on `AuditorPlaytest.cpp` with SHA-256
`2b4cce7b0d3792b340cd7f09aefd2b48b1cd17acf87469ca28797c06689dbfb2`.
The resulting source has SHA-256
`2ac1a8dd88ccba62ddec7c84c23d1bdc17e2199fcbd6d31137dafe349af1299f`.
The recovered project and licensed assets are needed for compilation; this patch
alone is not a complete Unreal project.

Update every affected task's executable hash in the package's `launch.json` when
installing the rebuilt binary. Startup logs report `AUDITOR_WINDOW_GLASS_REPAIR`
and the number of material slots changed. `-AuditorOriginalWindowGlass` temporarily
retains the original material for controlled comparisons.

The source patch does not change the published download manifest. See the
[validation record](../../docs/validation/2026-10-02/indoor-window-glass.md) for the
candidate identity, measured checks and remaining limits.
