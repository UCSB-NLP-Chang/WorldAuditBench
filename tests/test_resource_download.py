"""Runtime release integrity and extraction behavior without a GPU or network."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('download_resources', ROOT / 'scripts/download_resources.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

class RuntimeReleaseTests(unittest.TestCase):
    def archive(self, path, name='Linux/game', kind=tarfile.REGTYPE):
        with tarfile.open(path, 'w:gz') as tar:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.mode = 0o755
            if kind == tarfile.REGTYPE:
                member.size = 4
                tar.addfile(member, io.BytesIO(b'game'))
            else:
                member.linkname = '/etc/passwd'
                tar.addfile(member)

    def test_restore_verifies_binary_and_reuses_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'test.tar.gz'
            self.archive(archive)
            import hashlib
            package = {'id': 'test', 'filename': archive.name, 'sha256': release.digest(archive),
                       'binary': 'Linux/game', 'binary_sha256': hashlib.sha256(b'game').hexdigest()}
            release.restore(package, root / 'installed', root / 'cache', root)
            binary = root / 'installed/test/Linux/game'
            self.assertEqual(binary.read_bytes(), b'game')
            self.assertTrue(binary.stat().st_mode & 0o100)
            release.restore(package, root / 'installed', root / 'cache', root)
            binary.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'modified'):
                release.restore(package, root / 'installed', root / 'cache', root)

    def test_rejects_wrong_archive_hash_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root / 'test.tar.gz')
            with self.assertRaisesRegex(ValueError, 'mismatched'):
                release.restore({'id':'test','filename':'test.tar.gz','sha256':'wrong'}, root/'installed',root/'cache',root)
            self.assertFalse((root / 'installed/test').exists())

    def test_rejects_parent_paths_and_symbolic_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, kind in [('../escape',tarfile.REGTYPE),('link',tarfile.SYMTYPE)]:
                with self.subTest(name=name):
                    self.archive(root/'test.tar.gz', name, kind)
                    with self.assertRaises(ValueError):
                        release.extract(root/'test.tar.gz',root/'output')
            self.assertFalse((root/'escape').exists())

    def test_release_matches_all_experiment_builds(self):
        manifest=json.loads((ROOT/'resources/releases.json').read_text())
        profiles=json.loads((ROOT/'benchmark/profiles/ue-aws-profiles-20260918.json').read_text())['tasks']
        profiles.update(json.loads((ROOT/'benchmark/profiles/ue-urban-ipc-profiles-20260920.json').read_text())['tasks'])
        assigned=set((ROOT/'benchmark/splits/unreal.txt').read_text().splitlines())
        seen=[]
        for package in manifest['packages']:
            if package['group']!='unreal-runtime':continue
            for task in package['tasks']:
                self.assertEqual(profiles[task]['build_sha256'],package['binary_sha256'],task)
                seen.append(task)
        self.assertEqual(set(seen),assigned)
        self.assertEqual(len(seen),126)

if __name__=='__main__':unittest.main()
