"""Real compiler fixture for browser integration tests; isolated studio storage."""
import json
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from editor_service import editor_action
with tempfile.TemporaryDirectory() as temp:
    os.environ['MCP_DATA_DIR'] = temp
    parts = [{'type':'panel','label':'Üst kontrol paneli','w':120,'h':80,'edges':'eeee','holes':[{'x':20,'y':30,'d':4}],'slots':[{'x':70,'y':40,'w':8,'h':3}]}, {'type':'panel','label':'Destek','w':120,'h':35,'edges':'eeee'}]
    preview = editor_action('preview', {'primitives':parts,'parameters':{}}, {'project_id':'editor-fixture','name':'Editör denemesi'})
    print(json.dumps({'meta':{'primitives':parts,'parameters':{'material':'poplar_3mm'},'version':1,'project_id':'editor-fixture','name':'Editör denemesi','editable':True},'preview':preview}))
