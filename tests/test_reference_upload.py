import base64,os,tempfile,unittest
from email.message import Message
from unittest.mock import patch
from keys import current_auth
from reference_upload import start_reference_upload,upload_reference_chunk,read_reference_upload,discard_reference_upload,fetch_public_image,MAX_CHUNK_CHARS

class ReferenceUploadTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'MCP_DATA_DIR':self.tmp.name,'SUPABASE_URL':'','SUPABASE_SERVICE_ROLE_KEY':''});self.env.start();self.auth=current_auth.set({'id':'owner-a'})
 def tearDown(self):current_auth.reset(self.auth);self.env.stop();self.tmp.cleanup()
 def test_chunks_round_trip_and_discard(self):
  encoded=base64.b64encode(b'not-a-real-image-but-valid-transport').decode();parts=[encoded[:20],encoded[20:]];started=start_reference_upload(2)
  self.assertFalse(upload_reference_chunk(started['reference_upload_id'],0,parts[0])['complete'])
  self.assertTrue(upload_reference_chunk(started['reference_upload_id'],1,parts[1])['complete'])
  self.assertEqual(read_reference_upload(started['reference_upload_id']),encoded)
  self.assertTrue(discard_reference_upload(started['reference_upload_id'])['success'])
  with self.assertRaises(ValueError):read_reference_upload(started['reference_upload_id'])
 def test_incomplete_owner_and_size_are_rejected(self):
  upload_id=start_reference_upload(2)['reference_upload_id'];upload_reference_chunk(upload_id,0,'AAAA')
  with self.assertRaisesRegex(ValueError,'incomplete'):read_reference_upload(upload_id)
  token=current_auth.set({'id':'owner-b'})
  try:
   with self.assertRaisesRegex(ValueError,'another'):read_reference_upload(upload_id)
  finally:current_auth.reset(token)
  with self.assertRaises(ValueError):upload_reference_chunk(upload_id,1,'A'*(MAX_CHUNK_CHARS+1))
 def test_public_image_url_is_bounded_and_encoded(self):
  class Response:
   def __init__(self):self.headers=Message();self.headers['Content-Type']='image/png';self.headers['Content-Length']='3'
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def geturl(self):return 'https://example.com/reference.png'
   def read(self,n):return b'png'
  with patch('socket.getaddrinfo',return_value=[(None,None,None,None,('93.184.216.34',443))]),patch('urllib.request.urlopen',return_value=Response()):
   self.assertEqual(base64.b64decode(fetch_public_image('https://example.com/reference.png')),b'png')
  with self.assertRaises(ValueError):fetch_public_image('http://127.0.0.1/private.png')
