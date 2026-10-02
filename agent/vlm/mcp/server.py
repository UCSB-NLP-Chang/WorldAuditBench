"""One stdio MCP process per episode. The native CLI owns the agent loop/history."""
import argparse
import asyncio
import base64
from contextlib import redirect_stdout
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def load_upstream(path):
    sys.path.insert(0, str(Path(path).resolve()))
    from agent.vlm.tools import Dispatcher, tool_schemas
    return Dispatcher, tool_schemas


def finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numbers are not permitted")
    if isinstance(value, dict):
        for v in value.values():
            finite_json(v)
    elif isinstance(value, list):
        for v in value:
            finite_json(v)


class ResultSink:
    """Capture only this MCP result, never maintain a second model conversation."""
    def __init__(self):
        self.text = []
        self.images = []

    def append_tool(self, call_id, text):
        self.text.append(text)

    def append_user_images(self, label, items):
        self.images.extend(items)

    def mark_action(self, action):
        pass


MEMORY_MCP = ("Memory: captured frames are archived. Use inspect to retrieve selected images and history for prior tool actions and "
              "observations. Your native client controls context compaction; MCP does not rebuild your conversation.")


class Episode:
    def __init__(self, config):
        import jsonschema
        from agent.vlm.archive import FrameArchive
        from agent.vlm.ledger import BugLedger
        from agent.vlm.notes import Notes
        from agent.vlm.tools import Dispatcher, tool_schemas
        from agent.vlm.types import ObsConfig

        self.config = config
        self.scene_description = config.get("scene_description", "")
        if config["environment"] != "fake" and not self.scene_description.strip():
            raise ValueError("A real environment requires its public scene description")
        self.run = Path(config["run_dir"])
        self.run.mkdir(parents=True, exist_ok=True)
        # A restarted MCP server must not silently reset/replay an existing episode.
        self.lock = self.run / "episode.started"
        if self.lock.exists():
            raise ValueError("This episode already started; use a new run directory and a fresh environment")
        self.claimed = False
        self.examples = None
        self.examples_read = set()
        if config.get("icl", {}).get("enabled"):
            from agent.vlm.mcp.examples import ExamplePack
            code = config.get("subcategory")
            if not code:
                raise ValueError("ICL requires the task's specific subcategory")
            self.examples = ExamplePack(config["icl_directory"], code=code)
            if self.examples.manifest() != config["icl"]:
                raise ValueError("ICL snapshot differs from the launch manifest")
            self.examples.check_task(config["task"], config.get("allow_icl_overlap", False))
        self.started = False
        self.closed = False
        self.calls = 0
        self.broken = False
        self.last_items = []
        self.observation = config.get("observation", "on-demand")
        mode = "final" if self.observation == "final" else "film"
        self.obs = ObsConfig(mode=mode, film_dt=0.5, film_max=8)
        if config["environment"] == "fake":
            from agent.vlm.env.fake import FakeEnv
            self.env = FakeEnv()
        elif config["environment"] == "unreal-http":
            from agent.vlm.mcp.unreal_http import UnrealHTTP
            self.env = UnrealHTTP(config["environment_url"])
        elif config["environment"] == "threejs":
            from agent.vlm.mcp.browser import BrowserEnv
            self.env = BrowserEnv(config)
        elif config["environment"] == "vla-replay":
            from agent.vlm.mcp.replay import ReplayEnv
            rmode = config.get("replay_mode", "play")
            self.vqa = rmode == "vqa"
            self.env = ReplayEnv(config["replay_dir"], preview_every=0.5 if self.vqa else config.get("preview_every", 5.0),
                                 mode="all" if self.vqa else rmode)
        else:
            raise ValueError("Unsupported environment")
        self.replay = config["environment"] == "vla-replay"
        self.vqa = self.replay and config.get("replay_mode") == "vqa"
        if config["environment"] == "vla-replay" and config.get("replay_mode", "play") in ("all", "vqa") and config.get("inline_full_res", True):
            # gemini charges the same tokens for a 480x288 and a 960x576 image, and low-resolution inline frames only make the
            # model re-fetch them with inspect: deliver the inline frames at the largest size whose total JPEG payload stays
            # under the byte budget (one MCP result / one model request; 120 frames at 960x576 = 13 MB broke the native client).
            self.obs = ObsConfig(mode=mode, film_dt=0.5, film_max=8, ctx_film=self.env.inline_size(
                self.obs.ctx_final, budget_bytes=config.get("inline_budget_bytes", 4_000_000)))
        self.archive = FrameArchive(self.run)
        self.ledger = BugLedger(self.run)
        self.notes = Notes(self.run)
        self.sink = ResultSink()
        self.dispatch = Dispatcher(self.env, self.archive, self.ledger, self.notes, self.sink,
                                   self.obs, self.run, config["max_actions"],
                                   proprio=True, blocked_hint=False)
        schemas = tool_schemas(self.env.capabilities, {"memory", "bugs", "notes"})
        self.schemas = {s["function"]["name"]: s["function"] for s in schemas}
        self.schemas["observe"] = {
            "name": "observe", "description": "Start the assigned episode or re-read its current cached observation. Does not advance time.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        }
        self.schemas["read_example"] = {
            "name": "read_example",
            "description": "Read the ONE supplied ICL demonstration for this task's specific subcategory (definition, 1–3 images, reference answer). Read it before observe. Omit code to read the assigned example; re-read it after compaction. Other categories are unavailable. No environment action or time passes. Forward image blocks with image(block), not text/JSON serialization.",
            "parameters": {"type": "object", "properties": {"code": {"type": "string", **(
                {"enum": list(self.examples.examples)} if self.examples else {})}},
                           "additionalProperties": False},
        }
        if self.replay and self.env.mode == "play":
            last = self.env.last_t
            self.schemas.pop("wait")
            self.schemas["play"] = {
                "name": "play",
                "description": (f"Play a segment of the explorer's recording, from from_s to to_s (at most {self.env.MAX_SEGMENT:g} s, "
                                f"times in 0.5 s steps between 0 and {last:g}). Any segment, in any order; a segment can be played again. "
                                "Returns the final view at to_s; the film frames every 0.5 s inside the segment are archived for inspect. "
                                "This is your only environment action: you do not control the camera."),
                "parameters": {"type": "object", "properties": {
                    "from_s": {"type": "number", "minimum": 0, "maximum": last, "multipleOf": 0.5},
                    "to_s": {"type": "number", "minimum": 0.5, "maximum": last, "multipleOf": 0.5}},
                    "required": ["from_s", "to_s"]},
            }
        if self.vqa:
            from agent.vlm.ledger import CATEGORIES
            for name in ["inspect", "history", "write_notes", "flag_bug", "update_bug", "list_bugs", "done"]:
                self.schemas.pop(name, None)
            self.schemas["report"] = {
                "name": "report",
                "description": ("Your ONE and final answer: every distinct bug you found in the recording (an empty list if it shows no bug), "
                                "then the inspection ends. There is no other reporting tool and no second report."),
                "parameters": {"type": "object", "properties": {
                    "bugs": {"type": "array", "items": {"type": "object", "properties": {
                        "description": {"type": "string", "description": "what is wrong, which object, how you know"},
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                        "status": {"type": "string", "enum": ["suspect", "confirmed"]},
                        "evidence": {"type": "array", "items": {"type": "string"}, "description": "frame refs that show the problem, like a0.f37"}},
                        "required": ["description", "category", "status", "evidence"], "additionalProperties": False}},
                    "summary": {"type": "string"}}, "required": ["bugs", "summary"]},
            }
            config["inspect_budget"] = 0
        self.inspect_budget = config.get("inspect_budget")          # None = unlimited (embodied protocol); 0 = no inspect tool
        self.inspects = 0
        if self.inspect_budget == 0:
            self.schemas.pop("inspect", None)
        elif self.inspect_budget:
            self.schemas["inspect"]["description"] += f" At most {self.inspect_budget} inspect calls in this run."
        for schema in self.schemas.values():
            schema["parameters"]["additionalProperties"] = False
        if "inspect" in self.schemas:
            self.schemas["inspect"]["parameters"]["properties"]["refs"].update(minItems=1, maxItems=4)
            self.schemas["inspect"]["parameters"]["properties"]["region"]["items"].update(minimum=0, maximum=1)
        if "interact" in self.schemas:
            self.schemas["interact"]["description"] = "Attempt the reachable interaction under the crosshair. Use wait afterwards to observe delayed changes."
        self.validators = {k: jsonschema.Draft202012Validator(v["parameters"]) for k, v in self.schemas.items()}
        self.schema_hash = hashlib.sha256(json.dumps(self.schemas, sort_keys=True).encode()).hexdigest()
        (self.run / "tools.json").write_text(json.dumps(self.schemas, indent=2) + "\n")
        self.save("ready")

    def instructions(self):
        from agent.vlm.prompts import build_system, MEMORY, NOTES
        delivery = "film" if self.observation == "film" else "final"
        base = build_system(delivery, True, {"memory", "bugs", "notes"}, self.env.capabilities)
        base = base.replace(MEMORY, MEMORY_MCP)
        base = base.replace(NOTES, "Notes: write_notes appends durable notes. Use observe to retrieve these notes and the bug ledger after context compaction.")
        base = base.replace("within ~3 m", "within the scene's interaction range")
        if self.replay:
            base = self.replay_instructions(base)
        return base + (
            "\n" + self.example_instructions() + " Only world_audit MCP tools are allowed. "
            "Images are returned as MCP image content. All captured frames have archive refs. "
            f"Observation delivery is {self.observation}; on-demand sends the final image and stores film frames for inspect. "
            f"You have {self.config['max_actions']} environment actions. "
            + ("" if self.inspect_budget == 0 else "Use inspect to compare up to four frames or crop a region; ") + "memory/report tools do not advance time. "
            + ("" if self.vqa else "history contains tool actions and observations, not your private reasoning. ")
            + "confirmed is your own assessment, not a ground-truth verdict. "
            + ("End with report." if self.vqa else "End with done.")
        )

    def replay_instructions(self, base):
        from agent.vlm.prompts import RULES, OBS_FINAL
        env = self.env
        base = base.replace(
            "You are a game QA tester controlling a first-person agent in a 3D world through tools.",
            "You are a game QA tester reviewing a first-person RECORDING of a 3D world through tools. A separate explorer "
            "walked through the world; you did not control the camera and cannot move it.")
        if env.mode == "all":
            base = base.replace("Environment actions: done(summary) ends the inspection.",
                                "Environment actions: none - the whole recording is delivered by observe; done(summary) ends the inspection.")
            full = self.obs.ctx_film == self.obs.ctx_final
            base = base.replace(OBS_FINAL,
                                f"Observation: observe returns the start view a0 and the recording as a FILM STRIP of frames a0.f<k> "
                                f"(a0.f<k> is at t = {env.frame_dt:g} x (k+1) s; every recorded frame is archived, one every "
                                f"{env.preview_every:g} s is shown {'at full resolution' if full else 'at low resolution'}) together with the "
                                f"explorer's track (pose, path length and controller input per frame). Use the changes (or lack of changes) "
                                f"between frames to understand what happened. "
                                + ("" if self.inspect_budget == 0 else
                                   "The shown frames are already at full resolution: inspect them only with a region to zoom, or inspect the "
                                   "archived frames between them when a moment matters." if full else ""))
            if self.vqa:
                from agent.vlm.prompts import BUGS, NOTES, EXPECT
                base = base.replace(MEMORY_MCP, "Memory: the frames delivered by observe are all you can see - cite their refs as evidence.")
                base = base.replace("Environment actions: none - the whole recording is delivered by observe; done(summary) ends the inspection.",
                                    "Environment actions: none - the whole recording is delivered by observe; report(bugs, summary) is your single "
                                    "answer and ends the inspection.")
                base = base.replace(NOTES, "")
                base = base.replace(BUGS, "Bug reports: answer with ONE report call listing every distinct bug (description, category, "
                                          "suspect/confirmed, evidence frame refs) or an empty list. Only that report counts; wrong or duplicated "
                                          "entries are penalized, so include only what the frames support.")
                base = base.replace(EXPECT, "")
                base = base.replace("Finish with done when the inspection is complete - do not flag normal objects.",
                                    "Finish with report - do not report normal objects.")
                base = base.replace("\n\n\n", "\n\n")
            elif self.inspect_budget == 0:
                base = base.replace(MEMORY_MCP, "Memory: there is no inspect tool; the frames delivered by observe are all you can see - cite "
                                                "their refs as evidence. history re-reads earlier tool actions and observations as text.")
            rules = RULES.replace(
                "- Actively TEST the area: walk through it, view things from more than one angle, use wait to watch things over time, "
                "use interact on mechanisms. If you command a move but travel much less than asked while nothing solid is visibly in the way, "
                "that is evidence of an invisible blocker.",
                "- Actively REVIEW the recording: go through the frames, inspect the ones around anything suspicious at full resolution, "
                "compare views of the same object from different moments. The track reports the explorer's own displacement and what it "
                "was pressing: if it held forward for seconds while barely moving and nothing solid is visibly in the way, that is evidence of an "
                "invisible blocker.")
            rules = rules.replace("- You have a limited budget of environment actions (stated in the task). Memory and bug tools do not consume it. ",
                                  "- There are no environment actions. ")
        else:
            base = base.replace("Environment actions: wait(seconds) stands still and observes;",
                                f"Environment actions: play(from_s, to_s) plays a segment of the recording (at most {env.MAX_SEGMENT:g} s, "
                                "any order, repeatable);")
            base = base.replace("after each environment action you receive one full-resolution first-person view taken when the action has finished",
                                "after each play you receive the full-resolution view at to_s")
            base = base.replace("standing still with wait films the scene over time", "the film frames inside a played segment show how the scene changes over time")
            rules = RULES.replace(
                "- Actively TEST the area: walk through it, view things from more than one angle, use wait to watch things over time, "
                "use interact on mechanisms. If you command a move but travel much less than asked while nothing solid is visibly in the way, "
                "that is evidence of an invisible blocker.",
                "- Actively REVIEW the recording: play the segments you have not seen, replay and inspect the frames around anything suspicious, "
                "compare views of the same object from different moments. The play result reports the explorer's own displacement and what it "
                "was pressing: if it held forward for seconds while barely moving and nothing solid is visibly in the way, that is evidence of an "
                "invisible blocker.")
            rules = rules.replace("You have a limited budget of environment actions (stated in the task).",
                                  "You have a limited budget of play actions (stated in the task); the preview frames a0.f* sample the whole recording.")
        rules = rules.replace("- Inspect objects from 2-4 metres away so the whole object and its surroundings fit in view; use look up/down when needed. "
                              "Verify every claim against the actual images.",
                              "- You cannot choose the viewpoint. Verify every claim against the actual images." if self.inspect_budget == 0 else
                              "- You cannot choose the viewpoint: use inspect (optionally with a region) to zoom into what the explorer saw. "
                              "Verify every claim against the actual images.")
        return base.replace(RULES, rules)

    def example_instructions(self):
        if not self.examples:
            return "No ICL is enabled. Use observe first to start the assigned task."
        return ("Before observe, read the ONE supplied ICL demonstration for this task's specific subcategory with read_example. Code: "
                + ", ".join(self.examples.examples) + ". Each has a definition, ordered images and a reference answer. "
                "These examples are not evidence from the assigned task. Then use observe to start the scene. "
                "Deliver each example to the model before reading the next; do not batch examples in one "
                "code-mode execution. Forward image blocks with image(block), never stringify them. "
                "After compaction you can re-read this example by code; other categories are unavailable.")

    def claim(self):
        if not self.claimed:
            with self.lock.open("x") as f:
                f.write(str(time.time()))
            self.claimed = True

    def start(self):
        if self.started:
            return
        # Exclusive creation also rejects a second native client targeting the same run.
        self.claim()
        self.started = True
        try:
            initial = self.env.reset(self.config["task"], self.config.get("seed", 0), self.obs)
            instruction = self.config["instruction"]
            if self.scene_description:
                instruction += "\nEnvironment description: " + self.scene_description
            _, self.last_items = self.dispatch.observe_initial(initial, instruction)
        except Exception:
            self.broken = True
            self.save("backend_error")
            raise

    def save(self, status):
        data = {"status": status, "environment": self.config["environment"],
                "task": self.config["task"], "max_actions": self.config["max_actions"],
                "scene_description": self.scene_description,
                "actions_used": self.dispatch.n_actions, "tool_calls": self.calls,
                "observation": self.observation, "film_dt": 0.5, "film_max": 8,
                "tools_sha256": self.schema_hash, "flags": self.ledger.export(),
                "done_summary": self.dispatch.done_summary, "backend": self.env.meta(),
                "icl": self.config.get("icl", {"enabled": False}),
                "icl_examples_delivered": sorted(self.examples_read),
                "icl_complete": self.examples is None or len(self.examples_read) == len(self.examples.examples),
                "environment_started": self.started,
                "simulated_seconds": self.dispatch.sim_t}
        temp = self.run / "meta.json.tmp"
        temp.write_text(json.dumps(data, indent=2) + "\n")
        temp.replace(self.run / "meta.json")

    def invoke(self, name, args):
        from mcp.types import CallToolResult, TextContent, ImageContent
        items = []
        image_refs = []
        model_name, model_args = name, args
        try:
            self.calls += 1
            if self.calls > self.config.get("max_tool_calls", 400) and name != "done":
                raise ValueError("Tool-call budget exhausted; call done")
            if name not in self.schemas:
                raise ValueError("Unknown tool")
            finite_json(args)
            self.validators[name].validate(args)
            if name == "inspect" and self.inspect_budget and self.inspects >= self.inspect_budget:
                raise ValueError(f"inspect budget exhausted ({self.inspect_budget} calls); report from the frames you have")
            if name == "inspect" and args.get("region"):
                x0, y0, x1, y1 = args["region"]
                if x1 <= x0 or y1 <= y0:
                    raise ValueError("Crop must have x0 < x1 and y0 < y1")
            if self.broken:
                raise ValueError("Episode failed; start a fresh run with a fresh environment")
            if self.closed or self.dispatch.done:
                raise ValueError("Episode is finished")
            if name == "read_example":
                if not self.examples:
                    raise ValueError("ICL is disabled for this run")
                pending = [c for c in self.examples.examples if c not in self.examples_read]
                code = args.get("code")
                if code is None:
                    if not pending:
                        raise ValueError("All examples were delivered; use observe or provide a code to re-read")
                    code = pending[0]
                if code not in self.examples.examples:
                    raise ValueError("Unknown example code; available: " + ", ".join(self.examples.examples))
                self.claim()
                content, image_refs = self.examples.content(code)
                self.examples_read.add(code)
                pending = [c for c in self.examples.examples if c not in self.examples_read]
                content.append(TextContent(type="text", text=(
                    "Still to read before observe: " + ", ".join(pending) if pending else
                    "The task's matching ICL demonstration was delivered. Use observe to start/resume the assigned scene.")))
                text = "\n".join(c.text for c in content if c.type == "text")
                error = False
            else:
                if self.examples:
                    pending = [c for c in self.examples.examples if c not in self.examples_read]
                    if pending:
                        raise ValueError("Read all ICL examples before using scene tools. Call read_example for: "
                                         + ", ".join(pending))
                if (name == "done" and self.config.get("require_full_budget")
                        and not self.broken and self.dispatch.n_actions < self.config["max_actions"]
                        and self.calls <= self.config.get("max_tool_calls", 400)):
                    raise ValueError("This run requires the full action budget before done; continue exploration and verification")
                self.start()
                play = None
                if name == "play":
                    play = (float(args["from_s"]), float(args["to_s"]))
                    if play[1] <= play[0]:
                        raise ValueError("play needs from_s < to_s")
                    if play[1] - play[0] > self.env.MAX_SEGMENT + 1e-6:
                        raise ValueError(f"a segment is at most {self.env.MAX_SEGMENT:g} s long")
                    if self.dispatch.n_actions >= self.config["max_actions"]:
                        raise ValueError("action budget exhausted - no more play actions; call done.")
                    self.env.seek(play[0])
                    name, args = "wait", {"seconds": round(play[1] - play[0], 3)}
                if name == "report":
                    bugs = args.get("bugs") or []
                    lines = []
                    for i, b in enumerate(bugs, 1):
                        b = dict(b)
                        unknown = [r for r in b.get("evidence") or [] if not self.archive.has(r)]
                        b["evidence"] = [r for r in b.get("evidence") or [] if self.archive.has(r)]
                        self.sink.text.clear(); self.sink.images.clear()
                        self.dispatch.run([{"id": f"{self.calls}.{i}", "function": {"name": "flag_bug", "arguments": json.dumps(b)}}], self.calls, "")
                        lines.append("\n".join(self.sink.text).split("\nLedger:")[0]
                                     + (f"  (dropped unknown frame ref(s): {', '.join(unknown)})" if unknown else ""))
                    self.sink.text.clear(); self.sink.images.clear()
                    self.dispatch.run([{"id": f"{self.calls}.done", "function": {"name": "done", "arguments": json.dumps({"summary": args.get("summary", "")})}}], self.calls, "")
                    lines.append("\n".join(self.sink.text))
                    text = f"Report received ({len(bugs)} bug(s)).\n" + "\n".join(lines) + "\nLedger:\n" + self.ledger.render()
                    self.env.close(); self.closed = True
                    items = []
                    name = "done"
                elif name == "observe":
                    text = (f"Task: {self.config['instruction']}\nEnvironment description: {self.scene_description}\n"
                            f"Current view a{self.dispatch.n_actions}. "
                            f"Actions remaining: {self.config['max_actions'] - self.dispatch.n_actions}. "
                            f"Archived frames: {', '.join(self.archive.refs_for(self.dispatch.n_actions))}\n"
                            f"Notes:\n{self.notes.read()}\nBug ledger:\n{self.ledger.render()}")
                    if self.replay and self.env.mode == "all":
                        text += "\n" + self.env.track_text()
                    items = self.last_items
                else:
                    self.sink.text.clear()
                    self.sink.images.clear()
                    self.dispatch.run([{"id": str(self.calls), "function": {
                        "name": name, "arguments": json.dumps(args)}}], self.calls, "")
                    text = "\n".join(self.sink.text)
                    items = list(self.sink.images)
                    if name == "inspect" and not text.startswith("ERROR:"):
                        self.inspects += 1
                    if play and not text.startswith("ERROR:"):
                        n = self.dispatch.n_actions
                        old_desc, new_desc = f"wait {args['seconds']:.1f}s", f"play {play[0]:.1f}-{play[1]:.1f}s"
                        text = text.replace(old_desc, new_desc, 1)
                        rec = self.dispatch.records.get(n)
                        if rec:
                            rec["desc"] = new_desc; rec["result"] = rec["result"].replace(old_desc, new_desc, 1)
                        if self.dispatch.index_lines:
                            self.dispatch.index_lines[-1] = self.dispatch.index_lines[-1].replace(old_desc, new_desc, 1)
                    if name in self.env.capabilities and not text.startswith("ERROR:"):
                        self.last_items = items
                    if getattr(self.env, "failed", False):
                        self.broken = True
                    if name == "done":
                        self.env.close()
                        self.closed = True
                if name != "inspect" and self.observation == "on-demand":
                    keep_preview = self.replay and name == "observe"
                    items = [i for i in items if ".f" not in i[2] or (keep_preview and i[2].startswith("a0.f") and self.env.inline(i[2]))]
                    if keep_preview and self.env.mode == "all":
                        shown = sum(1 for i in items if i[2].startswith("a0.f"))
                        full = self.obs.ctx_film == self.obs.ctx_final
                        text += (f"\nEvery recorded frame is archived (a0.f0..a0.f{len(self.env.frames) - 2}, {self.env.frame_dt:g} s apart); "
                                 f"{shown} of them, every {self.env.preview_every:g} s, are shown below at {'full' if full else 'low'} resolution. "
                                 + ("This is the whole recording. Answer with ONE report call (every distinct bug with evidence refs, or an empty list)."
                                    if self.vqa else
                                    "There is no inspect tool: report from the shown frames and cite their refs." if self.inspect_budget == 0 else
                                    "Use inspect only to zoom into a region of a frame or to view the archived frames between the shown ones."
                                    if full else "Use inspect(refs) to view any archived frame at full resolution or zoomed."))
                    elif keep_preview:
                        text += ("\nPreview frames a0.f* are shown at low resolution; film frames of played segments are archived; "
                                 "use inspect(refs) to view selected frames.")
                    else:
                        text += "\nFilm frames are archived; use inspect(refs) to view selected frames."
                content = [TextContent(type="text", text=text)]
                for caption, url, ref in items:
                    content.append(TextContent(type="text", text=f"{caption} [ref={ref}]"))
                    header, encoded = url.split(",", 1)
                    base64.b64decode(encoded, validate=True)
                    content.append(ImageContent(type="image", data=encoded, mimeType=header[5:].split(";")[0]))
                error = text.startswith("ERROR:")
                image_refs = [i[2] for i in items]
        except Exception as e:
            if getattr(self.env, "failed", False):
                self.broken = True
            text = f"ERROR: {e}"
            content = [TextContent(type="text", text=text)]
            error = True
        with (self.run / "mcp-calls.jsonl").open("a") as f:
            try:
                finite_json(model_args)
                logged_args = model_args
            except ValueError:
                logged_args = {"invalid": "non-finite argument"}
            f.write(json.dumps({"time": time.time(), "tool": model_name, "arguments": logged_args,
                                "text": text, "images": image_refs, "is_error": error}, allow_nan=False) + "\n")
        self.save("backend_error" if self.broken else "completed" if self.dispatch.done else "running")
        return CallToolResult(content=content, isError=error)

    def close(self):
        if self.closed:
            return
        try:
            if self.started:
                self.env.close()
        finally:
            self.closed = True
            self.save("backend_error" if self.broken else "completed" if self.dispatch.done else "interrupted")


async def serve(config):
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool
    # All upstream debugging goes to stderr, stdout is exclusively MCP JSON-RPC.
    with redirect_stdout(sys.stderr):
        episode = Episode(config)
    server = Server("world_audit", instructions=episode.instructions())
    lock = asyncio.Lock()

    @server.list_tools()
    async def list_tools():
        return [Tool(name=s["name"], description=s["description"], inputSchema=s["parameters"])
                for s in episode.schemas.values()]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        async with lock:
            with redirect_stdout(sys.stderr):
                return episode.invoke(name, arguments)

    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        with redirect_stdout(sys.stderr):
            episode.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    load_upstream(config["upstream"])
    asyncio.run(serve(config))


if __name__ == "__main__":
    main()
