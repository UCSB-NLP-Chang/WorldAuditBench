# Narrower cabinet interaction range

The user reported that the first cabinet interaction range was too large. This revision changes only CabinetAvailable() thresholds: 250 to 150 cm and 35 to 18 degrees (viewing half-angle). It retains the upper-right E Open cabinet / Close cabinet prompt, visibility checks and shared prompt/action resolver.

The existing cabinet test now checks that the previous distant trigger and 25-degree offset are rejected, while a closer approach with a 10-degree offset still opens/closes the panel and updates the hint. Task criteria, anomalies and all other interactions are unchanged. Prior Indoor review versions remain compatible.

Source and build are authoritative on A10. Original source is in backup/ResidentialScenario.cpp. New distribution: ../indoor-workspace/dist/indoor-cabinet-range-20260914-v1. Publication status, backup, validation and public browser verification are in out/. Always resolve the current live service via systemd before publishing future changes.
