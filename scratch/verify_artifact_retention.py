"""Live expiry/deletion check; uses only isolated test objects."""
from datetime import datetime, timedelta, timezone
import uuid
from persist.migrate_studio import load_env


def main():
    load_env()
    from persist.artifacts import ArtifactRepository
    from persist.authz import PUBLIC_ORG_ID, authorize_customer_file
    from persist.job import persist_bytes
    from persist.storage import StorageService, sha256_hex
    from persist.supabase_rest import rest
    from scratch.apply_durable_studio import query
    suffix = uuid.uuid4().hex
    store, repo = StorageService(), ArtifactRepository()
    current = expired = None
    path = 'tmp/' + PUBLIC_ORG_ID + '/retention-test-' + suffix + '.svg'
    data = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    try:
        current = persist_bytes(organization_id=PUBLIC_ORG_ID, kind='svg', data=data,
            mime_type='image/svg+xml', source_file_id='active-' + suffix + '.svg')
        original = repo.get(current['id'])['expires_at']
        # Even old application code clearing expiry cannot bypass the DB trigger.
        rest('lasermcp_artifacts', method='PATCH', params={'id': 'eq.' + current['id']}, body={'expires_at': None})
        assert repo.get(current['id'])['expires_at'] == original
        assert authorize_customer_file(current['source_file_id'], None, auth_on=True)['allow']
        store.put(path, data, 'image/svg+xml')
        expired = repo.insert({'organization_id':PUBLIC_ORG_ID,'kind':'svg','storage_path':path,
            'file_size':len(data),'mime_type':'image/svg+xml','hash':sha256_hex(data),
            'source_file_id':'expired-' + suffix + '.svg',
            'created_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()})
        decision = authorize_customer_file(expired['source_file_id'], None, auth_on=True)
        assert decision['reason'] == 'expired' and not decision['allow']
        query('SELECT public.lasermcp_cleanup_artifacts()')
        assert repo.get(expired['id']) is None
        assert store.get(current['storage_path']) == data
        try:
            store.get(path)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('Expired object bytes still available')
        print('PASS: fixed 24-hour expiry, old-code expiry reset blocked, expired access denied, bytes deleted, active file preserved')
    finally:
        if current:
            store.delete(current['storage_path']); repo.delete(current['id'])
        if expired:
            store.delete(path); repo.delete(expired['id'])
        print('Isolated retention test records removed')


if __name__ == '__main__':
    main()
