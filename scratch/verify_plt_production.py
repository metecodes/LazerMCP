"""Isolated production PLT fixture verification; all test records removed."""
from persist.migrate_studio import load_env
load_env()
import json,uuid,hashlib,urllib.request,time
from pathlib import Path
from payas_cad import create_design
from persist.artifacts import ArtifactRepository
from persist.storage import StorageService
from persist.supabase_rest import rest
pid='plt-production-check-'+uuid.uuid4().hex;base='https://mcp.metehanavci.com';result={}
def retry(fn):
 for attempt in range(3):
  try:return fn()
  except OSError:
   if attempt==2:raise
   time.sleep(1)
try:
 with urllib.request.urlopen(base+'/editor.js',timeout=45) as response:remote=response.read()
 assert hashlib.sha256(remote).digest()==hashlib.sha256(Path('web/editor.js').read_bytes()).digest()
 result=create_design(plt='IN;SP1;PU0,0;PD400,0,400,800,0,800,0,0;PU200,400;CI40;PU;SP0;',parameters={'project_id':pid,'project':'Isolated PLT verification','format':'both'},public_base_url=base)
 assert result.get('artifact_persistence')=='ARTIFACT_PERSISTENCE_SUCCESS'
 assert result['plt_import']['source_bounds_mm']==[0,0,10,20]
 assert result['final_status']=='PROTOTYPE READY'
 assert result['dxf_id']
 with urllib.request.urlopen(base+'/api/editor/'+result['file_id'],timeout=45) as response:data=json.loads(response.read())
 assert data['svg'] and data['expires_at'] and data['editable']==False
 from xml.etree import ElementTree as ET
 path=ET.fromstring(data['svg']).find('.//{http://www.w3.org/2000/svg}path')
 from svgpathtools import parse_path
 outline=parse_path(path.get('d'))
 assert outline.bbox()==(2.,12.,2.,22.) and outline.start==complex(2,22)
 with urllib.request.urlopen(base+'/out/'+result['file_id'],timeout=45) as response:assert b'import-plt' in response.read()
 print('PASS: production PLT upload UI asset, imported vectors and orientation, SVG/DXF generation, Final Gate and 24h storage')
finally:
 for a in result.get('artifacts',[]):
  stored=retry(lambda:ArtifactRepository().get(a['id']))
  if stored:
   retry(lambda:StorageService().delete(stored['storage_path']))
   retry(lambda:ArtifactRepository().delete(a['id']))
 retry(lambda:rest('lasermcp_projects',method='DELETE',params={'id':'eq.'+pid}))
 print('Isolated PLT verification records removed')
