#!/usr/bin/env python3
"""Install native-client dependencies; shared agent tools live in this repository."""
from pathlib import Path
import subprocess
import venv

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "out/native-agents"


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    runtime = BASE / "venv"
    python = runtime / "bin/python"
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(runtime)
    subprocess.run([str(python), "-m", "pip", "install", "-r",
                    str(Path(__file__).with_name("requirements.txt"))], check=True)
    frozen = subprocess.check_output([str(python), "-m", "pip", "freeze"], text=True)
    (BASE / "installed-requirements.txt").write_text(frozen)
    print("Ready:", python)


if __name__ == "__main__":
    main()
