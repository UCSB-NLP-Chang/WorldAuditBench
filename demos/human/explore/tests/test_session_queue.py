import unittest
from unittest.mock import patch
from bf.common import Problem, uid
import test_browser_runtime as browser_tests


class SessionQueueTests(unittest.TestCase):
    setUp = browser_tests.BrowserRuntimeTests.setUp
    tearDown = browser_tests.BrowserRuntimeTests.tearDown
    start = browser_tests.BrowserRuntimeTests.start

    def unreal(self):
        self.runtime.c['tasks'][self.tid]['kind'] = 'unreal'
        self.runtime.c['gpu_guard'] = False
        self.runtime.c['legacy_player_ports'] = []

    def test_fifo_and_idempotent_start(self):
        self.unreal()
        a, one = self.start(self.users[0]); b, two = self.start(self.users[1])
        self.assertEqual((one['queue_position'], two['queue_position']), (1, 2))
        self.assertEqual(self.runtime.start(self.users[0], a['id'])['id'], one['id'])
        with patch.object(self.runtime, 'call', return_value={'ready': True, 'stopped': True}) as call:
            self.runtime.tick()
            self.assertEqual(self.runtime.current['id'], one['id'])
            self.assertEqual(self.runtime.status(self.users[1], b['id'])['queue_position'], 1)
            self.runtime.stop(self.users[0], a['id']); self.runtime.tick()
            self.assertEqual(self.runtime.current['id'], two['id'])
            self.assertEqual([c.args[0] for c in call.call_args_list], ['start', 'stop', 'start'])

    def test_one_session_across_browser_and_unreal(self):
        a, one = self.start(self.users[0])
        tid = uid(); self.store.register_task({'id':tid, 'title':'Other','query':'Explore','controls':'WASD'})
        self.store.grant_task('one', tid, 'explorer')
        other = self.store.start_attempt(self.users[0], tid)
        with self.assertRaises(Problem): self.runtime.start(self.users[0], other['id'])
        self.runtime.stop(self.users[0], a['id'])
        self.assertEqual(self.runtime.start(self.users[0], other['id'])['status'], 'queued')
        with self.assertRaises(Problem): self.runtime.start(self.users[0], a['id'])

    def test_cancel_queue_does_not_stop_other_user(self):
        self.unreal(); a, one = self.start(self.users[0]); b, two = self.start(self.users[1])
        with patch.object(self.runtime, 'call', return_value={'ready': True}) as call:
            self.runtime.tick(); self.runtime.stop(self.users[1], b['id'])
            self.assertEqual(self.runtime.current['id'], one['id'])
            self.assertFalse(self.runtime.queue); self.assertEqual(call.call_count, 1)

    def test_teardown_failure_quarantines_slot(self):
        self.unreal(); a, one = self.start(self.users[0]); b, two = self.start(self.users[1])
        with patch.object(self.runtime, 'call', return_value={}):
            self.runtime.tick()
            with self.assertRaises(Problem): self.runtime.stop(self.users[0], a['id'])
            with self.assertRaises(Problem): self.runtime.tick()
            self.assertEqual(self.runtime.current['id'], one['id'])
            self.assertEqual(len(self.runtime.queue), 1)
        with patch.object(self.runtime, 'call', return_value={'stopped':True}):
            self.runtime.tick(); self.assertEqual(self.runtime.current['id'], two['id'])

    def test_queue_expiry_logout_and_submit(self):
        self.unreal(); a, one = self.start(self.users[0]); self.runtime.queue[0]['heartbeat'] = 0
        with patch.object(self.runtime, 'call') as call:
            self.runtime.tick(); call.assert_not_called()
        self.assertFalse(self.runtime.queue)
        self.start(self.users[0]); self.runtime.stop_user(self.users[0]); self.assertFalse(self.runtime.queue)
        self.start(self.users[0]); self.runtime.finish_attempt(self.users[0], a['id']); self.assertFalse(self.runtime.queue)

    def test_audit_preemption_preserves_browser_and_queue(self):
        browser_attempt, browser = self.start(self.users[0])
        self.unreal(); a, one = self.start(self.users[1])
        with patch.object(self.runtime, 'call', return_value={'ready':True,'stopped':True}):
            self.runtime.tick()
            with patch.object(self.runtime, 'legacy_busy', return_value=True): self.runtime.tick()
        self.assertIsNone(self.runtime.current)
        self.assertIn(browser['id'], self.runtime.browsers)

    def test_queue_rechecks_access_before_launch(self):
        self.unreal(); self.start(self.users[0])
        self.store.db.execute('DELETE FROM task_access WHERE user_id=?', (self.users[0]['id'],))
        with patch.object(self.runtime, 'call') as call:
            self.runtime.tick(); call.assert_not_called()
        self.assertFalse(self.runtime.queue)

    def test_busy_gpu_keeps_fifo_without_launch(self):
        self.unreal(); self.runtime.c['gpu_guard'] = True; self.start(self.users[0])
        with patch('bf.runtime.subprocess.run') as gpu, patch.object(self.runtime, 'call') as call:
            gpu.return_value.stdout = '1000, 90'
            self.runtime.tick(); call.assert_not_called()
        self.assertEqual(len(self.runtime.queue), 1)
