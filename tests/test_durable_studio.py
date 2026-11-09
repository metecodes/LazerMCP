"""Remote metadata survives local state loss and never silently falls back."""
import os
import tempfile
import unittest
from unittest.mock import patch


class DurableStudioTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_SERVICE_ROLE_KEY': 'test-secret', 'MCP_DATA_DIR': tempfile.mkdtemp()})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_file_lookup_reads_remote_without_sqlite(self):
        from persist.artifacts import ArtifactRepository
        from persist.authz import authorize_customer_file
        row = {'id': '00000000-0000-0000-0000-000000000002', 'organization_id': 'public',
               'source_file_id': 'design.svg'}
        with patch('persist.artifacts.connect', side_effect=AssertionError('local DB used')), \
             patch('persist.artifacts.rows', return_value=[row]) as query, \
             patch('persist.artifacts.rest') as request:
            decision = authorize_customer_file('design.svg', None, auth_on=True)
            self.assertTrue(decision['allow'])
            query.assert_called_once_with('lasermcp_artifacts', source_file_id='eq.design.svg', order='created_at.desc', limit=1)
            request.assert_not_called()

    def test_project_save_uses_atomic_remote_append(self):
        from projects import save_version
        with patch('projects.read_json', side_effect=AssertionError('local JSON used')), \
             patch('projects.rows', return_value=[]), \
             patch('projects.rest', return_value={'project_id': 'existing', 'version': 3}) as request:
            result = save_version({'project_id': 'existing', 'project': 'Box'}, {'file_id': 'design.svg'})
            self.assertEqual(result['version'], 3)
            self.assertEqual(request.call_args.args, ('rpc/append_lasermcp_version',))
            self.assertEqual(request.call_args.kwargs['body']['p_version']['file_id'], 'design.svg')

    def test_project_can_load_after_local_files_disappear(self):
        from projects import project_by_file
        project = {'id': 'box', 'name': 'Box', 'versions': [{'n': 1, 'file_id': 'design.svg',
                   'primitives': [{'type': 'panel', 'w': 20, 'h': 30}]}]}
        with patch('projects.rows', return_value=[{'id': 'box', 'payload': project}]), \
             patch('projects.read_json', side_effect=AssertionError('local JSON used')):
            self.assertEqual(project_by_file('design.svg')['primitives'][0]['w'], 20)

    def test_remote_failure_does_not_fall_back(self):
        from projects import project_history
        with patch('projects.rows', side_effect=OSError('remote unavailable')), \
             patch('projects.read_json', side_effect=AssertionError('fallback used')):
            with self.assertRaises(OSError):
                project_history('box')

    def test_membership_checked_remotely(self):
        from persist.orgs import OrganizationRepository
        with patch('persist.orgs.rows', return_value=[]), \
             patch('persist.orgs.connect', side_effect=AssertionError('local DB used')):
            self.assertFalse(OrganizationRepository().member_of('other-user', 'org'))

    def test_remote_expiration_cleanup_uses_metadata(self):
        from persist.artifacts import ArtifactRepository
        with patch('persist.artifacts.rows', return_value=[]) as query:
            self.assertEqual(ArtifactRepository().expired('2026-09-17T00:00:00Z'), [])
            query.assert_called_once_with('lasermcp_artifacts', expires_at='lte.2026-09-17T00:00:00Z')

    def test_approval_does_not_replace_project_history(self):
        from projects import approve_latest
        with patch('projects.project_history', return_value={'id': 'box'}), \
             patch('projects.rest', return_value={'project_id': 'box', 'version': 4}) as request:
            self.assertEqual(approve_latest('box')['version'], 4)
            request.assert_called_once_with('rpc/approve_lasermcp_version', method='POST', body={'p_id': 'box'})

    def test_cannot_approve_someone_elses_project(self):
        from projects import approve_latest
        with patch('projects.project_history', return_value=None), patch('projects.rest') as request:
            with self.assertRaises(ValueError):
                approve_latest('box')
            request.assert_not_called()


class ProjectScopeTests(unittest.TestCase):
    """Hosted project history is per organization; guests see none, operators see all."""

    def setUp(self):
        self.env = patch.dict(os.environ, {'SUPABASE_URL': 'https://example.supabase.co',
            'SUPABASE_SERVICE_ROLE_KEY': 'test-secret', 'MCP_DATA_DIR': tempfile.mkdtemp()})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _list(self, principal, owned_files=()):
        from keys import current_auth
        import projects
        token = current_auth.set(principal)
        try:
            with patch('projects._owner_org', side_effect=lambda p: str((p or {}).get('organization_id') or '')), \
                 patch('projects.rows', return_value=[{'source_file_id': f} for f in owned_files]), \
                 patch('projects.rest', return_value=[]) as request:
                out = projects.list_projects(limit=80)
            return out, request
        finally:
            current_auth.reset(token)

    def test_guest_gets_no_history_and_no_query(self):
        out, request = self._list(None)
        self.assertEqual(out, [])
        request.assert_not_called()

    def test_user_filter_covers_owner_and_legacy_files(self):
        _, request = self._list({'id': 'u1', 'email': 'a@x.com', 'organization_id': 'org-a'}, ['old.svg'])
        params = request.call_args.kwargs['params']
        self.assertIn('owner_org.in.("org-a")', params['or'])
        self.assertIn('file_id.in.("old.svg")', params['or'])
        self.assertNotIn('*', params['select'])

    def test_operator_lists_without_filter(self):
        _, request = self._list({'id': 'u2', 'email': 'metehan1387@gmail.com', 'organization_id': 'org-b'})
        self.assertNotIn('or', request.call_args.kwargs['params'])

    def test_history_hidden_from_other_orgs(self):
        from keys import current_auth
        import projects
        project = {'id': 'p', 'versions': [{'n': 1, 'file_id': 'a.svg', 'owner_org': 'org-a'}]}
        for org, visible in (('org-a', True), ('org-b', False)):
            token = current_auth.set({'id': 'u', 'email': 'u@x.com', 'organization_id': org})
            try:
                with patch('projects._owner_org', return_value=org), \
                     patch('projects.rows', side_effect=[[{'id': 'p', 'payload': project}], []]):
                    self.assertEqual(projects.project_history('p') is not None, visible, org)
            finally:
                current_auth.reset(token)

    def _save_into(self, org, project):
        from keys import current_auth
        import projects
        token = current_auth.set({'id': 'u', 'email': 'u@x.com', 'organization_id': org} if org else None)
        try:
            with patch('projects._owner_org', side_effect=lambda p: str((p or {}).get('organization_id') or '')), \
                 patch('projects.rows', side_effect=[[{'id': 'p', 'payload': project}], []]), \
                 patch('projects.rest', return_value={'version': 1}) as request:
                projects.save_version({'project_id': 'p', 'project': 'Box'}, {'file_id': 'new.svg'})
            return request.call_args.kwargs['body']['p_id']
        finally:
            current_auth.reset(token)

    def test_versions_cannot_be_appended_to_another_orgs_project(self):
        owned = {'id': 'p', 'versions': [{'n': 1, 'file_id': 'a.svg', 'owner_org': 'org-a'}]}
        self.assertEqual(self._save_into('org-a', owned), 'p')
        # Someone else's id (or a guess) still saves the work, but as a new project.
        self.assertNotEqual(self._save_into('org-b', owned), 'p')
        self.assertNotEqual(self._save_into('', owned), 'p')

    def test_guest_can_keep_revising_an_unowned_draft(self):
        draft = {'id': 'p', 'versions': [{'n': 1, 'file_id': 'g.svg', 'owner_org': ''}]}
        self.assertEqual(self._save_into('', draft), 'p')
