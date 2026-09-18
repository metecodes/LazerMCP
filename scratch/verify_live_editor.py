"""Exercise compiler -> Supabase -> editor API with isolated test records."""
import asyncio
import json
import uuid
from persist.migrate_studio import load_env


async def main():
    load_env()
    from keys import current_auth
    from persist.orgs import ensure_personal_org
    from persist.supabase_rest import rest, rows
    from persist.storage import StorageService
    from payas_cad import create_design
    from server import api_editor
    from starlette.requests import Request
    suffix = uuid.uuid4().hex
    uid, pid = 'editor-check-' + suffix, 'editor-check-' + suffix
    org = ensure_personal_org(uid, 'Temporary editor verification')
    token = current_auth.set({'id':uid, 'organization_id':org, 'role':'individual', 'plan':'free'})
    try:
        result = create_design(primitives=[{'type':'panel','label':'Panel','w':80,'h':40,'edges':'eeee'}],
            parameters={'project_id':pid,'project':'Temporary editor verification'},
            public_base_url='https://mcp.metehanavci.com')
        assert result.get('file_id'), 'compiler did not create a file'
        assert result.get('artifact_persistence') == 'ARTIFACT_PERSISTENCE_SUCCESS', 'artifact save failed'
        assert result.get('project_persistence') == 'PROJECT_PERSISTENCE_SUCCESS', 'project save failed'
        filename = result['file_id']
        request = Request({'type':'http','method':'GET','path':'/api/editor/'+filename,
            'headers':[],'path_params':{'filename':filename}})
        response = await api_editor(request)
        assert response.status_code == 200, f'editor API returned {response.status_code}'
        data = json.loads(response.body)
        assert '<svg' in data['svg'] and data['editable']
        assert data['primitives'][0]['w'] == 80
        assert data['expires_at']
        print('PASS: compiled design, project history, all generated attachments persisted, editor API returned SVG + editable parts + expiry')
    finally:
        current_auth.reset(token)
        for artifact in rows('lasermcp_artifacts', organization_id='eq.'+org):
            StorageService().delete(artifact['storage_path'])
        rest('lasermcp_organizations', method='DELETE', params={'id':'eq.'+org})
        rest('lasermcp_projects', method='DELETE', params={'id':'eq.'+pid})
        print('Isolated live editor verification records removed')


if __name__ == '__main__':
    asyncio.run(main())
