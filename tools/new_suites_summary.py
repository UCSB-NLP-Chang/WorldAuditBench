#!/usr/bin/env python3
"""Summary of the AF / WL / CT bug suites (reports/new-suites-0908.md): per-case table from the answers files and,
when present, the S1 pilot results (reports/<suite>/s1-pilot-30b.md is appended verbatim)."""
import json, pathlib, re, sys
REPO = pathlib.Path(__file__).resolve().parents[1]
SUITES = [("af", "airfield-suite", "Sketchbook airfield", "03_sketchbook_airfield_constrained.html"),
          ("wl", "wilderness-suite", "Beyond Fable wilderness (world seed 7)", "13_beyond_fable_wilderness_constrained.html"),
          ("ct", "cottage-suite", "Mistwood Cottage", "01_mistwood_cottage_constrained.html")]
VERIFIED = {  # how each case type was checked (bridge smoke / behaviour verifier / catalogue screenshot)
    "airwall": "bridge: walk blocked (clean walk passes)", "hole": "bridge: drop + respawn counted", "ghost": "bridge: walks through (clean blocked)",
    "unload": "bridge: hidden after visit + leave", "statereset": "bridge: position flips after visit + leave", "lodpop": "bridge: proxy shown far, detail near",
}
out = ["# AF / WL / CT bug suites (2026-09-08)\n",
       "Three new 17-case catalogues, same taxonomy as SP / HS / WT (15 shared types + 2 environment-specific), each page driven by the shared",
       "harness contract `candidate_environments/src/common/harness_page.js`.  Builds: GitHub release envs-2026-09-08d (see",
       "`candidate_environments/BUILDS.md`); a case is viewed with `?bug=<id>` and run with `audit_<id-prefix>_bug` (90 steps).\n"]
for pre, rdir, title, page in SUITES:
    out.append(f"## {title} (`{pre}`) - `candidate_environments/{page}`\n")
    out.append("| id | name | category | where | verification |\n|---|---|---|---|---|")
    for c in sorted((REPO / "env" / "configs").glob(f"{pre}[0-9][0-9]-*.answers.json")):
        a = json.loads(c.read_text())[0]; cid = c.name.split("-")[0]; slug = c.name.replace(".answers.json", "").split("-", 1)[1]
        ver = VERIFIED.get(slug, "catalogue screenshot")
        out.append(f"| {cid} | {a['name']} | {a['category']} | {a['where']} | {ver} |")
    out.append(f"\nCatalogue sheet: `reports/{rdir}/catalog/catalog.jpg`.\n")
    pilot = REPO / "reports" / rdir / "s1-pilot-30b.md"
    if pilot.exists():
        out.append(f"### S1 pilot (Qwen3-VL-30B, f2 film, 90 steps, 17 bugs x 1 + clean x 2)\n")
        out.append(pilot.read_text().strip() + "\n")
    else:
        out.append("### S1 pilot: not run yet\n")
(REPO / "reports" / "new-suites-0908.md").write_text("\n".join(out) + "\n")
print("wrote reports/new-suites-0908.md")
