import unittest
from joint_library import library_index, search_joint_templates, plan_references
from job_planner import plan_laser_job

class JointLibraryTests(unittest.TestCase):
    def test_scans_actual_installed_sources(self):
        index = library_index()
        self.assertGreater(len(index['templates']), 100)
        self.assertEqual(index['failures'], [])
        for row in index['templates']:
            self.assertEqual(len(row['source_sha256']), 64)
            self.assertNotIn('Misc', row['edge_sequences_in_source'])

    def test_exact_generator_and_schema(self):
        result = search_joint_templates('UniversalBox', 1)
        row = result['matches'][0]
        self.assertEqual(row['name'], 'UniversalBox')
        self.assertIn('thickness', {p['name'] for p in row['parameters']})
        self.assertIn('NOT VERIFIED', row['verification'])

    def test_turkish_pen_holder_retrieval(self):
        result = plan_references('geçmeli kalemlik')
        self.assertEqual(result['matches'][0]['name'], 'PenHolderBox')
        self.assertNotIn('parameters', result['matches'][0])

    def test_unknown_query_does_not_make_up_template(self):
        self.assertEqual(search_joint_templates('xyznonexistent')['matches'], [])

    def test_planner_reuses_explicit_template(self):
        plan = plan_laser_job('Boxes.py UniversalBox 130x90 mm')
        self.assertEqual(plan['next_tool'], 'generate_svg')
        self.assertEqual(plan['next_arguments']['generator'], 'UniversalBox')
        self.assertEqual(plan['next_arguments']['parameters'], {'x': 130, 'y': 90})

    def test_house_photo_keeps_custom_structure(self):
        plan = plan_laser_job('ev kalemlik', has_photo=True, what_you_see='ön yüz ev şeklinde')
        self.assertEqual(plan['next_tool'], 'create_design')
        self.assertIn('joint_library', plan)
        self.assertTrue(plan['next_arguments']['primitives'][0].get('placement'))
