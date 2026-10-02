"""Validated, immutable-per-run visual demonstrations shared by native clients."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil


class ExamplePack:
    def __init__(self, directory, code=None):
        self.root = Path(directory).resolve()
        try:
            source = json.loads((self.root / "context.json").read_text())
            exclusions = json.loads((self.root / "exclude_from_eval.json").read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot load ICL pack at {self.root}: {exc}") from exc
        messages = source.get("messages", [])
        if not messages or len(messages) % 2:
            raise ValueError("ICL requires nonempty user/assistant demonstration pairs")
        self.examples = {}
        self.images = {}
        clean_messages = []
        for index in range(0, len(messages), 2):
            pair = messages[index:index + 2]
            if [m.get("role") for m in pair] != ["user", "assistant"]:
                raise ValueError("ICL pairs must contain user input followed by reference answer")
            blocks = pair[0].get("content", [])
            heading = blocks[0].get("text", "") if blocks else ""
            match = re.match(r"^([A-Z][0-9]+)\s+—\s+([^\n]+)", heading)
            if not match or match[1] in self.examples:
                raise ValueError("Each ICL example needs a unique category code and title")
            example_code, title = match.groups()
            if code is not None and example_code != code:
                continue
            cleaned = []
            count = 0
            for message in pair:
                content = []
                for block in message["content"]:
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        content.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image" and message["role"] == "user":
                        rel = Path(block["path"])
                        path = (self.root / rel).resolve()
                        if rel.is_absolute() or ".." in rel.parts or not path.is_relative_to(self.root):
                            raise ValueError("ICL images must be inside the example pack")
                        raw = path.read_bytes()
                        mime = block.get("media_type")
                        if not ((mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or
                                (mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"))):
                            raise ValueError("ICL images must be genuine PNG/JPEG files with matching MIME type")
                        self.images[str(rel)] = hashlib.sha256(raw).hexdigest()
                        content.append({"type": "image", "path": str(rel), "media_type": mime})
                        count += 1
                    else:
                        raise ValueError("ICL allows only text and user-side image blocks")
                if not content:
                    raise ValueError("ICL input and reference answer must not be empty")
                cleaned.append({"role": message["role"], "content": content})
            if not 1 <= count <= 3:
                raise ValueError(f"ICL {example_code} must have 1–3 images")
            self.examples[example_code] = {"title": title, "messages": cleaned, "image_count": count}
            clean_messages.extend(cleaned)
        if not self.examples:
            raise ValueError(f"No ICL example for subcategory {code}; provide a matching example pack or explicitly use --no-icl")
        ids = exclusions.get("task_ids", []) + exclusions.get("additional_aliases", [])
        if not ids or any(not isinstance(v, str) or not v.strip() for v in ids):
            raise ValueError("ICL requires a nonempty task/alias exclusion list")
        self.excluded = sorted(set(v.strip().casefold() for v in ids))
        self.context = {"messages": clean_messages}
        payload = {"context": self.context, "images": self.images, "excluded": self.excluded}
        self.sha256 = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def check_task(self, task, allow_overlap=False):
        overlap = task.strip().casefold() in self.excluded
        if overlap and not allow_overlap:
            raise ValueError(f"Task {task} is an ICL demonstration/alias; choose a held-out task. "
                             "For connection checks only, use --allow-icl-overlap (not eligible for evaluation).")
        return overlap

    def snapshot(self, directory):
        target = Path(directory)
        target.mkdir(parents=True)
        (target / "context.json").write_text(json.dumps(self.context, ensure_ascii=False, indent=2) + "\n")
        (target / "exclude_from_eval.json").write_text(json.dumps({"task_ids": self.excluded}, indent=2) + "\n")
        for rel in self.images:
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / rel, dest)
        saved = ExamplePack(target)
        if saved.sha256 != self.sha256:
            raise ValueError("ICL source changed while preparing the run")
        return saved

    def manifest(self):
        return {"enabled": True, "sha256": self.sha256, "codes": list(self.examples),
                "example_count": len(self.examples),
                "image_count": sum(e["image_count"] for e in self.examples.values()),
                "delivery": "mcp-before-observation", "excluded_task_ids": self.excluded}

    def content(self, code):
        from mcp.types import TextContent, ImageContent
        contents = [TextContent(type="text", text=(
            f"ICL demonstration {code}: {self.examples[code]['title']}. "
            "This is a reference example from another task, not evidence in your assigned scene. "
            "The reference answer is supplied below; do not report this example as a new bug."))]
        refs = []
        for message in self.examples[code]["messages"]:
            if message["role"] == "assistant":
                contents.append(TextContent(type="text", text="Reference answer (demonstration):"))
            for block in message["content"]:
                if block["type"] == "text":
                    contents.append(TextContent(type="text", text=block["text"]))
                else:
                    raw = (self.root / block["path"]).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != self.images[block["path"]]:
                        raise ValueError("ICL snapshot image changed after startup")
                    contents.append(ImageContent(type="image", data=base64.b64encode(raw).decode(),
                                                 mimeType=block["media_type"]))
                    refs.append(f"icl:{code}:{len(refs) + 1}")
        return contents, refs
