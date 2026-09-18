"""Read-only checks of the corrected production artifact and MCP preview tool."""
from persist.migrate_studio import load_env
load_env()
from pathlib import Path
import json,os,urllib.request
r=json.loads(Path('scratch/house-result.json').read_text())
base='https://mcp.metehanavci.com'
auth={'Authorization':'Bearer '+os.environ['MCP_AUTH_TOKEN']} if os.environ.get('MCP_AUTH_TOKEN') else {}
with urllib.request.urlopen(urllib.request.Request(base+'/api/editor/'+r['file_id'],headers=auth),timeout=45) as response:
 d=json.loads(response.read())
 assert len(d['primitives'])==7 and d['assembled_preview_svg'] and d['expires_at']
 assert 'no-store' in response.headers.get('Cache-Control','')
print('PASS: production bundled SVG, seven parts, upright view, expiry and cache policy')
with urllib.request.urlopen(urllib.request.Request(r['assembled_preview_url'],headers=auth),timeout=45) as response:
 assert b'assembled-view' in response.read()
print('PASS: production upright editor link opens')
headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
if os.environ.get('MCP_AUTH_TOKEN'):headers['Authorization']='Bearer '+os.environ['MCP_AUTH_TOKEN']
def call(payload):
 req=urllib.request.Request(base+'/mcp',data=json.dumps(payload).encode(),headers=headers)
 with urllib.request.urlopen(req,timeout=45) as response:
  if response.headers.get('Mcp-Session-Id'):headers['Mcp-Session-Id']=response.headers['Mcp-Session-Id']
  raw=response.read().decode()
 if raw.startswith('event:') or raw.startswith('data:'):
  raw=next(line[5:].strip() for line in raw.splitlines() if line.startswith('data:'))
 return json.loads(raw)
a=call({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'house-verification','version':'1'}}})
assert 'result' in a
headers['MCP-Protocol-Version']='2025-06-18'
b=call({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'render_preview','arguments':{'file_id':r['file_id'],'view':'assembled'}}})
assert 'result' in b and not b['result'].get('isError'), 'MCP tool failed'
text=' '.join(c.get('text','') for c in b['result'].get('content',[]))
assert 'assembled' in text and r['file_id'] in text
print('PASS: live MCP initialize and tools/call render_preview(view=assembled)')
