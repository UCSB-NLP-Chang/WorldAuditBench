#!/usr/bin/env python3
"""Download the pinned task table and shared ICL examples from Hugging Face."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.tasks import ensure_dataset, ensure_examples


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks-only', action='store_true', help='Skip shared demonstration images')
    args = parser.parse_args()
    print(ensure_dataset())
    if not args.tasks_only:
        print(ensure_examples())
