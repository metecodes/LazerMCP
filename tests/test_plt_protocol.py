import unittest
from unittest.mock import patch
from starlette.testclient import TestClient
from mcp.server.transport_security import TransportSecuritySettings

class PLTProtocolTests(unittest.TestCase):
 def test_mcp_schema_and_calls(self):
  import server
  app=server.mcp.streamable_http_app(streamable_http_path='/mcp',stateless_http=True,json_response=True,transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
  headers={'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'}
  def save(raw,*a,**kw):return {'success':True,'file_id':'protocol-test.svg',**a[3]}
  with patch('plans.gate_job',return_value={'ok':True}),patch('payas_cad._save_build',side_effect=save),TestClient(app) as client:
   init=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'plt-test','version':'1'}}})
   self.assertEqual(init.status_code,200)
   self.assertIn('result',init.json())
   schema=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list'}).json()
   design=next(t for t in schema['result']['tools'] if t['name']=='create_design')
   self.assertTrue({'create_text','create_vector_graphic','create_image_reference','inspect_design','compute_safe_design_area','compose_design','compose_source_sheet','validate_composition','repair_composition','export_composed_dxf'}.issubset({t['name'] for t in schema['result']['tools']}))
   response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':9,'method':'tools/call','params':{'name':'create_from_reference','arguments':{}}})
   import json
   missing=json.loads(response.json()['result']['content'][0]['text']);self.assertEqual(missing['error_code'],'REFERENCE_IMAGE_MISSING');self.assertTrue(missing['retryable'])
   self.assertTrue(any(t['name']=='search_joint_templates' for t in schema['result']['tools']))
   self.assertIn('plt',design['inputSchema']['properties']);self.assertIn('plt_base64',design['inputSchema']['properties'])
   for i,source,expected in [(3,'IN;SP1;PU0,0;PD400,0,400,400,0,400,0,0;PU;',True),(4,'PU0,0;PD400,0;PE;',False)]:
    response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'name':'create_design','arguments':{'plt':source}}})
    self.assertEqual(response.status_code,200)
    result=response.json()['result'];self.assertFalse(result.get('isError',False))
    data=json.loads(result['content'][0]['text'])
    self.assertEqual(data['success'],expected)
    if expected:self.assertEqual(data['plt_import']['source_bounds_mm'],[0,0,10,10]);self.assertEqual(data['final_status'],'PROTOTYPE READY')
    else:self.assertTrue(any('PE' in n for n in data['look_again']))
   response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'create_design','arguments':{'svg':'<svg width="10mm" height="10mm" viewBox="0 0 10 10"><path d="M0 0 L2.7 0 L2.7 9 L0 9 Z"/></svg>','parameters':{'svg_default_operation':'CUT','thickness':2.7}}}})
   self.assertEqual(response.status_code,200)
   data=json.loads(response.json()['result']['content'][0]['text'])
   self.assertTrue(data['success'])
   self.assertTrue(data['preserve_source_geometry'])
   self.assertEqual(data['parameters']['thickness'],2.7)
   response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':6,'method':'tools/call','params':{'name':'search_joint_templates','arguments':{'query':'UniversalBox','limit':1}}})
   self.assertEqual(response.status_code,200)
   data=json.loads(response.json()['result']['content'][0]['text'])
   self.assertEqual(data['matches'][0]['name'],'UniversalBox')
   self.assertGreater(data['indexed_templates'],100)
   response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':7,'method':'tools/call','params':{'name':'create_design','arguments':{'preset':'engraving_layout','parameters':{'width_mm':100,'height_mm':100,'items':[{'kind':'text','value':'ÖNCE GÜVENLİK','x':50,'y':50,'width':80}]}}}})
   self.assertEqual(response.status_code,200)
   data=json.loads(response.json()['result']['content'][0]['text'])
   self.assertTrue(data['success'])
   self.assertEqual(data['method'],'positioned_vector_layout')
   from tests.test_image_engraving import sample
   response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':8,'method':'tools/call','params':{'name':'create_from_reference','arguments':{'image_base64':sample('white','black'),'format':'both','primitives':[{'type':'panel','w':100,'h':100,'edges':'eeee','label':'top-panel'}],'reference_markings':[{'target_part':'top-panel','x':50,'y':70,'width':25}]}}})
   self.assertEqual(response.status_code,200)
   self.assertFalse(response.json()['result'].get('isError',False))
   data=json.loads(response.json()['result']['content'][0]['text'])
   self.assertTrue(data['success'])

if __name__=='__main__':unittest.main()
