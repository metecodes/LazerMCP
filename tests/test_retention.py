import json
import os
import tempfile
import unittest
import io
from urllib.error import HTTPError
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'MCP_DATA_DIR': self.temp.name, 'SUPABASE_URL': '', 'SUPABASE_SERVICE_ROLE_KEY': ''})
        env.start()
        self.addCleanup(env.stop)

    def test_ready_artifact_expires_and_open_does_not_extend(self):
        from persist.job import persist_bytes
        from persist.authz import authorize_customer_file
        from persist.artifacts import ArtifactRepository
        record = persist_bytes(organization_id='public', kind='svg', data=b'<svg/>',
            mime_type='image/svg+xml', source_file_id='retention.svg', durable=True)
        expiry = datetime.fromisoformat(record['expires_at'])
        created = datetime.fromisoformat(record['created_at'])
        self.assertAlmostEqual((expiry-created).total_seconds(), 86400, delta=1)
        self.assertTrue(authorize_customer_file('retention.svg', None, auth_on=True)['allow'])
        self.assertEqual(ArtifactRepository().get(record['id'])['expires_at'], record['expires_at'])

    def test_expired_owner_denied_before_cleanup(self):
        from persist.authz import authorize_customer_file
        artifact = {'id': 'test', 'organization_id': 'public', 'expires_at': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
        with patch('persist.authz.resolve_artifact_ref', return_value=artifact):
            decision = authorize_customer_file('expired.svg', None, auth_on=True)
        self.assertFalse(decision['allow'])
        self.assertEqual(decision['reason'], 'expired')

    def test_failed_object_delete_keeps_metadata_for_retry(self):
        from persist.cleanup import cleanup_expired
        with patch('persist.cleanup.ArtifactRepository') as repo, patch('persist.cleanup.StorageService') as store:
            repo.return_value.expired.return_value = [{'id': 'test', 'storage_path': 'tmp/test.svg'}]
            store.return_value.delete.side_effect = OSError('unavailable')
            self.assertEqual(cleanup_expired(), 0)
            repo.return_value.delete.assert_not_called()
            store.return_value.delete.side_effect = None
            self.assertEqual(cleanup_expired(), 1)
            repo.return_value.delete.assert_called_once_with('test')

    def test_storage_delete_uses_prefixes_api(self):
        from persist.supabase_rest import storage_delete
        response = MagicMock()
        with patch('persist.supabase_rest.supabase_url', return_value='https://example.supabase.co'), \
             patch('persist.supabase_rest.urllib.request.urlopen', return_value=response) as request:
            storage_delete('cikti', 'tmp/test.svg')
        sent = request.call_args.args[0]
        self.assertEqual(json.loads(sent.data), {'prefixes': ['tmp/test.svg']})
        self.assertTrue(sent.full_url.endswith('/storage/v1/object/cikti'))

    def test_storage_missing_object_400_becomes_missing_file(self):
        from persist.supabase_rest import storage_download
        failure = HTTPError('https://example.supabase.co', 400, 'Bad Request', {},
                            io.BytesIO(b'{"statusCode":"404","error":"not_found","message":"Object not found"}'))
        with patch('persist.supabase_rest.supabase_url', return_value='https://example.supabase.co'), \
             patch('persist.supabase_rest.urllib.request.urlopen', side_effect=failure):
            with self.assertRaises(FileNotFoundError):
                storage_download('cikti', 'missing.svg')
