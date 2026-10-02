# Ancient Chinese City: public scene context

The scene depicts everyday life in an ancient Chinese city.

The shared bilingual paragraphs in scene-descriptions.json define normal behavior and are identical for each scene's baseline and all bug tasks. They do not reveal a task's injected change.

- Market: stalls, tables and benches are fixed. Loose paper umbrellas are physics-enabled and may be nudged; they should settle naturally. Aim at the separate wicker basket and press E to give it one gentle horizontal push; it remains stationary before E and settles afterward.
- Tea house: tables, benches and hanging lanterns are fixed. No E interaction or deliberately pushable props.
- Residence: stone lions and hanging lanterns are fixed. One door leaf starts open and the other closed. E toggles only the targeted leaf independently; both swing inward. The stairs are traversable through an open leaf.

Expected motion is not a waiver for excessive impulses or unexplained flight. Authored physics configuration was inventoried in out/scene-context/physics-inventory.json: within the Market bounds, 15 SM_umbrella_01 and 6 SM_umbrella_02 components have simulation enabled. Hanging lanterns within TeaHouse/Courtyard bounds do not. This inventory verifies intended mobility, not physical quality under every possible collision.
