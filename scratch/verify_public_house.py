"""Verify production editor assets and bundled API using one isolated design."""
import hashlib
import json
from pathlib import Path
import uuid
import urllib.request
from persist.migrate_studio import load_env


def main():
    load_env()
    from payas_cad import create_design
    from persist.supabase_rest import rest
    from persist.artifacts import ArtifactRepository
    from persist.storage import StorageService
    base = 'https://mcp.metehanavci.com'
    pid = 'production-editor-check-' + uuid.uuid4().hex
    result = {}
    try:
        with urllib.request.urlopen(base+'/editor.js', timeout=30) as response:
            deployed = response.read()
        local = (Path(__file__).resolve().parents[1]/'web'/'editor.js').read_bytes()
        assert hashlib.sha256(deployed).digest() == hashlib.sha256(local).digest(), 'deployed editor asset differs'
        from house_holder import recipe
        result = create_design(primitives=recipe(),
            parameters={'project_id':pid,'project':'Isolated production verification'}, public_base_url=base)
        assert result.get('artifact_persistence') == 'ARTIFACT_PERSISTENCE_SUCCESS'
        filename = result['file_id']
        with urllib.request.urlopen(base+'/api/editor/'+filename, timeout=30) as response:
            data = json.loads(response.read())
            assert 'no-store' in response.headers.get('Cache-Control', '')
        assert data['editable'] and len(data['primitives']) == 7
        assert data['assembled_preview_svg'] and 'raised-star' in data['assembled_preview_svg']
        assert '<svg' in data['svg'] and data['expires_at']
        request = urllib.request.Request(base+'/out/'+filename, headers={'Accept':'text/html'})
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200 and b'editor.js' in response.read()
        print('PASS: exact production editor asset; public domain returns bundled SVG, seven holder parts, raised star upright preview, 24-hour expiry and editor page')
    finally:
        for artifact in result.get('artifacts', []):
            stored = ArtifactRepository().get(artifact['id'])
            if stored:
                StorageService().delete(stored['storage_path'])
                ArtifactRepository().delete(artifact['id'])
        rest('lasermcp_projects', method='DELETE', params={'id':'eq.'+pid})
        print('Isolated production verification records removed')


if __name__ == '__main__':
    main()
