"""Live smoke test with isolated records; removes only its own test data."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from persist.migrate_studio import load_env


def main():
    load_env()
    from persist.supabase_rest import rest, rows
    from persist.storage import StorageService
    from persist.job import persist_bytes
    from persist.orgs import ensure_personal_org
    from projects import save_version, approve_latest, project_history
    suffix = uuid.uuid4().hex
    pid = 'durability-check-' + suffix
    fid = pid + '.svg'
    uid = 'durability-test-' + suffix
    org = ensure_personal_org(uid, 'Temporary durability verification')
    artifact = None
    try:
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10"><rect x="1" y="1" width="8" height="8" fill="none" stroke="red"/></svg>'
        artifact = persist_bytes(organization_id=org, kind='svg', data=svg,
            mime_type='image/svg+xml', source_file_id=fid, name=fid)
        def append(i):
            return save_version({'project_id': pid, 'project': 'Temporary verification'},
                {'file_id': fid, 'primitives': [{'type': 'panel', 'label': 'Panel', 'w': 10, 'h': 10}]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(append, range(8)))
        assert sorted(r['version'] for r in results) == list(range(1, 9))
        assert approve_latest(pid)['version'] == 8
        assert project_history(pid)['versions'][-1]['approved'] is True
        child = r'''
import sys
from persist.migrate_studio import load_env
load_env()
from projects import project_by_file
from persist.authz import authorize_customer_file
from persist.storage import StorageService
fid, uid = sys.argv[1:]
assert project_by_file(fid)['version'] == 8
allowed = authorize_customer_file(fid, {'id': uid}, auth_on=True)
assert allowed['allow']
assert not authorize_customer_file(fid, {'id': 'unrelated-test-user'}, auth_on=True)['allow']
assert b'<svg' in StorageService().get(allowed['artifact']['storage_path'])
print('Fresh process: project, SVG and owner authorization OK')
'''
        result = subprocess.run([sys.executable, '-c', child, fid, uid], capture_output=True, text=True, check=True)
        print(result.stdout.strip())
        print('Concurrent append: 8 distinct sequential versions; latest approval OK')
        print('Persisted project histories:', len(rows('lasermcp_projects')) - 1)
    finally:
        if artifact:
            StorageService().delete(artifact['storage_path'])
            rest('lasermcp_artifacts', method='DELETE', params={'id': 'eq.' + artifact['id']})
        rest('lasermcp_projects', method='DELETE', params={'id': 'eq.' + pid})
        rest('lasermcp_organizations', method='DELETE', params={'id': 'eq.' + org})
        print('Isolated smoke-test records removed')


if __name__ == '__main__':
    main()
