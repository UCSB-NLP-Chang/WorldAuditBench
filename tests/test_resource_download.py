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
from environments.unreal_launch import without_hud

class RuntimeReleaseTests(unittest.TestCase):
    def test_hud_disabled_after_merging_console_commands(self):
        args = ['-vulkan', '-ExecCmds=t.MaxFPS 30,showhud',
                '-AuditorExplorationTask=U014', '-ExecCmds=r.SSR.Quality 3']
        result = without_hud(args)
        commands = [a for a in result if a.startswith('-ExecCmds=')]
        self.assertEqual(len(commands), 1)
        self.assertIn('t.MaxFPS 30', commands[0])
        self.assertIn('r.SSR.Quality 3', commands[0])
        self.assertTrue(commands[0].endswith('set HUD bShowHUD false,getall HUD bShowHUD'))
        self.assertIn('-AuditorExplorationTask=U014', result)
        self.assertEqual(without_hud(result), result)

    def test_every_unreal_task_uses_expanded_frozen_policy(self):
        profiles = json.loads((ROOT/'data/benchmark/profiles/ue-aws-profiles-20260918.json').read_text())
        policies = {release.digest(p): json.loads(p.read_text())
                    for p in (ROOT/'data/benchmark/policies').glob('*/policy.json')}
        for task in (ROOT/'data/benchmark/splits/unreal.txt').read_text().splitlines():
            profile = profiles['tasks'][task]
            checksum = profiles['policies'][profile['policy_version']]['sha256']
            policy = policies[checksum]
            self.assertTrue(policy['frozen'])
            spec = policy['tasks'][task]
            for field in ('bounds_min', 'bounds_max', 'spawn', 'yaw'):
                self.assertEqual(spec[field], profile['policy'][field], (task, field))
            area = (spec['bounds_max'][0]-spec['bounds_min'][0]) * (spec['bounds_max'][1]-spec['bounds_min'][1])
            old = (spec['old_bounds_max'][0]-spec['old_bounds_min'][0]) * (spec['old_bounds_max'][1]-spec['old_bounds_min'][1])
            self.assertAlmostEqual(area/old, 3, places=5, msg=task)

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

    def test_bundle_restores_shared_files_and_checks_every_variant(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'urban.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                first = tarfile.TarInfo('first/Linux/game')
                first.size, first.mode = 4, 0o755
                tar.addfile(first, io.BytesIO(b'game'))
                second = tarfile.TarInfo('second/Linux/game')
                second.type, second.linkname, second.mode = tarfile.LNKTYPE, first.name, 0o755
                tar.addfile(second)
            checksum = hashlib.sha256(b'game').hexdigest()
            package = {'id': 'urban', 'filename': archive.name, 'sha256': release.digest(archive),
                       'variants': [{'id': v, 'binary': v + '/Linux/game', 'binary_sha256': checksum}
                                    for v in ('first', 'second')]}
            release.restore(package, root/'installed', root/'cache', root)
            first = root/'installed/urban/first/Linux/game'
            second = root/'installed/urban/second/Linux/game'
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertTrue(second.stat().st_mode & 0o100)
            second.write_bytes(b'modified')
            self.assertEqual(first.read_bytes(), b'game')
            with self.assertRaisesRegex(ValueError, 'modified: second'):
                release.restore(package, root/'installed', root/'cache', root)

    def test_rejects_hard_links_outside_preceding_archive_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root/'test.tar.gz', 'link', tarfile.LNKTYPE)
            with self.assertRaisesRegex(ValueError, 'Unsafe archive hard link'):
                release.extract(root/'test.tar.gz', root/'output')

    def test_release_matches_all_experiment_builds(self):
        manifest=json.loads((ROOT/'data/resources/releases.json').read_text())
        profiles=json.loads((ROOT/'data/benchmark/profiles/ue-aws-profiles-20260918.json').read_text())['tasks']
        profiles.update(json.loads((ROOT/'data/benchmark/profiles/ue-urban-ipc-profiles-20260920.json').read_text())['tasks'])
        assigned=set((ROOT/'data/benchmark/splits/unreal.txt').read_text().splitlines())
        seen=[]
        for package in manifest['packages']:
            if package['group']!='unreal-runtime':continue
            for build in release.builds(package):
                for task in build['tasks']:
                    self.assertEqual(profiles[task]['build_sha256'],build['binary_sha256'],task)
                    seen.append(task)
        self.assertEqual(set(seen),assigned)
        self.assertEqual(len(seen),126)

if __name__=='__main__':unittest.main()
