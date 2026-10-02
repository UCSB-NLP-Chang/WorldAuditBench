#!/usr/bin/env python3
"""Prepare an identical MCP episode, then start exactly one native CLI process."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from auditor.mcp_agent.examples import ExamplePack
from auditor.task_dataset import example_checksum, load_task, ensure_examples

BASE = ROOT / "out/native-agents"
DEFAULT_ICL = ROOT / "examples/icl"
DEFAULT_TASK_CATALOG = Path(__file__).with_name("task-subcategories.json")
DEFAULT_SCENE_CATALOG = Path(__file__).with_name("task-scenes.json")
MODELS = {"codex": "gpt-6-astra", "gemini": "gemini-3.8-flash", "claude": "claude-opus-5", "qwen": "qwen3.8-flash", "muse": "muse-spark-1.3",
          "opencode": "openrouter/meta/muse-spark-1.3-contributor"}
QWEN_TOKEN_PLAN_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
TOOLS = ["read_example", "observe", "move", "turn", "look", "interact", "wait", "inspect", "history",
         "write_notes", "flag_bug", "update_bug", "list_bugs", "done"]
REPLAY_TOOLS = ["read_example", "observe", "play", "inspect", "history", "write_notes", "flag_bug", "update_bug", "list_bugs", "done"]
REPLAY_ALL_TOOLS = ["read_example", "observe", "inspect", "history", "write_notes", "flag_bug", "update_bug", "list_bugs", "done"]
NO_INSPECT_TOOLS = ["read_example", "observe", "history", "write_notes", "flag_bug", "update_bug", "list_bugs", "done"]
VQA_TOOLS = ["read_example", "observe", "report"]
DEFAULT_INSTRUCTION = (
    "Inspect the assigned 3D environment for anomalies. Explore and gather visual evidence. "
    "Report each distinct anomaly with a clear description and evidence frame references."
)


def cli_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("client", choices=MODELS)
    p.add_argument("--model", help="Exact model ID; defaults to the requested model, never auto-substituted")
    p.add_argument("--environment", choices=["fake", "unreal-http", "threejs", "vla-replay"], required=True)
    p.add_argument("--replay-dir", type=Path, help="vla-replay: the VLA recording episode directory (meta.json, poses.jsonl, f*.jpg)")
    p.add_argument("--preview-every", type=float, default=5.0, help="vla-replay: seconds between the preview frames delivered with observe")
    p.add_argument("--inspect-budget", type=int, default=None, help="maximum inspect calls per run; 0 removes the inspect tool (default: unlimited)")
    p.add_argument("--inline-low-res", action="store_true", help="vla-replay all: show the inline frames at film resolution (480x288) instead of the final-view resolution")
    p.add_argument("--replay-mode", choices=["play", "all", "vqa"], default="play",
                   help="vla-replay: play = the model plays segments (play tool, action budget); all = observe delivers every recorded frame "
                        "at once (film resolution) plus the explorer's track, no environment actions (max-actions 0)")
    p.add_argument("--browser-config", type=Path, help="Operator-only pinned page configuration")
    p.add_argument("--env-url", help="Dedicated /reset /step environment endpoint, usually over an SSH tunnel")
    p.add_argument("--task", required=True, help="Backend task ID (not rubric or bug description)")
    p.add_argument("--dataset", type=Path, help="Local unified task Parquet; default downloads the pinned HF release once")
    p.add_argument("--legacy-task-files", action="store_true", help="Use archived JSON catalogs and external ICL images")
    p.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    p.add_argument("--prompt-file", type=Path, help="Task instruction text; no hidden labels")
    p.add_argument("--scene-catalog", type=Path, default=DEFAULT_SCENE_CATALOG,
                   help="Public environment descriptions indexed by task ID")
    p.add_argument("--scene-description-file", type=Path,
                   help="Explicit public environment description; never use task answers or rubrics")
    icl = p.add_mutually_exclusive_group()
    icl.add_argument("--icl-dir", type=Path, default=DEFAULT_ICL, help="Visual demonstration pack; enabled by default")
    icl.add_argument("--no-icl", action="store_true", help="Explicit zero-shot ablation; do not load examples")
    p.add_argument("--subcategory", help="Exact task subcategory, e.g. C3; required for tasks absent from the catalog")
    p.add_argument("--task-catalog", type=Path, default=DEFAULT_TASK_CATALOG,
                   help="Task-to-subcategory map; never passed to the model")
    p.add_argument("--require-full-budget", action="store_true", help="Require the action budget before done, except on environment/tool-budget failure")
    p.add_argument("--allow-icl-overlap", action="store_true", help="Allow demonstration tasks for smoke tests only; marks run ineligible for evaluation")
    p.add_argument("--max-actions", type=int, default=40)
    p.add_argument("--max-tool-calls", type=int, default=400)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--observation", choices=["on-demand", "film", "final"], default="on-demand")
    p.add_argument("--reasoning-effort", default="low", choices=["low", "medium", "high", "xhigh"],
                   help="Codex-only; Gemini keeps its native reasoning policy")
    p.add_argument("--gemini-auth", choices=["oauth-personal", "gemini-api-key"], default="oauth-personal")
    p.add_argument("--gemini-thinking", choices=["low", "medium", "high"], default="medium",
                   help="Gemini thinking level; explicit medium baseline")
    p.add_argument("--qwen-effort", choices=["low", "medium", "high"], default="medium", help="Qwen Code generationConfig.reasoning.effort")
    p.add_argument("--qwen-base-url", default=QWEN_TOKEN_PLAN_URL, help="OpenAI-compatible endpoint for Qwen Code (Token Plan, Singapore)")
    p.add_argument("--qwen-api-key-file", type=Path, help="Qwen API key file, read into the child environment only")
    p.add_argument("--qwen-context-window", type=int, default=None,
                   help="declare the model's context window (tokens) to Qwen Code; needed for models it does not know (e.g. OpenRouter ones), otherwise it refuses large prompts")
    p.add_argument("--muse-effort", choices=["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"], default="medium", help="Muse --reasoning-effort")
    p.add_argument("--muse-base-url", default=None,
                   help="route Muse Code's Meta provider to another Responses-API endpoint, pinned in the private settings.json "
                        "(endpoint_transport, auth bearer) with a local model_catalog row for --model. For OpenRouter use the "
                        "namespace-restoring relay: scripts/native-agents/muse_openrouter_proxy.py --port 18090 and "
                        "--muse-base-url http://127.0.0.1:18090/api/v1 (OpenRouter drops the tool namespaces Muse relies on)")
    p.add_argument("--muse-api-key-file", type=Path, default=None, help="API key for --muse-base-url, passed as META_API_KEY to the child only")
    p.add_argument("--muse-context-window", type=int, default=1000000, help="context_limit of the local model_catalog row used with --muse-base-url")
    p.add_argument("--muse-supports-video", action="store_true", help="mark the local model_catalog row supports_video (Muse then sends multi-image tool results as video)")
    p.add_argument("--opencode-effort", choices=["minimal", "low", "medium", "high", "xhigh", "max"], default="medium",
                   help="OpenCode --variant (the model's reasoning effort variant)")
    p.add_argument("--opencode-api-key-file", type=Path, default=None, help="OpenRouter key for the opencode client, passed as OPENROUTER_API_KEY to the child only")
    p.add_argument("--opencode-context-window", type=int, default=1048576, help="context limit declared for the model in the private opencode.json")
    p.add_argument("--opencode-base-url", default=None, help="override the provider baseURL in the private opencode.json (debugging through a relay)")
    p.add_argument("--opencode-home", type=Path, default=None,
                   help="shared XDG config dir for OpenCode (its provider SDK install, ~60 MB); default out/native-agents/opencode-home. "
                        "Sessions/cache stay per run and are deleted after the CLI exits (the transcript is in native-events.jsonl)")
    p.add_argument("--muse-config-dir", type=Path, default=Path.home() / ".config/muse", help="Muse config dir whose auth.json holds the Meta login")
    p.add_argument("--mcp-output-tokens", type=int, default=4_000_000, help="Claude Code MAX_MCP_OUTPUT_TOKENS for the session (tool results above it are truncated)")
    p.add_argument("--claude-effort", choices=["low", "medium", "high", "xhigh", "max"], default="high",
                   help="Claude Code effort level for the session (native --effort); keep it equal to the embodied Claude batch")
    p.add_argument("--gemini-api-key-file", type=Path,
                   help="Read API credential from a local file into child environment only")
    p.add_argument("--run-dir", type=Path, help="New empty run directory")
    p.add_argument("--cli", help="Explicit path to native client executable")
    p.add_argument("--dry-run", action="store_true", help="Write configurations without logging in, calling a model, or starting an environment")
    p.add_argument("--interactive", action="store_true", help="Use native interactive UI instead of headless execution")
    return p


def toml_inline(value):
    if isinstance(value, dict):
        return "{ " + ", ".join(json.dumps(k) + " = " + toml_inline(v) for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(toml_inline(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def task_subcategory(args):
    """Use the operator's task metadata, never ask the model to guess its category."""
    requested = args.subcategory.strip().upper() if args.subcategory else None
    row = unified_task(args)
    if row is not None:
        known = row['subcategory']
        if requested and requested != known:
            raise ValueError(f"Task {args.task} is {known} in the dataset, not {requested}")
        return known
    mapping = {}
    if args.task_catalog.exists():
        mapping = json.loads(args.task_catalog.read_text())["task_subcategories"]
    matches = {v.strip().upper() for k, v in mapping.items() if k.strip().casefold() == args.task.strip().casefold()}
    if len(matches) > 1:
        raise ValueError(f"Conflicting subcategories in task catalog for {args.task}")
    known = next(iter(matches), None)
    if known and requested and known != requested:
        raise ValueError(f"Task {args.task} is {known} in the catalog, not {requested}")
    code = known or requested
    if not code:
        raise ValueError(f"No subcategory metadata for task {args.task}; provide --subcategory or --task-catalog. "
                         "ICL never falls back to all examples or another category.")
    return code


def scene_description(args):
    if args.scene_description_file:
        description = args.scene_description_file.read_text().strip()
    elif args.environment == "fake":
        description = "A synthetic test environment used only to verify the agent/tool interface; not a real game scene."
    elif unified_task(args) is not None:
        description = unified_task(args)['input']['scene_description']
    else:
        scenes = json.loads(args.scene_catalog.read_text())["scenes"]
        matches = {s["description"]["en"].strip() for s in scenes
                   if any(t.strip().casefold() == args.task.strip().casefold() for t in s["task_ids"])}
        if len(matches) > 1:
            raise ValueError(f"Conflicting scene descriptions for task {args.task}")
        description = next(iter(matches), "")
    if not description:
        raise ValueError(f"Missing environment description for {args.task}; provide --scene-description-file or update --scene-catalog")
    return description


def unified_task(args):
    if args.legacy_task_files or (args.environment == 'fake' and args.dataset is None):
        return None
    key = (args.task, args.dataset)
    if getattr(args, '_dataset_key', None) != key:
        args._dataset_row = load_task(args.task, args.dataset)
        args._dataset_key = key
    return args._dataset_row


def prepare(args):
    if args.client in ("qwen", "muse", "opencode") and args.interactive:
        raise ValueError("qwen, muse and opencode run headless here")
    if args.client == "claude" and args.interactive:
        raise ValueError("Claude Code runs headless here (-p); interactive mode is not wired")
    if args.client == "codex" and args.interactive:
        raise ValueError("Use headless Codex exec: this installed CLI only supports --ignore-user-config on exec")
    replay_all = args.environment == "vla-replay" and args.replay_mode in ("all", "vqa")
    replay_vqa = args.environment == "vla-replay" and args.replay_mode == "vqa"
    if replay_all and args.max_actions != 0:
        raise ValueError("--replay-mode all has no environment actions; pass --max-actions 0")
    if replay_all and args.require_full_budget:
        raise ValueError("--require-full-budget does not apply to --replay-mode all")
    if not (0 if replay_all else 1) <= args.max_actions <= 10000 or not args.max_tool_calls >= args.max_actions:
        raise ValueError("Require 1..10000 actions and max-tool-calls >= max-actions")
    if not 0 <= args.seed <= 2147483647:
        raise ValueError("Seed must be a nonnegative 32-bit integer")
    if args.environment == "unreal-http" and not args.env_url:
        raise ValueError("--env-url is required; the review website is not an environment action endpoint")
    if args.environment == "vla-replay":
        if not args.replay_dir or not (args.replay_dir / "meta.json").exists():
            raise ValueError("--replay-dir must point at a VLA recording episode directory")
        if not 0.5 <= args.preview_every <= 60:
            raise ValueError("--preview-every must be between 0.5 and 60 seconds")
    subcategory = None if args.no_icl else task_subcategory(args)
    row = unified_task(args)
    if row is not None and not args.no_icl:
        examples = ExamplePack(ensure_examples() if args.icl_dir == DEFAULT_ICL else args.icl_dir, code=subcategory)
        if examples.sha256 != example_checksum(subcategory):
            raise ValueError('Shared examples differ from the dataset release')
    else:
        examples = None if args.no_icl else ExamplePack(args.icl_dir, code=subcategory)
    if examples:
        examples.check_task(args.task, args.allow_icl_overlap)
        if args.max_tool_calls < len(examples.examples) + 2:
            raise ValueError("Tool-call budget must cover every ICL example, observe, and done")
    scene = scene_description(args)
    python = BASE / "venv/bin/python"
    upstream = ROOT
    if not python.exists() or not (upstream / "agent/tools.py").exists():
        raise ValueError("Run python3 scripts/native-agents/setup.py first")
    # Verify the bundled implementation without cloning a second private repository.
    pin = json.loads(Path(__file__).with_name("upstream.json").read_text())
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT / "agent").rglob("*.py"))
              if "tests" not in p.relative_to(ROOT / "agent").parts}
    if hashes != pin["bundled_files"]:
        raise ValueError("Bundled agent tools differ from upstream.json; review changes and update the source pin")
    revision = "bundled-sha256:" + hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run = (args.run_dir or BASE / "runs" / f"{stamp}-{args.client}-{uuid.uuid4().hex[:6]}").resolve()
    if run.exists() and any(run.iterdir()):
        raise ValueError("Run directory must be new or empty; native sessions are never silently resumed")
    run.mkdir(parents=True, exist_ok=True)
    work = run / "workspace"
    work.mkdir()
    icl_manifest = {"enabled": False}
    if examples:
        examples = examples.snapshot(run / "icl")
        icl_manifest = examples.manifest()
    episode_dir = run / "episode"
    model = args.model or MODELS[args.client]
    instruction = args.prompt_file.read_text() if args.prompt_file else args.instruction
    if row is not None and not args.prompt_file and args.instruction == DEFAULT_INSTRUCTION:
        instruction = row['input']['instruction']
    episode = {"upstream": str(upstream), "run_dir": str(episode_dir), "environment": args.environment,
               "environment_url": args.env_url, "task": args.task, "instruction": instruction,
               "max_actions": args.max_actions, "max_tool_calls": args.max_tool_calls,
               "require_full_budget": args.require_full_budget,
               "seed": args.seed, "observation": args.observation, "inspect_budget": args.inspect_budget,
               "icl": icl_manifest, "icl_directory": str(examples.root) if examples else None,
               "subcategory": subcategory,
               "scene_description": scene,
               "allow_icl_overlap": args.allow_icl_overlap}
    if args.environment == "vla-replay":
        recording = json.loads((args.replay_dir / "meta.json").read_text())
        restored = args.replay_dir / "frames.restored.json"
        episode["replay_dir"] = str(args.replay_dir.resolve())
        episode["preview_every"] = args.preview_every
        episode["replay_mode"] = args.replay_mode
        episode["inline_full_res"] = not args.inline_low_res
        episode["recording"] = {"kind": recording.get("kind"), "explorer": recording.get("model"), "task": recording.get("task"),
                                "frames": len(recording.get("frames", [])), "sim_seconds": recording.get("sim_seconds"),
                                "frame_source": json.loads(restored.read_text()) if restored.exists() else "recorded jpeg"}
    if args.environment == "threejs":
        if not args.browser_config:
            raise ValueError("--browser-config is required")
        browser = json.loads(args.browser_config.read_text())
        for key in ["browser_root", "browser_page", "browser_case", "page_sha256"]:
            episode[key] = browser[key]
    episode_path = run / "episode-config.json"
    episode_path.write_text(json.dumps(episode, indent=2) + "\n")
    mcp_args = [str(ROOT / "auditor/mcp_agent/server.py"), "--config", str(episode_path)]
    common = {"command": str(python), "args": mcp_args}
    tools = (VQA_TOOLS if replay_vqa else REPLAY_ALL_TOOLS if replay_all else REPLAY_TOOLS) if args.environment == "vla-replay" else TOOLS
    if args.inspect_budget == 0:
        tools = [t for t in tools if t != "inspect"]
    if args.inspect_budget is not None and args.inspect_budget < 0:
        raise ValueError("--inspect-budget must be >= 0")
    if replay_vqa:
        budget = ("You are reviewing a recording made by a separate explorer; you do not control the camera. "
                  "There are no environment actions and no memory tools: observe returns the start view, every recorded frame of the "
                  "recording (0.5 s apart) and the explorer's track. Answer with ONE report call listing every distinct bug with "
                  "evidence frame refs (an empty list if the recording shows no bug); that report ends the inspection. ")
    elif replay_all:
        budget = ("You are reviewing a recording made by a separate explorer; you do not control the camera. "
                  f"There are no environment actions: observe returns the start view, {'full' if not args.inline_low_res else 'low'}-resolution "
                  f"frames of the whole recording (every {args.preview_every:g} s; every recorded frame, 0.5 s apart, is archived) and the "
                  "explorer's track; " + ("there is no inspect tool: report from the shown frames. " if args.inspect_budget == 0 else
                  "inspect zooms into a region or shows an archived frame that is not displayed. "))
    elif args.environment == "vla-replay":
        budget = (f"You are reviewing a recording made by a separate explorer; you do not control the camera. "
                  f"You have {args.max_actions} play actions (play(from_s, to_s) plays any segment of the recording, at most 4 s each, "
                  "in any order; observe returns the start view plus low-resolution preview frames of the whole recording). ")
    else:
        budget = f"You have {args.max_actions} environment actions. "
    memory = ("Use write_notes to retain " if args.inspect_budget == 0
              else "Inspect selected archived frames for details, and use write_notes to retain ")
    cap = f"You may call inspect at most {args.inspect_budget} times. " if args.inspect_budget else ""
    reporting = ("" if replay_vqa else f"{memory}progress. Report bugs through flag_bug/update_bug and finish with done. {cap}")
    prompt = (
        f"{instruction}\n\nEnvironment description:\n{scene}\n\n"
        "This is an environment auditing run using only world_audit MCP tools. "
        f"The task is already assigned by the operator. {budget}{reporting}"
        "Do not use shell, files, web, delegation, or tools outside world_audit. "
        "If the MCP server cannot be reached, report the failure; do not invent observations."
    )
    if examples:
        prompt += (
            f"\nThis task's specific subcategory is {subcategory}. Before observe or any scene action, "
            f"call read_example(code=\"{subcategory}\") to read its ONE matching demonstration. "
            "Only this subcategory's example is available for this task. The result contains a category definition, 1–3 real images "
            "with figure captions. Deliver ONE example per tool execution, then return to the model "
            "before reading the next. Do not batch or loop over examples in a single code-mode exec: "
            "the combined image payload can exceed client transport limits. In code mode, forward each "
            "image block using image(block) and text block using text(block.text); do not stringify images. "
            "Each example also contains "
            "a reference answer. These are supplied demonstrations, not questions "
            "you need to answer. Read this example, then call observe to start your assigned scene. "
            "Do not use example images as evidence for your own bug reports. "
            "You may re-read a category with read_example(code) after context compaction. "
            "Example reads do not consume environment actions, but count toward the tool-call budget."
        )
    else:
        prompt += "\nThis is a zero-shot run with no ICL examples. Start with observe."
    if args.environment == "fake":
        prompt += "\nThis is a SYNTHETIC transport smoke test, not a real Unreal benchmark."
    (run / "prompt.txt").write_text(prompt + "\n")
    env = os.environ.copy()
    binary = args.cli or shutil.which(args.client) or args.client
    if args.client == "codex":
        config = {
            "model": model, "model_reasoning_effort": args.reasoning_effort,
            "forced_login_method": "chatgpt", "approval_policy": "never", "sandbox_mode": "read-only",
            "web_search": "disabled", "project_doc_max_bytes": 0,
            "features.shell_tool": False, "features.unified_exec": False,
            "features.view_image": False, "features.multi_agent": False,
            "mcp_servers.world_audit": {**common, "enabled_tools": tools, "required": True,
                                        "startup_timeout_sec": 30, "tool_timeout_sec": 240,
                                        "default_tools_approval_mode": "approve"},
        }
        overrides = [part for k, v in config.items() for part in ("-c", k + "=" + toml_inline(v))]
        command = [binary, "exec", "--ignore-user-config", *overrides,
                   "--skip-git-repo-check", "--json", "--color", "never",
                   "-C", str(work), "--output-last-message", str(run / "final.txt"), "-"]
        # Subscription mode is explicit; do not fall back to an API key from the environment.
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)
        (run / "codex-overrides.json").write_text(json.dumps(config, indent=2) + "\n")
    elif args.client == "qwen":
        # Qwen Code (Gemini CLI fork) headless: system settings file with the OpenAI-compatible provider (Token Plan endpoint,
        # key through the environment only), reasoning effort, only the world_audit MCP server, built-in tools off, the Stop
        # hook as completion guard (same after_agent.py rule as Gemini's AfterAgent and Claude's Stop).
        hook = run / "after-agent.py"
        shutil.copyfile(ROOT / "scripts/native-agents/after_agent.py", hook)
        settings = {
            "model": {"name": model},
            "modelProviders": {"openai": [{"id": model, "name": model, "baseUrl": args.qwen_base_url, "envKey": "QWEN_API_KEY",
                                           "capabilities": {"vision": True},
                                           "generationConfig": {"reasoning": {"effort": args.qwen_effort},
                                                                **({"contextWindowSize": args.qwen_context_window} if args.qwen_context_window else {})}}]},
            "security": {"auth": {"selectedType": "openai"}},
            "tools": {"core": []}, "mcp": {"allowed": ["world_audit"]},
            "mcpServers": {"world_audit": {**common, "trust": True, "includeTools": tools, "timeout": 240000}},
            "hooksConfig": {"enabled": True},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "timeout": 10000,
                                          "command": shlex.join([str(python), str(hook), str(episode_path)])}]}]},
            "context": {"fileName": "AUDIT_NATIVE_CONTEXT.md"},
        }
        settings_path = run / "qwen-settings.json"
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        env["QWEN_CODE_SYSTEM_SETTINGS_PATH"] = str(settings_path)
        if args.qwen_api_key_file:
            key = args.qwen_api_key_file.read_text().strip()
            env["QWEN_API_KEY"] = key; env["OPENAI_API_KEY"] = key
        env["OPENAI_BASE_URL"] = args.qwen_base_url; env["OPENAI_MODEL"] = model
        env["QWEN_CODE_SUPPRESS_YOLO_WARNING"] = "1"
        command = [binary, "--auth-type", "openai", "-m", model, "--output-format", "stream-json", "--approval-mode", "yolo",
                   "--allowed-mcp-server-names", "world_audit", "-e", "none"]          # prompt on stdin (headless requirement)
    elif args.client == "muse":
        # Muse Code headless (`muse exec --json`): a private XDG config dir per run with a copy of the Meta login and a
        # settings.json that registers only the world_audit stdio MCP server; no workspace tools (no --workspace), shell and
        # writes disabled, approvals off, tool output uncapped so the 120-frame observe result reaches the model.
        cfg = run / "muse-config"
        (cfg / "muse").mkdir(parents=True)
        settings = {"schema_version": 1, "mcpServers": {          # Muse settings.json shape (bundled migrate skill): map by name
            "world_audit": {"type": "stdio", "command": common["command"], "args": list(common["args"]), "tool_timeout_sec": 240}}}
        env.pop("META_API_KEY", None)
        if args.muse_base_url:
            # Meta front door replaced by another endpoint (OpenRouter serves the same /responses wire): the settings pin lets
            # the bearer leave for that host, and a local catalog row (profile "tbh" = this session's profile) stands in for
            # the /muse-code/models catalog the endpoint does not serve.
            settings["endpoint_transport"] = {"base_url": args.muse_base_url, "auth": "bearer"}
            settings["model_catalog"] = [{"model_id": model, "provider_id": "meta", "profile_id": "tbh", "display_label": model,
                                          "visibility": "visible", "context_limit": args.muse_context_window, "output_limit": 32000,
                                          "is_default": True, "enabled": True, "supports_video": args.muse_supports_video}]
            if not args.muse_api_key_file:
                raise ValueError("--muse-base-url needs --muse-api-key-file")
            env["META_API_KEY"] = args.muse_api_key_file.read_text().strip()
        else:
            auth = args.muse_config_dir / "auth.json"
            if not auth.exists():
                raise ValueError("Muse login missing: run muse login (or muse auth set) first")
            shutil.copyfile(auth, cfg / "muse/auth.json")
        (cfg / "muse/settings.json").write_text(json.dumps(settings, indent=2) + "\n")
        env["XDG_CONFIG_HOME"] = str(cfg)
        (run / "prompt-file.txt").write_text(prompt + "\n")
        command = [binary, "exec", "--json", "--model", model, "--reasoning-effort", args.muse_effort, "--prompt-file", str(run / "prompt-file.txt"),
                   "--disable-shell", "--disable-write", "--approval-mode", "never", "--no-session-log", "--max-tool-output-bytes", "0",
                   "--max-model-steps", str(args.max_tool_calls + 10)]
    elif args.client == "opencode":
        # OpenCode headless (`opencode run --format json`): a private opencode.json (OPENCODE_CONFIG) declares the model on the
        # OpenRouter provider (key from OPENROUTER_API_KEY only, never written to disk), registers only the world_audit stdio
        # MCP server and switches every built-in tool off; private XDG dirs keep sessions and logs inside the run; --pure skips
        # external plugins, --auto approves the MCP tools, --title skips the title-generation call (which would use a second model).
        if "/" not in model:
            raise ValueError("opencode models are provider/model ids, e.g. openrouter/meta/muse-spark-1.3-contributor")
        provider, model_id = model.split("/", 1)
        price = json.loads((ROOT / "scripts/native-agents/pricing.json").read_text())["models"].get(model_id, {})
        cost = ({"input": price["input_per_million"], "output": price["output_per_million"], "cache_read": price["cached_input_per_million"]}
                if price else {"input": 0, "output": 0, "cache_read": 0})
        cfg = {"$schema": "https://opencode.ai/config.json", "model": model, "small_model": model, "share": "disabled",
               "provider": {provider: {**({"options": {"baseURL": args.opencode_base_url}} if args.opencode_base_url else {}), "models": {model_id: {
                   "name": model_id, "attachment": True, "reasoning": True, "tool_call": True,
                   "reasoning_options": [{"type": "effort", "values": ["minimal", "low", "medium", "high", "xhigh", "max"]}],
                   "modalities": {"input": ["text", "image"], "output": ["text"]},
                   "limit": {"context": args.opencode_context_window, "output": 65536}, "cost": cost}}}},
               "mcp": {"world_audit": {"type": "local", "command": [common["command"], *common["args"]], "enabled": True, "timeout": 240000}},
               "tools": {t: False for t in ["bash", "read", "write", "edit", "glob", "grep", "list", "webfetch", "websearch", "todowrite",
                                            "todoread", "task", "patch", "multiedit", "skill", "question", "lsp", "apply_patch"]}}
        (run / "opencode.json").write_text(json.dumps(cfg, indent=2) + "\n")
        xdg = run / "opencode-home"
        shared = (args.opencode_home or BASE / "opencode-home").resolve()
        for d in (xdg / "data", xdg / "state", xdg / "cache", shared / "config"):
            d.mkdir(parents=True, exist_ok=True)
        env.update({"OPENCODE_CONFIG": str(run / "opencode.json"), "XDG_CONFIG_HOME": str(shared / "config"), "XDG_DATA_HOME": str(xdg / "data"),
                    "XDG_STATE_HOME": str(xdg / "state"), "XDG_CACHE_HOME": str(xdg / "cache")})
        if args.opencode_api_key_file:
            env["OPENROUTER_API_KEY"] = args.opencode_api_key_file.read_text().strip()
        command = [binary, "run", "--format", "json", "--pure", "--auto", "--model", model, "--variant", args.opencode_effort,
                   "--title", f"world_audit {args.task}", prompt]
    elif args.client == "claude":
        # Claude Code headless: only the world_audit MCP server (strict), no built-in tools, MCP tools pre-approved, no
        # user/project settings, no session persistence; the Stop hook is the same completion guard as Gemini's AfterAgent.
        mcp_cfg = {"mcpServers": {"world_audit": {"type": "stdio", **common}}}
        (run / "claude-mcp.json").write_text(json.dumps(mcp_cfg, indent=2) + "\n")
        hook = run / "after-agent.py"
        shutil.copyfile(ROOT / "scripts/native-agents/after_agent.py", hook)
        settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "timeout": 10,
                                                   "command": shlex.join([str(python), str(hook), str(episode_path)])}]}]}}
        (run / "claude-settings.json").write_text(json.dumps(settings, indent=2) + "\n")
        command = [binary, "-p", "--output-format", "stream-json", "--verbose", "--model", model, "--effort", args.claude_effort,
                   "--mcp-config", str(run / "claude-mcp.json"), "--strict-mcp-config", "--tools", "",
                   "--allowedTools", *[f"mcp__world_audit__{t}" for t in tools], "--permission-mode", "dontAsk",
                   "--no-session-persistence", "--setting-sources", "", "--settings", str(run / "claude-settings.json")]
        env.pop("ANTHROPIC_API_KEY", None)          # subscription login only, like the other clients
        # Claude Code truncates MCP tool results above MAX_MCP_OUTPUT_TOKENS (default 25k, counted on the raw result): a full
        # recording of 120 frames must reach the model uncut, exactly as the other clients receive it.
        env["MAX_MCP_OUTPUT_TOKENS"] = str(args.mcp_output_tokens)
    else:
        settings = {
            "model": {"name": model, "maxSessionTurns": args.max_tool_calls + 10},
            "tools": {"core": []}, "mcp": {"allowed": ["world_audit"]},
            "mcpServers": {"world_audit": {**common, "trust": True, "includeTools": tools, "timeout": 240000}},
            "security": {"auth": {"selectedType": args.gemini_auth}},
            "context": {"fileName": "AUDIT_NATIVE_CONTEXT.md"},
            "modelConfigs": {"customOverrides": [{"match": {"model": model}, "modelConfig": {
                "generateContentConfig": {"thinkingConfig": {"thinkingLevel": args.gemini_thinking.upper()}}
            }}]},
        }
        hook = run / "after-agent.py"
        shutil.copyfile(ROOT / "scripts/native-agents/after_agent.py", hook)
        settings["hooksConfig"] = {"enabled": True}
        settings["hooks"] = {"AfterAgent": [{"hooks": [{
            "name": "audit-completion", "type": "command", "timeout": 10000,
            "command": shlex.join([str(python), str(hook), str(episode_path)])
        }]}]}
        if args.gemini_api_key_file:
            if args.gemini_auth != "gemini-api-key":
                raise ValueError("--gemini-api-key-file requires --gemini-auth gemini-api-key")
            env["GEMINI_API_KEY"] = args.gemini_api_key_file.read_text().strip()
        settings_path = run / "gemini-settings.json"
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(settings_path)
        command = [binary, "--model", model, "--allowed-mcp-server-names", "world_audit", "--extensions", "none"]
        if args.interactive:
            command += ["--prompt-interactive", prompt]
        else:
            command += ["--output-format", "stream-json", "--prompt", prompt]
    protocol = {k: v for k, v in episode.items() if k not in {"upstream", "run_dir", "environment_url", "icl_directory"}}
    protocol["upstream_revision"] = revision
    protocol["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
    protocol["mcp_implementation_sha256"] = hashlib.sha256(b"\n".join(
        p.read_bytes() for p in sorted((ROOT / "auditor/mcp_agent").glob("*.py")))).hexdigest()
    protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    manifest = {"client": args.client, "model_requested": model, "native_single_process": True,
                "reasoning_requested": {"gemini": args.gemini_thinking, "claude": args.claude_effort, "qwen": args.qwen_effort, "muse": args.muse_effort,
                                        "opencode": args.opencode_effort}.get(args.client, args.reasoning_effort),
                "upstream_revision": revision, "protocol_sha256": protocol_hash,
                "mcp_implementation_sha256": protocol["mcp_implementation_sha256"],
                "icl": icl_manifest,
                "subcategory": subcategory,
                "scene_description": scene,
                "prompt_sha256": protocol["prompt_sha256"],
                "evaluation_eligible": args.environment != "fake" and not args.allow_icl_overlap,
                "command": command, "working_directory": str(work), "status": "prepared",
                "mcp_server": "world_audit", "tools": tools, "created_at": stamp}
    (run / "launch.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return run, command, env, prompt, manifest


def main():
    args = cli_parser().parse_args()
    run = None
    manifest = None
    try:
        run, command, env, prompt, manifest = prepare(args)
        print("Run:", run, flush=True)
        print("Model:", manifest["model_requested"], "| protocol:", manifest["protocol_sha256"], flush=True)
        if args.dry_run:
            print("Prepared only; no model call or environment started.")
            return
        if not shutil.which(command[0]):
            raise ValueError(f"Native CLI not found: {command[0]}")
        if args.client == "gemini" and not args.interactive:
            if args.gemini_auth == "oauth-personal" and not (Path.home() / ".gemini/oauth_creds.json").exists():
                raise ValueError("Gemini Google login is missing. Run gemini interactively and sign in with Google, then rerun this script.")
            if args.gemini_auth == "gemini-api-key" and not env.get("GEMINI_API_KEY"):
                raise ValueError("GEMINI_API_KEY is missing for --gemini-auth gemini-api-key")
        if args.client == "codex":
            status = subprocess.run([command[0], "login", "status"], capture_output=True, text=True, env=env)
            if status.returncode or "ChatGPT" not in status.stdout + status.stderr:
                raise ValueError("Codex requires ChatGPT login. Run codex login first.")
        if args.client == "claude":
            status = subprocess.run([command[0], "auth", "status"], capture_output=True, text=True, env=env)
            if status.returncode or '"loggedIn": true' not in status.stdout:
                raise ValueError("Claude Code requires a claude.ai login. Run claude and sign in first.")
        manifest["cli_version"] = subprocess.check_output([command[0], "--version"], text=True, env=env).strip()
        manifest["status"] = "running"
        (run / "launch.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print("Native CLI is running; output:", run / "native-events.jsonl", flush=True)
        import time
        cli_started = time.perf_counter()
        if args.interactive:
            result = subprocess.run(command, cwd=manifest["working_directory"], env=env)
        else:
            with (run / "native-events.jsonl").open("w") as out, (run / "native-stderr.log").open("w") as err:
                feed = {"input": prompt} if args.client in ("codex", "claude", "qwen") else {"stdin": subprocess.DEVNULL}
                result = subprocess.run(command, **feed, text=True,
                                        cwd=manifest["working_directory"], env=env, stdout=out, stderr=err)
        manifest["cli_wall_s"] = round(time.perf_counter() - cli_started, 3)
        if args.client == "opencode":
            shutil.rmtree(run / "opencode-home", ignore_errors=True)      # session db (holds the images again) and caches: ~30 MB per run
        meta = run / "episode/meta.json"
        episode_done = meta.exists() and json.loads(meta.read_text()).get("status") == "completed"
        manifest.update(status="completed" if result.returncode == 0 and episode_done else "failed",
                        native_exit_code=result.returncode, mcp_episode_completed=episode_done)
        (run / "launch.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print("Result:", manifest["status"], "| native exit:", result.returncode)
        if manifest["status"] != "completed":
            print("Check native-stderr.log and native-events.jsonl; a CLI exit alone is not benchmark completion.", file=sys.stderr)
            sys.exit(result.returncode or 1)
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        if run is not None and manifest is not None:
            manifest.update(status="startup_failed", error=str(e))
            (run / "launch.json").write_text(json.dumps(manifest, indent=2) + "\n")
        sys.exit(str(e))


if __name__ == "__main__":
    main()
