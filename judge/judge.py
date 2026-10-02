"""GPT-6 binary bug-discovery judge: rubric + model output + optional images."""
import argparse
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from judge.codex_metrics import usage_from_events

PROMPT_PATH = Path(__file__).with_name("judge_prompt.md")
SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "score": {"type": "integer", "enum": [0, 1]},
    },
    "required": ["reason", "score"],
    "additionalProperties": False,
}


def validate_result(value):
    if not isinstance(value, dict) or set(value) != {"reason", "score"}:
        raise ValueError("Judge must return exactly reason and score")
    if type(value["score"]) is not int or value["score"] not in (0, 1):
        raise ValueError("Judge score must be the integer 0 or 1")
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise ValueError("Judge reason must be a nonempty string")
    return {"reason": value["reason"], "score": value["score"]}


def read_images(paths):
    if not paths:
        return []
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Image input requires Pillow: python3 -m pip install pillow") from exc
    images = []
    for path in paths:
        data = path.read_bytes()
        try:
            with Image.open(io.BytesIO(data)) as image:
                image_format = image.format
                if image_format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Use PNG, JPEG or WebP screenshots")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Use separate still screenshots, not an animation")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError(f"Cannot decode screenshot {path.name}: {exc}") from exc
        suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image_format]
        images.append((path.name, suffix, data))
    return images


def judge(rubrics, model_output, images=(), *, model="gpt-6-astra",
          reasoning_effort="medium", timeout=300, codex="codex", metrics_dir=None,
          instructions=None):
    if not rubrics.strip():
        raise ValueError("Rubrics must not be empty")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be a finite positive number")
    binary = shutil.which(codex)
    if not binary:
        raise ValueError("Codex CLI not found; install/login or supply --codex-bin")
    instructions = PROMPT_PATH.read_text(encoding="utf-8") if instructions is None else instructions
    payload = {
        "rubrics": rubrics,
        "model_output": model_output,
        "screenshots": [{"id": f"image_{i}", "filename": name}
                        for i, (name, _, _) in enumerate(images, 1)],
    }
    # Each call has fresh context. Input text is data, never shell code.
    with tempfile.TemporaryDirectory(prefix="bug-judge-") as directory:
        root = Path(directory)
        schema = root / "schema.json"
        schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
        result_path = root / "result.json"
        work = root / "work"
        work.mkdir()
        config = {
            "developer_instructions": instructions,
            "model_reasoning_effort": reasoning_effort,
            "forced_login_method": "chatgpt",
            "approval_policy": "never",
            "web_search": "disabled",
            "project_doc_max_bytes": 0,
            "features.shell_tool": False,
            "features.unified_exec": False,
            "features.view_image": False,
            "features.multi_agent": False,
        }
        command = [binary, "exec", "--ignore-user-config", "--ephemeral",
                   "--skip-git-repo-check", "--sandbox", "read-only",
                   "--model", model, "--color", "never", "--json", "-C", str(work)]
        for key, value in config.items():
            command.extend(["-c", key + "=" + json.dumps(value, ensure_ascii=False)])
        for i, (_, suffix, data) in enumerate(images, 1):
            # Neutral attachment names also avoid the CLI's comma-separated-path parsing.
            attachment = root / (f"image_{i}" + suffix)
            attachment.write_bytes(data)
            command.extend(["--image", str(attachment)])
        command.extend(["--output-schema", str(schema),
                        "--output-last-message", str(result_path), "-"])
        env = os.environ.copy()
        # Match the existing native GPT-6 runner: subscription auth, no API-key fallback.
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)
        started = time.perf_counter()

        def save_metrics(stdout, stderr, returncode):
            if metrics_dir is None:
                return
            directory = Path(metrics_dir)
            directory.mkdir(parents=True, exist_ok=True)
            stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else (stdout or "")
            stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else (stderr or "")
            (directory / "judge-native-events.jsonl").write_text(stdout, encoding="utf-8")
            (directory / "judge-native-stderr.log").write_text(stderr, encoding="utf-8")
            metrics = {**usage_from_events(stdout), "model": model, "reasoning_effort": reasoning_effort,
                       "codex_binary": binary, "command": command, "exit_code": returncode,
                       "wall_s": round(time.perf_counter() - started, 3), "images": len(images),
                       "cost_usd": None, "cost_basis": "ChatGPT subscription; no API invoice inferred"}
            (directory / "judge-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")

        try:
            completed = subprocess.run(
                command, input="Evaluate this input data:\n" + json.dumps(payload, ensure_ascii=False),
                text=True, encoding="utf-8", capture_output=True,
                timeout=timeout, env=env, cwd=work,
            )
        except subprocess.TimeoutExpired as exc:
            save_metrics(exc.stdout, exc.stderr, -1)
            raise RuntimeError(f"Judge timed out after {timeout:g}s; no score produced") from exc
        save_metrics(completed.stdout, completed.stderr, completed.returncode)
        if completed.returncode:
            raise RuntimeError(f"Codex exited {completed.returncode}; no score produced.\n"
                               + completed.stderr[-2000:])
        if not result_path.is_file():
            raise RuntimeError("Codex did not return a final result; no score produced")
        try:
            return validate_result(json.loads(result_path.read_text(encoding="utf-8")))
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError(f"Invalid judge result; no score produced: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--task", help="Task ID from the unified Hugging Face dataset")
    source.add_argument("--rubrics", type=Path, help="Explicit UTF-8 rubric file for custom or archival evaluation")
    parser.add_argument("--dataset", type=Path, help="Local task Parquet; default uses the pinned HF release")
    parser.add_argument("--model-output", type=Path, required=True, help="UTF-8 model output file")
    parser.add_argument("--images", type=Path, nargs="+", action="extend", default=[],
                        help="Optional screenshots, in supplied order; repeatable")
    parser.add_argument("--output", type=Path, help="Also save the JSON result to this file")
    parser.add_argument("--model", default="gpt-6-astra", help="Exact judge model; no substitution")
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh"], default="medium")
    parser.add_argument("--timeout", type=float, default=300, help="Maximum call time in seconds")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable")
    args = parser.parse_args(argv)
    try:
        inputs = [args.rubrics, args.dataset, args.model_output, *args.images]
        if args.output and args.output.resolve() in {p.resolve() for p in inputs if p is not None}:
            raise ValueError("Output path must not overwrite an input file")
        instructions = None
        if args.task:
            from data.tasks import load_task
            task = load_task(args.task, args.dataset)
            rubrics = json.dumps(task['rubric'], ensure_ascii=False, indent=2)
        else:
            rubrics = args.rubrics.read_text(encoding="utf-8")
        result = judge(rubrics,
                       args.model_output.read_text(encoding="utf-8"), read_images(args.images),
                       model=args.model, reasoning_effort=args.reasoning_effort,
                       timeout=args.timeout, codex=args.codex_bin,
                       metrics_dir=args.output.parent if args.output else None,
                       instructions=instructions)
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Leave any previous result intact if writing the new result fails.
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent,
                                             prefix=".judge-", delete=False) as file:
                temporary = Path(file.name)
                try:
                    file.write(text)
                    file.close()
                    temporary.replace(args.output)
                finally:
                    temporary.unlink(missing_ok=True)
        sys.stdout.write(text)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"judge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
