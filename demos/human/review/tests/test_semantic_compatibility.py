import json, pathlib, unittest
from taxonomy import TAXONOMY, classify
ROOT=pathlib.Path(__file__).resolve().parents[1]
class SemanticCompatibilityTests(unittest.TestCase):
 def test_exact_semantic_membership(self):
  tasks=json.loads((ROOT/'tasks.json').read_text())['tasks']
  groups={code:{t['id'] for t in tasks if (classify(t) or {}).get('code')==code} for code in ('S1','S2','S3')}
  self.assertEqual(groups, {'S1': {'S20'}, 'S2': {'A25', 'H13', 'U028', 'A18', 'A19', 'U046', 'S18', 'R12', 'MV17', 'I19', 'S19'}, 'S3': {'A20', 'A21', 'A22', 'A23', 'A24', 'MV18', 'MV19', 'MV20', 'MV21', 'MV22'}})
 def test_version_definitions_and_legacy_catalog_aliases(self):
  self.assertEqual(TAXONOMY['version'], 'user-2026-09-13-material')
  for sub in TAXONOMY['categories'][-1]['subcategories']:
   self.assertTrue(sub['definition']['zh']);self.assertTrue(sub['definition']['en'])
  for tid in ['S18', 'H13', 'U028', 'A18', 'A19', 'R12', 'MV17', 'S17', 'S19', 'U039']:
   self.assertEqual(classify({'id':tid,'subcategory':'semantic.layout'})['code'],'S2')
