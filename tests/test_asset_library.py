import os,tempfile,unittest
from unittest.mock import patch
from asset_library import upload_asset,list_assets,place_asset

ASSET='<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" viewBox="0 0 20 10"><path d="M0 10 L10 0 L20 10"/></svg>'
class AssetLibraryTests(unittest.TestCase):
 def test_upload_list_place_is_scoped_and_vector(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'MCP_DATA_DIR':folder,'SUPABASE_URL':'','SUPABASE_SERVICE_ROLE_KEY':''}):
   made=upload_asset('org-a','My Logo','logo',ASSET);token=made['library_token'];asset=made['asset']
   self.assertEqual(list_assets('org-a',token)[0]['name'],'My Logo')
   self.assertEqual(list_assets('org-b',token),[])
   obj=place_asset('org-a',token,asset['id'],'PART_A',width=30)
   self.assertEqual(obj['operation'],'ENGRAVE');self.assertEqual(obj['parent_part_id'],'PART_A');self.assertTrue(obj['d'].startswith('M '))
   with self.assertRaises(ValueError):place_asset('org-a','bad',asset['id'],'PART_A')
