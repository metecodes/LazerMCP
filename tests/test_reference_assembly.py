import unittest
from unittest.mock import patch
from tests.test_image_engraving import sample
from reference_assembly import compose_reference
from payas_cad import create_from_reference
from image_trace import _binary_mask,_decode_image
from xml.etree import ElementTree as ET

class ReferenceAssemblyTests(unittest.TestCase):
    def test_same_sheet_retains_cut_and_yellow_image(self):
        captured={}
        def save(svg,*args,**kwargs):
            captured.update(svg=svg,dxf=kwargs['dxf_bytes'])
            return {'success':True,**args[3]}
        recipe=[{'type':'panel','w':100,'h':100,'edges':'fFeF','label':'top-panel','holes':[{'x':15,'y':15,'d':5}]}]
        with patch('plans.gate_job',return_value={'ok':True}),patch('payas_cad._save_build',side_effect=save):
            result=create_from_reference(image_base64=sample('white','black'),primitives=recipe,reference_markings=[{'target_part':'top-panel','x':50,'y':70,'width':25}],format='both')
        self.assertTrue(result['success'])
        self.assertNotIn('markings',recipe[0])
        paths=[el for el in ET.fromstring(captured['svg']).iter() if el.tag.endswith('path')]
        self.assertTrue(any(p.get('data-operation')=='CUT' for p in paths))
        self.assertTrue(any(p.get('data-operation')=='ENGRAVE' and p.get('stroke')=='#FFFF00' for p in paths))
        self.assertIn(b'ENGRAVE',captured['dxf']);self.assertIn(b'CUT',captured['dxf'])

    def test_unknown_destination_is_reported(self):
        result=create_from_reference(image_base64=sample('white','black'),primitives=[{'type':'panel','w':100,'h':100,'label':'top'}],reference_markings=[{'target_part':'absent','x':50,'y':50,'width':25}])
        self.assertFalse(result['success'])
        self.assertEqual(result['error_code'],'REFERENCE_ASSEMBLY_INVALID')

    def test_box_face_target_is_exact(self):
        recipe=[{'type':'box','label':'body','x':100,'y':100,'h':100}]
        parts,_=compose_reference(recipe,[{'target_part':'body.front','x':50,'y':50,'width':30}],sample('white','black'),None,{},'both')
        self.assertEqual(len(parts[0]['walls']['front']['markings']),1)

    def test_export_error_is_not_success(self):
        with patch('plans.gate_job',return_value={'ok':True}),patch('payas_cad._save_build',side_effect=OSError('storage unavailable')),self.assertLogs('payas_cad',level='ERROR'):
            result=create_from_reference(image_base64=sample('white','black'),style='etch')
        self.assertFalse(result['success'])
        self.assertEqual(result['error_code'],'REFERENCE_EXPORT_FAILED')

    def test_flat_reference_preserves_operation_settings(self):
        captured={}
        def save(svg,*args,**kwargs):
            captured.update(extra=args[3])
            return {'success':True,**args[3]}
        settings={'ENGRAVE':{'speed_scale':0.5,'power_scale':0.2}}
        with patch('plans.gate_job',return_value={'ok':True}),patch('payas_cad._save_build',side_effect=save):
            result=create_from_reference(image_base64=sample('white','black'),style='etch',parameters={'operation_settings':settings})
        self.assertTrue(result['success'])
        self.assertEqual(captured['extra']['parameters']['operation_settings'],settings)

    def test_equal_mask_scores_do_not_compare_arrays(self):
        with patch('image_trace._score_mask',return_value=0):
            _binary_mask(_decode_image(image_base64=sample('white','black')),None,0)
