import unittest
from unittest.mock import patch
import numpy as np
from image_trace import _marching_segments, _CASES

class CadPerformanceTests(unittest.TestCase):
    def test_fast_contours_exactly_match_old_algorithm(self):
        rng=np.random.default_rng(5)
        for mask in [np.zeros((8,8),dtype=np.uint8),np.ones((8,8),dtype=np.uint8),rng.integers(0,2,(20,25),dtype=np.uint8)]:
            padded=np.pad(mask,1,mode='constant');expected=[]
            for y in range(padded.shape[0]-1):
                for x in range(padded.shape[1]-1):
                    code=int(padded[y,x])*8+int(padded[y,x+1])*4+int(padded[y+1,x+1])*2+int(padded[y+1,x])
                    for a,b in _CASES[code]:
                        expected.append(((x+a[0]-1.,y+a[1]-1.),(x+b[0]-1.,y+b[1]-1.)))
            self.assertEqual(_marching_segments(mask),expected)

    def test_hosted_save_never_waits_for_cleanup(self):
        from boxes_adapter import save_generated_svg
        import persist.cleanup  # Import dependency bindings before mocking backend selection.
        for hosted in (True,False):
            with patch('persist.env.uses_supabase_app_db',return_value=hosted),patch('persist.cleanup.cleanup_expired') as cleanup,patch('boxes_adapter._write_svg',side_effect=RuntimeError('stop before persistence')):
                with self.assertRaises(RuntimeError):save_generated_svg(b'<svg/>')
                self.assertEqual(cleanup.call_count,0 if hosted else 1)

    def test_packaged_index_skips_source_scan(self):
        from joint_library import library_index
        library_index.cache_clear()
        with patch('joint_library.scan_sources',side_effect=RuntimeError('runtime scanning is slow')):
            self.assertGreater(len(library_index()['templates']),100)
