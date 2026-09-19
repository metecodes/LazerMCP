import copy
import os
import tempfile
import unittest
from unittest.mock import patch
from editor_service import editor_action, connection_checks, validate_draft

class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'MCP_DATA_DIR': self.temp.name,
            'SUPABASE_URL': '', 'SUPABASE_SERVICE_ROLE_KEY': ''})
        self.env.start()
        self.context = {'project_id': 'editor-tests', 'name': 'Editör testi'}
        self.parts = [{'type': 'panel', 'label': 'Kapak', 'w': 120, 'h': 80, 'edges': 'eeee', 'holes': [{'x': 20, 'y': 30, 'd': 4}], 'slots': [{'x': 60, 'y': 40, 'w': 8, 'h': 3}]}]
    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()
    def test_preview_compiles_holes_and_keeps_history_unchanged(self):
        from projects import project_history
        r = editor_action('preview', {'primitives': self.parts}, self.context)
        self.assertIn('data-panel="Kapak"', r['svg'])
        self.assertEqual(r['primitives'][0]['holes'][0]['x'], 20)
        self.assertEqual(r['primitives'][0]['slots'][0]['h'], 3)
        self.assertNotEqual(r['review']['final_status'], 'PRODUCTION READY')
        self.assertIsNone(project_history('editor-tests'))
    def test_bad_connection_blocks_review_and_save(self):
        parts = self.parts + [{'type':'panel','label':'Destek','w':40,'h':80,'edges':'Feee'}]
        params = {'editor_connections':[{'a':'Kapak','b':'Destek','edge_a':0,'edge_b':0}]}
        self.assertEqual(connection_checks(parts, params)[0]['status'], 'FAIL')
        result = editor_action('preview', {'primitives':parts,'parameters':params}, self.context)
        self.assertEqual(result['review']['final_status'], 'BLOCKED')
        with self.assertRaises(ValueError):
            editor_action('save', {'primitives':parts,'parameters':params}, self.context)
    def test_correct_pair_and_self_connection(self):
        parts = [{'type':'panel','label':'A','w':80,'h':40,'edges':'feee'}, {'type':'panel','label':'B','w':80,'h':40,'edges':'Feee'}]
        params = {'editor_connections':[{'a':'A','b':'B','edge_a':0,'edge_b':0}]}
        self.assertEqual(connection_checks(parts,params)[0]['status'],'PASS')
        params['editor_connections'][0]['b']='A'
        self.assertEqual(connection_checks(parts,params)[0]['status'],'FAIL')
    def test_history_returns_old_geometry(self):
        from projects import save_version
        save_version(self.context, {'primitives':self.parts,'file_id':'old.svg'})
        newer = copy.deepcopy(self.parts)
        newer[0]['w']=150
        save_version(self.context, {'primitives':newer,'file_id':'new.svg'})
        rows=editor_action('history',{},self.context)['versions']
        self.assertEqual([v['primitives'][0]['w'] for v in rows],[120,150])
    def test_draft_cannot_replace_project_identity(self):
        parts, params=validate_draft({'primitives':self.parts,'parameters':{'project_id':'other','_machine':{'bed_w':9}}},self.context)
        self.assertEqual(params['project_id'],'editor-tests')
        self.assertNotIn('_machine',params)
        self.assertEqual(params['scale'], 1)
        self.assertEqual(params['physical_assembly'], 'not_verified')
        parts[0]['w']=9
        self.assertEqual(self.parts[0]['w'],120)
    def test_duplicate_names_rejected(self):
        with self.assertRaises(ValueError):
            validate_draft({'primitives':self.parts*2},self.context)

    def test_saved_millimetres_are_not_scaled_twice(self):
        result = editor_action('preview', {'primitives':self.parts, 'parameters':{'scale':2}}, self.context)
        self.assertEqual(result['primitives'][0]['w'],120)

class EditorRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_editor_get_reaches_file_authorization_without_bearer_header(self):
        from server import BearerGate
        from unittest.mock import AsyncMock
        app = AsyncMock()
        scope = {'type':'http', 'method':'GET', 'path':'/api/editor/design.svg', 'headers':[]}
        with patch('keys.auth_required', return_value=True):
            await BearerGate(app)(scope, AsyncMock(), AsyncMock())
        app.assert_awaited_once()

    async def test_editor_returns_svg_without_local_file(self):
        from server import api_editor
        from starlette.requests import Request
        import json
        request = Request({'type':'http', 'method':'GET', 'path':'/api/editor/design.svg',
                           'headers':[], 'path_params':{'filename':'design.svg'}})
        decision = {'allow': True, 'artifact': {'source_file_id': 'design.svg', 'storage_path': 'objects/design.svg', 'expires_at': '2099-01-01T00:00:00Z'}}
        with patch('server._authorize_output_file', return_value=(decision, {'id': 'owner'})), \
             patch('workshop.editor_context', return_value={'success': True, 'primitives': []}), \
             patch('persist.storage.StorageService.get', return_value=b'<svg/>'), \
             patch('server.boxespy._safe_output_file', side_effect=AssertionError('temporary disk used')):
            response = await api_editor(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)['svg'], '<svg/>')
        self.assertIn('no-store', response.headers['cache-control'])

    async def test_editor_classifies_signin_expiry_and_remote_failure(self):
        from server import api_editor
        from starlette.requests import Request
        import json
        request = Request({'type':'http', 'method':'GET', 'path':'/api/editor/design.svg',
                           'headers':[], 'path_params':{'filename':'design.svg'}})
        for decision, principal, expected in (({'allow':False,'reason':'forbidden'}, None, 401),
                    ({'allow':False,'reason':'expired'}, {'id':'owner'}, 410)):
            with patch('server._authorize_output_file', return_value=(decision, principal)):
                response = await api_editor(request)
            self.assertEqual(response.status_code, expected)
            if expected == 401:
                self.assertIn('/account?next=', json.loads(response.body)['signin_url'])
        with patch('server._authorize_output_file', side_effect=OSError('temporary remote failure')):
            response = await api_editor(request)
        self.assertEqual(response.status_code, 503)

    async def test_denied_file_cannot_read_history_or_compile(self):
        from server import api_editor_action
        from starlette.requests import Request
        request = Request({'type':'http', 'method':'POST', 'path':'/api/editor/private.svg/history',
                           'headers':[], 'path_params':{'filename':'private.svg','action':'history'}})
        with patch('server._authorize_output_file', return_value=({'allow':False}, None)), patch('editor_service.editor_action') as action:
            response = await api_editor_action(request)
        self.assertEqual(response.status_code, 404)
        action.assert_not_called()

    async def test_editor_javascript_is_registered(self):
        from server import BRAND_FILES
        self.assertEqual(BRAND_FILES['/editor.js'][0], 'editor.js')

    async def test_editor_zoom_keeps_pointer_focus_and_supports_wheel(self):
        from pathlib import Path
        script=Path(__file__).parents[1].joinpath('web','editor.js').read_text(encoding='utf-8')
        self.assertIn("addEventListener('wheel'",script)
        self.assertIn('matrixTransform(matrix.inverse())',script)
        self.assertNotIn("if(state.assembledMode||state.tool==='place'",script)

if __name__=='__main__': unittest.main()
