"""Native Gemini AfterAgent hook: finish the MCP episode before exiting.

Runs inside the native client's lifecycle; never calls a model or restarts a CLI.
Only local action counters and completion state are read, never grading rubrics.
"""
import json
from pathlib import Path
import sys


def decide(config, meta, state):
    if meta.get("status") in {"completed", "backend_error"}:
        return {}, state
    progress = (meta.get("actions_used", 0), meta.get("tool_calls", 0))
    idle = state.get("idle", 0) + 1 if list(progress) == state.get("progress") else 0
    state = {"progress": list(progress), "idle": idle, "continuations": state.get("continuations", 0) + 1}
    if idle >= 3 or state["continuations"] > 20:
        return {"continue": False, "stopReason": "MCP episode incomplete; continuation limit reached."}, state
    remaining = config["max_actions"] - progress[0]
    if config.get("require_full_budget") and remaining > 0 and progress[1] < config.get("max_tool_calls", 400):
        reason = (f"The audit is incomplete: {progress[0]}/{config['max_actions']} environment actions used. "
                  "Continue exploring and verifying through world_audit MCP tools, even if a bug was found. "
                  "Read the assigned example and observe if not already done. Use the remaining action budget, "
                  "then update your reports and call done. Do not end with a text-only response.")
    else:
        reason = ("The MCP episode is still open. Call world_audit report now with every bug you found (or an empty list)."
                  if config.get("replay_mode") == "vqa" else
                  "The MCP episode is still open. Finalize your bug reports and call world_audit done now.")
    return {"decision": "block", "reason": reason}, state


def main():
    json.load(sys.stdin)
    path = Path(sys.argv[1])
    config = json.loads(path.read_text())
    meta_path = Path(config["run_dir"]) / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    state_path = path.parent / "continuation-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    result, state = decide(config, meta, state)
    state_path.write_text(json.dumps(state) + "\n")
    with (path.parent / "continuations.jsonl").open("a") as f:
        f.write(json.dumps({"actions_used": meta.get("actions_used", 0), "result": result}) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
