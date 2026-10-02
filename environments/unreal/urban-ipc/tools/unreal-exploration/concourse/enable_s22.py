"""Allow the reviewed S22 candidate in the Review-only service catalog validator."""
from pathlib import Path
import argparse
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--server', type=Path, required=True)
parser.add_argument('--backup', type=Path, required=True)
a = parser.parse_args()
old = a.server.read_text()
needle = r'S(?:0[1-9]|1[0-9]|2[01])'
replacement = r'S(?:0[1-9]|1[0-9]|2[012])'
if replacement not in old:
    assert old.count(needle) == 1
    assert not a.backup.exists()
    shutil.copy2(a.server, a.backup)
    a.server.write_text(old.replace(needle, replacement))
print('Review accepts S22; all other task ID validation remains unchanged')
