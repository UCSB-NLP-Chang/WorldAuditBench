"""Build a browsable page from a directory of agent runs.

    python -m agent.vlm.dashboard runs/<tag> --open        # one tag
    python -m agent.vlm.dashboard runs --open              # every run under runs/ (recursive)

Writes `index.html` in the directory. The page is self-contained apart from the frames, which
it references in place (relative paths), so it opens from `file://` with no server. It is a
snapshot: re-run after new episodes.

Each episode is shown as its transcript: one block per model call with the model's text, every
tool it called (environment actions with their film strip / final frame, inspect with the frames
it brought back, flag_bug / update_bug with the ledger state, write_notes, history, done),
compaction events with the rewritten notes, plus a top-down path and the final bug ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

ENV_ACTIONS = ("move", "turn", "look", "interact", "wait")


def _jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


_REGION = re.compile(r"region \[([0-9., ]+)\]")


def _frames_from_parts(parts: List[dict], frames_idx: Dict[str, dict], prefix: str, archive=None) -> List[dict]:
    """Image parts of a transcript user message -> [{ref, caption, url, kind, t_sim}]. For runs recorded
    before inspect crops were archived (ref = parent frame, caption carries the region) the crop is
    derived here - it is deterministic - so the page shows what the model actually saw."""
    out, caption = [], ""
    for p in parts:
        if p.get("type") == "text":
            caption = p["text"]
        elif p.get("type") == "image_ref":
            ref = p.get("ref", "?")
            m = _REGION.search(caption)
            if m and "#" not in ref and archive is not None and archive.has(ref):
                region = [float(v) for v in m.group(1).split(",")]
                ref = archive.put_derived(ref, archive.get(ref, region), region)
                frames_idx[ref] = archive.info(ref)
            info = frames_idx.get(ref, {})
            out.append(dict(ref=ref, caption=caption, kind=info.get("kind", "?"), t_sim=info.get("t_sim"),
                            url=f"{prefix}/frames/{info['file']}" if info else None))
    return out


def load_run(run_dir: Path, html_dir: Path) -> dict:
    run_dir = Path(run_dir)
    prefix = os.path.relpath(run_dir, html_dir).replace(os.sep, "/")
    meta = _json(run_dir / "meta.json") or {}
    calls = {c["call"]: c for c in _jsonl(run_dir / "calls.jsonl")}
    actions = {a["index"]: a for a in _jsonl(run_dir / "actions.jsonl")}
    frames_idx = {r["ref"]: r for r in _jsonl(run_dir / "frames" / "index.jsonl")}
    bugs_events = _jsonl(run_dir / "bugs.jsonl")
    archive = None
    if (run_dir / "frames").exists():
        from agent.vlm.archive import FrameArchive
        archive = FrameArchive(run_dir)

    turns: List[dict] = []
    cur: Optional[dict] = None
    last_call: Optional[dict] = None
    pending_compaction: Optional[int] = None
    rows = _jsonl(run_dir / "transcript.jsonl")
    # Transcripts written before call numbers were recorded: assistant rows appear in the order of
    # the step calls whose reply was appended (truncated-and-retried calls appended nothing).
    appended = iter(sorted(n for n, c in calls.items()
                           if c.get("kind") == "step" and not (c.get("finish_reason") == "length" and not c.get("tools"))))
    for row in rows:
        if row.get("event") == "compaction":
            pending_compaction = row.get("epoch")
            cur, last_call = None, None
            continue
        role = row.get("role")
        if role == "system":
            continue
        if role == "user":
            content = row.get("content")
            parts = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
            imgs = _frames_from_parts(parts, frames_idx, prefix, archive)
            text = next((p["text"] for p in parts if p.get("type") == "text"), "")
            if pending_compaction is not None:
                note_p = run_dir / "context" / f"note_{pending_compaction}.md"
                turns.append(dict(kind="compaction", epoch=pending_compaction, header=text,
                                  notes=note_p.read_text() if note_p.exists() else ""))
                pending_compaction = None
            elif not turns:
                turns.append(dict(kind="start", text=text, frames=imgs))
            elif imgs and last_call is not None:
                last_call["frames"] = imgs
            elif imgs:
                turns.append(dict(kind="images", text=text, frames=imgs))
            else:
                turns.append(dict(kind="nudge", text=text))
            continue
        if role == "assistant":
            n = row.get("call")
            if n is None:
                n = next(appended, None)
            c = calls.get(n, {})
            tool_calls = []
            for tc in row.get("tool_calls") or []:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except ValueError:
                    args = {"_raw": tc["function"].get("arguments")}
                tool_calls.append(dict(id=tc.get("id"), name=tc["function"]["name"], args=args, result="",
                                       error=False, frames=[], action=None, bug=None))
            cur = dict(kind="call", call=n, content=row.get("content") or "", reasoning=row.get("reasoning_content") or "",
                       tool_calls=tool_calls,
                       usage=dict(prompt_tokens=c.get("prompt_tokens"), completion_tokens=c.get("completion_tokens"),
                                  cached_tokens=c.get("cached_tokens"), reasoning_tokens=c.get("reasoning_tokens"),
                                  latency_s=c.get("latency_s"), finish_reason=c.get("finish_reason")))
            turns.append(cur)
            last_call = None
            continue
        if role == "tool" and cur is not None:
            text = str(row.get("content") or "")
            tc = next((t for t in cur["tool_calls"] if t["id"] == row.get("tool_call_id")), None)
            if tc is None:
                continue
            tc["result"] = text
            tc["error"] = text.startswith("ERROR")
            if tc["name"] in ENV_ACTIONS:
                m = re.match(r"a(\d+)\b", text)
                if m and int(m.group(1)) in actions:
                    a = actions[int(m.group(1))]
                    tc["action"] = dict(index=a["index"], moved=a.get("moved"), blocked=bool(a.get("blocked")),
                                        pose=a.get("pose"), events=a.get("events"))
            elif tc["name"] in ("flag_bug", "update_bug"):
                m = re.match(r"(?:Recorded|Updated) (b\d+) \[(\w+)\]", text)
                if m:
                    tc["bug"] = dict(id=m.group(1), status=m.group(2))
            last_call = tc

    # path: a0 from the frame index, then every env action
    path = []
    a0 = frames_idx.get("a0")
    if a0:
        p = a0["pose"]
        path.append(dict(index=0, x=p["x"], y=p["y"], yaw=p["yaw"], blocked=False, moved=0.0, kind="start"))
    for i in sorted(actions):
        a = actions[i]
        p = a["pose"]
        path.append(dict(index=i, x=p["x"], y=p["y"], yaw=p["yaw"], blocked=bool(a.get("blocked")),
                         moved=a.get("moved"), kind=a["action"]["kind"]))

    ledger: Dict[str, dict] = {}
    for e in bugs_events:
        ledger[e["id"]] = dict(id=e["id"], status=e["status"], category=e.get("category"),
                               description=e.get("description"), evidence=e.get("evidence") or [],
                               action=e.get("action"), pos=e.get("pos"))
    frames_map = {ref: f"{prefix}/frames/{r['file']}" for ref, r in frames_idx.items()}
    notes_p = run_dir / "notes.md"
    steps_meta = dict(actions=meta.get("steps_used", len(actions)), calls=meta.get("calls", len(calls)))
    return dict(id=prefix, meta=meta, turns=turns, path=path, ledger=list(ledger.values()),
                notes=notes_p.read_text() if notes_p.exists() else "", frames=frames_map,
                thumb=frames_map.get("a0"), tool_counts=meta.get("tool_counts") or _count_tools(turns), **steps_meta)


def _count_tools(turns: List[dict]) -> dict:
    out: Dict[str, int] = {}
    for t in turns:
        for tc in t.get("tool_calls", []):
            out[tc["name"]] = out.get(tc["name"], 0) + 1
    return out


def collect_runs(root: Path, html_dir: Path) -> List[dict]:
    runs = []
    for meta_path in sorted(Path(root).glob("**/meta.json")):
        if not (meta_path.parent / "transcript.jsonl").exists():
            continue                                   # not an agent/vlm/ run (old harness dirs have no transcript)
        runs.append(load_run(meta_path.parent, html_dir))
    runs.sort(key=lambda r: r["meta"].get("started") or "", reverse=True)
    return runs


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171a;--dim:#5d6570;--line:#e2e5ea;--accent:#2f6feb;
      --ok:#1a7f45;--warn:#9a6700;--bad:#c1362e;--code:#f0f2f5;--mem:#6f42c1;--note:#b08800}
@media(prefers-color-scheme:dark){:root{--bg:#0f1216;--card:#171b21;--ink:#e6e9ee;--dim:#9aa4b2;
      --line:#262c35;--accent:#5b8cf5;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--code:#0d1117;
      --mem:#a371f7;--note:#e3b341}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);
       padding:10px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:600}
.sub{color:var(--dim);font-size:12px}
main{padding:20px;max-width:1280px;margin:0 auto}
button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--ink);
       border-radius:7px;padding:5px 11px}
button:hover{border-color:var(--accent);color:var(--accent)}
input{font:inherit;padding:5px 10px;border:1px solid var(--line);border-radius:7px;background:var(--bg);
      color:var(--ink);min-width:220px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;overflow:hidden;cursor:pointer;transition:.13s}
.card:hover{border-color:var(--accent);transform:translateY(-2px)}
.card img{width:100%;aspect-ratio:16/10;object-fit:cover;display:block;background:var(--code)}
.card .body{padding:11px 13px}
.title{font-weight:600;margin-bottom:6px;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;word-break:break-all}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.tag{font-size:11px;padding:2px 7px;border-radius:20px;background:var(--code);color:var(--dim);white-space:nowrap}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600;
       background:color-mix(in srgb,var(--dim) 15%,transparent);color:var(--dim)}
.badge.ok{background:color-mix(in srgb,var(--ok) 17%,transparent);color:var(--ok)}
.badge.info{background:color-mix(in srgb,var(--accent) 17%,transparent);color:var(--accent)}
.badge.warn{background:color-mix(in srgb,var(--warn) 17%,transparent);color:var(--warn)}
.badge.bad{background:color-mix(in srgb,var(--bad) 17%,transparent);color:var(--bad)}
.badge.mem{background:color-mix(in srgb,var(--mem) 17%,transparent);color:var(--mem)}
.badge.note{background:color-mix(in srgb,var(--note) 20%,transparent);color:var(--note)}
.summary{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:13px;margin-bottom:13px;
         display:grid;gap:15px;grid-template-columns:minmax(260px,380px) 1fr}
@media(max-width:800px){.summary,.turn{grid-template-columns:1fr}}
.turn{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:13px;margin-bottom:13px;
      display:grid;gap:15px;grid-template-columns:minmax(260px,380px) 1fr}
.turn.compaction{display:block;background:color-mix(in srgb,var(--warn) 9%,transparent);border-left:4px solid var(--warn)}
.turn.nudge{display:block;padding:7px 13px;color:var(--dim);font-size:12.5px}
.turn.start{border-left:4px solid var(--accent)}
img.frame{width:100%;border-radius:7px;display:block;cursor:zoom-in;background:var(--code)}
.strip{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:6px}
.strip img{width:100%;border-radius:4px;display:block;cursor:zoom-in;background:var(--code)}
.strip .cap{font-size:10px;color:var(--dim);text-align:center;font-family:ui-monospace,Menlo,monospace}
.fcap{font-size:11px;color:var(--dim);font-family:ui-monospace,Menlo,monospace;margin:2px 0 8px}
.imgs.inspect{border:2px dashed var(--mem);border-radius:9px;padding:6px;margin-bottom:8px}
.imgs.inspect .fcap{color:var(--mem)}
.zoom{position:fixed;inset:0;z-index:20;background:#000d;display:flex;align-items:center;justify-content:center;
      flex-direction:column;cursor:zoom-out}
.zoom img{max-width:96vw;max-height:88vh;object-fit:contain}
.zoom .cap{color:#fff;font-family:ui-monospace,Menlo,monospace;font-size:13px;margin-top:8px}
.row{display:flex;align-items:baseline;gap:9px;margin-bottom:8px;flex-wrap:wrap}
.n{font-weight:700;font-size:15px}
.content{margin-bottom:9px;white-space:pre-wrap}
.tc{border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px;background:var(--bg)}
.tc.err{border-color:var(--bad)}
.tc .head{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:4px}
.name{font-family:ui-monospace,Menlo,monospace;font-weight:700;font-size:12.5px;padding:1px 7px;border-radius:5px;
      background:color-mix(in srgb,var(--accent) 15%,transparent);color:var(--accent)}
.name.mem{background:color-mix(in srgb,var(--mem) 15%,transparent);color:var(--mem)}
.name.bug{background:color-mix(in srgb,var(--warn) 18%,transparent);color:var(--warn)}
.name.note{background:color-mix(in srgb,var(--note) 22%,transparent);color:var(--note)}
.name.done{background:color-mix(in srgb,var(--ok) 15%,transparent);color:var(--ok)}
.args{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--dim);word-break:break-all}
pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;background:var(--code);
    padding:7px 9px;border-radius:6px;overflow-x:auto;margin:0;white-space:pre-wrap;word-break:break-word}
pre.err{color:var(--bad)}
details{margin-top:5px}summary{cursor:pointer;color:var(--dim);font-size:12px}summary:hover{color:var(--accent)}
details pre{margin-top:6px;max-height:340px;overflow-y:auto}
.label{font-size:10.5px;text-transform:uppercase;letter-spacing:.55px;color:var(--dim);font-weight:600;margin-bottom:4px}
table{border-collapse:collapse;font-size:12.5px;width:100%}
td,th{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.ref{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--accent);cursor:pointer;text-decoration:underline dotted}
svg.path{width:100%;background:var(--code);border-radius:7px}
.empty{color:var(--dim);text-align:center;padding:60px 20px}
.hide{display:none}
.cfg{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.stats{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:var(--dim)}
</style></head><body>
<header>
  <button id="back" class="hide">&larr; All runs</button>
  <h1 id="title">__TITLE__</h1>
  <span class="sub" id="subtitle"></span>
  <span style="flex:1"></span>
  <input id="filter" placeholder="filter by task, model, outcome, tag">
</header>
<main><div id="view"></div></main>
<div id="zoom" class="zoom hide"><img id="zoomimg" alt=""><div class="cap" id="zoomcap"></div></div>
<script>
const RUNS = __DATA__;
const el = document.getElementById('view');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ENV = new Set(['move','turn','look','interact','wait']);
const MEM = new Set(['inspect','history','list_bugs']);
const cls = n => ENV.has(n) ? '' : MEM.has(n) ? 'mem' : n === 'flag_bug' || n === 'update_bug' ? 'bug'
  : n === 'write_notes' ? 'note' : n === 'done' ? 'done' : '';
const outcomeBadge = o => o === 'done' ? 'ok' : o === 'budget' ? 'info' : o ? 'bad' : '';
const statusBadge = s => s === 'confirmed' ? 'ok' : s === 'suspect' ? 'warn' : s === 'retracted' ? 'bad' : '';
const shortModel = m => String(m ?? '').split('/').filter(Boolean).pop() || '—';
const fmt = v => v == null ? '—' : v;
let CUR = null;

function zoom(url, cap) {
  document.getElementById('zoomimg').src = url; document.getElementById('zoomcap').textContent = cap || '';
  document.getElementById('zoom').classList.remove('hide');
}
document.getElementById('zoom').onclick = () => document.getElementById('zoom').classList.add('hide');
function zoomRef(ref) { if (CUR && CUR.frames[ref]) zoom(CUR.frames[ref], ref); }

function toolChips(counts) {
  return Object.entries(counts || {}).map(([k, v]) => `<span class="tag ${cls(k)}">${esc(k)} ×${v}</span>`).join('');
}

function listView(q) {
  CUR = null;
  document.getElementById('back').classList.add('hide');
  document.getElementById('title').textContent = '__TITLE__';
  const hits = RUNS.filter(r => !q || (r.id + ' ' + (r.meta.task || '') + ' ' + (r.meta.model || '') + ' ' +
    (r.meta.outcome || '')).toLowerCase().includes(q));
  document.getElementById('subtitle').textContent = `${hits.length} of ${RUNS.length} run${RUNS.length === 1 ? '' : 's'}`;
  if (!hits.length) { el.innerHTML = '<div class="empty">No runs match.</div>'; return; }
  el.innerHTML = '<div class="grid">' + hits.map(r => {
    const m = r.meta, flags = r.ledger.filter(b => b.status !== 'retracted');
    return `<div class="card" data-id="${esc(r.id)}">
      ${r.thumb ? `<img loading="lazy" src="${esc(r.thumb)}" alt="">` : '<div style="aspect-ratio:16/10;background:var(--code)"></div>'}
      <div class="body">
        <div class="title">${esc(r.id)}</div>
        <span class="badge ${outcomeBadge(m.outcome)}">${esc(m.outcome || 'unfinished')}</span>
        <span class="badge ${flags.length ? 'warn' : ''}">${flags.length} flag${flags.length === 1 ? '' : 's'}</span>
        ${r.ledger.some(b => b.status === 'retracted') ? '<span class="badge bad">retracted</span>' : ''}
        <div class="tags">
          <span class="tag">${r.actions} actions</span><span class="tag">${r.calls} calls</span>
          ${m.compactions ? `<span class="tag">${m.compactions} compaction${m.compactions > 1 ? 's' : ''}</span>` : ''}
          ${m.cached_ratio != null ? `<span class="tag">cache ${Math.round(m.cached_ratio * 100)}%</span>` : ''}
          <span class="tag">${esc(m.obs || '')}</span><span class="tag">${esc(shortModel(m.model))}</span>
        </div>
        <div class="tags">${toolChips(r.tool_counts)}</div>
        <div class="sub" style="margin-top:8px">${esc(m.started || '')}</div>
      </div></div>`;
  }).join('') + '</div>';
  el.querySelectorAll('.card').forEach(c => c.onclick = () => { location.hash = c.dataset.id; });
}

function pathSvg(path, ledger) {
  if (path.length < 2) return '';
  const xs = path.map(p => p.x), ys = path.map(p => p.y);
  const fx = ledger.filter(b => b.pos).map(b => b.pos[0]), fy = ledger.filter(b => b.pos).map(b => b.pos[2]);
  const minx = Math.min(...xs, ...fx) - 1, maxx = Math.max(...xs, ...fx) + 1;
  const miny = Math.min(...ys, ...fy) - 1, maxy = Math.max(...ys, ...fy) + 1;
  const W = 380, H = Math.max(160, Math.min(380, W * (maxy - miny) / (maxx - minx)));
  const sx = x => (x - minx) / (maxx - minx) * (W - 20) + 10;
  const sy = y => H - ((y - miny) / (maxy - miny) * (H - 20) + 10);
  const pts = path.map(p => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ');
  const dots = path.map(p => `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="${p.blocked ? 4 : 2.5}"
      fill="${p.blocked ? 'var(--bad)' : p.kind === 'start' ? 'var(--ok)' : 'var(--accent)'}"><title>a${p.index} ${p.kind}${p.blocked ? ' BLOCKED' : ''} (${p.x.toFixed(2)}, ${p.y.toFixed(2)})</title></circle>`
    + (p.index % 5 === 0 ? `<text x="${(sx(p.x) + 4).toFixed(1)}" y="${(sy(p.y) - 4).toFixed(1)}" font-size="9" fill="var(--dim)">a${p.index}</text>` : '')).join('');
  const flags = ledger.filter(b => b.pos).map(b => `<g><rect x="${(sx(b.pos[0]) - 5).toFixed(1)}" y="${(sy(b.pos[2]) - 5).toFixed(1)}" width="10" height="10" transform="rotate(45 ${sx(b.pos[0]).toFixed(1)} ${sy(b.pos[2]).toFixed(1)})" fill="${b.status === 'retracted' ? 'var(--dim)' : b.status === 'confirmed' ? 'var(--ok)' : 'var(--warn)'}"><title>${esc(b.id)} ${esc(b.status)}: ${esc(b.description)}</title></rect></g>`).join('');
  const last = path[path.length - 1];
  const heading = `<line x1="${sx(last.x).toFixed(1)}" y1="${sy(last.y).toFixed(1)}" x2="${(sx(last.x) + 12 * Math.cos(last.yaw * Math.PI / 180)).toFixed(1)}" y2="${(sy(last.y) - 12 * Math.sin(last.yaw * Math.PI / 180)).toFixed(1)}" stroke="var(--ink)" stroke-width="1.5"/>`;
  return `<svg class="path" viewBox="0 0 ${W} ${H}"><polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5" opacity=".7"/>${dots}${flags}${heading}</svg>
    <div class="stats">x ${minx.toFixed(1)}..${maxx.toFixed(1)}, y ${miny.toFixed(1)}..${maxy.toFixed(1)} m · red = blocked · diamonds = flags · tick = final heading</div>`;
}

function framesHtml(frames, inspect) {
  if (!frames || !frames.length) return '';
  const film = frames.filter(f => f.kind === 'film'), rest = frames.filter(f => f.kind !== 'film');
  let h = `<div class="imgs ${inspect ? 'inspect' : ''}">` + (inspect ? '<div class="fcap">inspect → archived frames</div>' : '');
  if (film.length) h += '<div class="strip">' + film.map(f => `<div><img loading="lazy" src="${esc(f.url)}" data-cap="${esc(f.caption)}" alt=""><div class="cap">${esc(f.ref)} ${f.t_sim != null ? '+' + f.t_sim + 's' : ''}</div></div>`).join('') + '</div>';
  h += rest.map(f => `<img class="frame" loading="lazy" src="${esc(f.url)}" data-cap="${esc(f.caption)}" alt=""><div class="fcap">${esc(f.caption)}</div>`).join('');
  return h + '</div>';
}

function toolHtml(tc) {
  const a = tc.action;
  const argStr = Object.entries(tc.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' ');
  const long = (tc.result || '').length > 400 || (tc.result || '').includes('\n');
  const res = tc.result ? (long
      ? `<details${tc.name === 'flag_bug' || tc.name === 'update_bug' ? ' open' : ''}><summary>result (${tc.result.length} chars)</summary><pre class="${tc.error ? 'err' : ''}">${esc(tc.result)}</pre></details>`
      : `<pre class="${tc.error ? 'err' : ''}">${esc(tc.result)}</pre>`) : '';
  return `<div class="tc ${tc.error ? 'err' : ''}">
    <div class="head"><span class="name ${cls(tc.name)}">${esc(tc.name)}</span><span class="args">${esc(argStr)}</span>
      ${a ? `<span class="badge info">a${a.index}</span>${a.blocked ? '<span class="badge bad">BLOCKED</span>' : ''}${a.events && a.events.teleported ? '<span class="badge warn">teleported</span>' : ''}${a.events && a.events.respawned ? '<span class="badge warn">respawned</span>' : ''}` : ''}
      ${tc.bug ? `<span class="badge ${statusBadge(tc.bug.status)}">${esc(tc.bug.id)} ${esc(tc.bug.status)}</span>` : ''}
      ${tc.error ? '<span class="badge bad">error</span>' : ''}
      ${tc.name === 'inspect' && tc.frames.length ? `<span class="badge mem">${tc.frames.length} frame${tc.frames.length > 1 ? 's' : ''} recalled</span>` : ''}
    </div>${res}</div>`;
}

function detailView(run) {
  CUR = run;
  const m = run.meta;
  document.getElementById('back').classList.remove('hide');
  document.getElementById('title').textContent = run.id;
  document.getElementById('subtitle').textContent = `${run.actions} actions · ${run.calls} calls · ${esc(m.started || '')}`;
  const cfgKeys = ['model', 'obs', 'decision', 'tick', 'max_sim_seconds', 'film_dt', 'film_max', 'context_limit', 'keep_recent', 'tools', 'expect', 'proprio', 'preserve_thinking', 'thinking_budget',
                   'blocked_hint', 'max_tokens', 'temperature', 'reasoning_effort', 'steps_budget', 'env', 'renderer'];
  const cfg = cfgKeys.filter(k => m[k] !== undefined && m[k] !== null).map(k =>
    `<span class="tag">${esc(k)} ${esc(Array.isArray(m[k]) ? m[k].join(',') : String(m[k]).slice(0, 40))}</span>`).join('');
  const u = m.vlm_usage || {};
  const ledger = run.ledger.length ? `<table><tr><th>id</th><th>status</th><th>category</th><th>description</th><th>evidence</th><th>at</th></tr>` +
    run.ledger.map(b => `<tr><td>${esc(b.id)}</td><td><span class="badge ${statusBadge(b.status)}">${esc(b.status)}</span></td><td>${esc(b.category)}</td><td>${esc(b.description)}</td><td>${(b.evidence || []).map(r => `<span class="ref" data-ref="${esc(r)}">${esc(r)}</span>`).join(' ')}</td><td>a${b.action}</td></tr>`).join('') + '</table>' : '<div class="sub">no bugs flagged</div>';
  let html = `<div class="cfg"><span class="badge ${outcomeBadge(m.outcome)}">${esc(m.outcome || 'unfinished')}</span>${cfg}</div>
    <div class="summary"><div><div class="label">top-down path</div>${pathSvg(run.path, run.ledger)}</div>
    <div><div class="label">bug ledger (final)</div>${ledger}
      <div class="label" style="margin-top:12px">tools used</div><div class="tags">${toolChips(run.tool_counts)}</div>
      <div class="label" style="margin-top:12px">usage</div><div class="stats">prompt ${fmt(u.prompt_tokens)} · cached ${fmt(u.cached_tokens)} · completion ${fmt(u.completion_tokens)} · reasoning ${fmt(u.reasoning_tokens)} · compactions ${fmt(m.compactions)} · wall ${fmt(m.wall_s)}s</div>
      ${run.notes ? `<div class="label" style="margin-top:12px">final notes</div><pre>${esc(run.notes)}</pre>` : ''}
      ${m.done_summary ? `<div class="label" style="margin-top:12px">done summary</div><div>${esc(m.done_summary)}</div>` : ''}
    </div></div>`;
  html += run.turns.map(t => {
    if (t.kind === 'start') return `<div class="turn start"><div>${framesHtml(t.frames)}</div><div><div class="row"><span class="n">start</span></div><pre>${esc(t.text)}</pre></div></div>`;
    if (t.kind === 'compaction') return `<div class="turn compaction"><div class="row"><span class="n">context compacted</span><span class="badge warn">epoch ${t.epoch}</span></div>
      <div class="label">rewritten notes (carried into the new context)</div><pre>${esc(t.notes || '(empty)')}</pre>
      <details><summary>full header the model received</summary><pre>${esc(t.header)}</pre></details></div>`;
    if (t.kind === 'nudge') return `<div class="turn nudge">harness → ${esc(t.text)}</div>`;
    if (t.kind === 'images') return `<div class="turn"><div>${framesHtml(t.frames)}</div><div>${esc(t.text)}</div></div>`;
    const u = t.usage || {};
    const imgs = t.tool_calls.map(tc => framesHtml(tc.frames, tc.name === 'inspect')).join('');
    return `<div class="turn"><div>${imgs}</div><div>
      <div class="row"><span class="n">call ${t.call}</span>
        <span class="stats">${u.latency_s != null ? u.latency_s + 's' : ''} · prompt ${fmt(u.prompt_tokens)} (cached ${fmt(u.cached_tokens)}) · out ${fmt(u.completion_tokens)}${u.reasoning_tokens ? ' (reasoning ' + u.reasoning_tokens + ')' : ''}${u.finish_reason && u.finish_reason !== 'tool_calls' ? ' · ' + esc(u.finish_reason) : ''}</span></div>
      ${t.content ? `<div class="content">${esc(t.content)}</div>` : '<div class="sub" style="margin-bottom:8px">(no visible text)</div>'}
      ${t.reasoning ? `<details style="margin-bottom:8px"><summary>chain of thought (${t.reasoning.length} chars)</summary><pre>${esc(t.reasoning)}</pre></details>` : ''}
      ${t.tool_calls.length ? t.tool_calls.map(toolHtml).join('') : '<div class="sub">no tool call</div>'}
    </div></div>`;
  }).join('');
  el.innerHTML = html;
  el.querySelectorAll('img[data-cap]').forEach(i => i.onclick = () => zoom(i.src, i.dataset.cap));
  el.querySelectorAll('.ref').forEach(r => r.onclick = () => zoomRef(r.dataset.ref));
}

function route() {
  const id = decodeURIComponent(location.hash.slice(1));
  const run = RUNS.find(r => r.id === id);
  run ? detailView(run) : listView(document.getElementById('filter').value.toLowerCase());
  window.scrollTo(0, 0);
}
document.getElementById('back').onclick = () => { location.hash = ''; };
document.getElementById('filter').oninput = e => { if (location.hash) location.hash = ''; else listView(e.target.value.toLowerCase()); };
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { const z = document.getElementById('zoom'); z.classList.contains('hide') ? (location.hash = '') : z.classList.add('hide'); }
});
window.addEventListener('hashchange', route);
route();
</script></body></html>
"""


def build_html(runs: List[dict], title: str) -> str:
    payload = json.dumps(runs, default=str).replace("</", r"<\/")
    return TEMPLATE.replace("__DATA__", payload).replace("__TITLE__", title.replace("<", "&lt;"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a browsable page from a directory of agent runs.")
    ap.add_argument("directory", nargs="?", default="runs", help="runs/<tag> or runs (recursive)")
    ap.add_argument("-o", "--output", help="output html (default: DIRECTORY/index.html)")
    ap.add_argument("--open", action="store_true", help="open it in a browser")
    args = ap.parse_args(argv)
    root = Path(args.directory).expanduser().resolve()
    if not root.is_dir():
        print(f"no such directory: {root}", file=sys.stderr)
        return 1
    out = Path(args.output).expanduser().resolve() if args.output else root / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    runs = collect_runs(root, out.parent)
    if not runs:
        print(f"no agent runs found under {root} (need meta.json + transcript.jsonl)", file=sys.stderr)
        return 1
    out.write_text(build_html(runs, root.name))
    print(f"{len(runs)} runs, {sum(r['calls'] for r in runs)} calls -> {out}")
    if args.open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
