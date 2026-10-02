import unittest
from fastapi.testclient import TestClient
import app
class ApiTests(unittest.TestCase):
    def test_unconfigured_space_is_honest_and_reveals_only_on_request(self):
        with TestClient(app.app) as c:
            r=c.get('/api/catalog');self.assertEqual(r.status_code,200)
            data=r.json();self.assertFalse(data['available']);self.assertEqual(len(data['cases']),5)
            self.assertEqual(len({x['family'] for x in data['cases']}),5)
            self.assertNotIn('answer',str(data));self.assertNotIn('floats',str(data))
            self.assertEqual(c.post('/api/session',json={'case_id':'H01'}).status_code,503)
            self.assertEqual(c.post('/api/session',json={'case_id':'INVALID'}).status_code,404)
            self.assertIn('floats',c.get('/api/answer/H01').json()['criteria'])
            self.assertEqual(c.get('/api/answer/INVALID').status_code,404)
            self.assertEqual(c.post('/api/session/invalid/heartbeat').status_code,401)
            self.assertEqual(c.get('/').status_code,200)
            self.assertEqual(c.get('/explore').status_code,200)
if __name__=='__main__':unittest.main()
