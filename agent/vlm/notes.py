"""The model's durable notes (notes.md). During an epoch the model appends short entries
(write_notes); at compaction it rewrites the whole file as its continuation state, and the
rebuilt context carries the file verbatim."""
from pathlib import Path


class Notes:
    def __init__(self, run_dir):
        self.path = Path(run_dir) / "notes.md"

    def read(self) -> str:
        return self.path.read_text() if self.path.exists() else ""

    def write(self, text: str) -> None:
        """Replace the notes (used for the compaction rewrite)."""
        self.path.write_text(text.strip())

    def append(self, text: str) -> None:
        """Add one entry on its own line; blank text is ignored."""
        text = text.strip()
        if not text:
            return
        cur = self.read()
        self.path.write_text(f"{cur}\n{text}" if cur else text)

    def count(self) -> int:
        return sum(1 for line in self.read().splitlines() if line.strip())
