import unittest
from sessions import Sessions

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now=0;self.q=Sessions(limit=2,clock=lambda:self.now)
    def test_fifo_and_independent_credentials(self):
        a=self.q.create({'id':'A'});b=self.q.create({'id':'B'})
        self.assertEqual(self.q.public(b)['position'],2)
        with self.assertRaises(PermissionError):self.q.owner(a['id'],b['token'])
        a['state']='ready';a['started']=0
        self.assertEqual(self.q.public(b)['position'],1)
        self.assertEqual(self.q.public(a)['seconds_left'],600)
    def test_bounded_queue(self):
        self.q.create({'id':'A'});self.q.create({'id':'B'})
        with self.assertRaises(ValueError):self.q.create({'id':'C'})
    def test_idle_and_absolute_deadlines(self):
        a=self.q.create({'id':'A'});a['started']=0
        self.now=44;self.assertEqual(self.q.expired(),[])
        self.now=46;self.assertEqual(self.q.expired(),[a])
        a['heartbeat']=601;self.now=601;self.assertEqual(self.q.expired(),[a])
    def test_missing_session_is_expired(self):
        with self.assertRaises(PermissionError):self.q.owner('missing','token')
if __name__=='__main__':unittest.main()
