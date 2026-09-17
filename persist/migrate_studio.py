"""Run python -m persist.migrate_studio --check, then --apply after SQL migrations.

Copies available legacy files; never deletes the source or overwrites remote rows.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
from pathlib import Path
from persist.env import uses_supabase_app_db
from persist.supabase_rest import rest, rows, upsert


def load_env():
    path = Path(__file__).resolve().parents[1] / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--schema', action='store_true', help='Print API column names only')
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    load_env()
    if not uses_supabase_app_db():
        raise SystemExit('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required')
    if args.schema:
        definitions = rest('')['definitions']
        for table in ('lasermcp_organizations', 'lasermcp_organization_members', 'lasermcp_artifacts', 'lasermcp_projects'):
            print(table + ': ' + ', '.join(definitions.get(table, {}).get('properties', {})))
        return
    import urllib.error
    missing = False
    for table in ('lasermcp_organizations', 'lasermcp_organization_members', 'lasermcp_artifacts', 'lasermcp_projects'):
        try:
            rows(table, limit=1)
            print(f'{table}: OK')
        except urllib.error.HTTPError as exc:
            print(f'{table}: HTTP {exc.code} (check SQL migrations and service-role configuration)')
            missing = True
    if missing:
        raise SystemExit('Apply migrations/0002_durable_studio.sql first')
    if not args.apply:
        return
    from studio_store import data_dir
    from persist.authz import PUBLIC_ORG_ID
    from persist.storage import StorageService
    source = (args.data_dir or data_dir()).resolve()
    db = source / 'app.sqlite'
    count = 0
    if db.is_file():
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
            conn.row_factory = sqlite3.Row
            for table, conflict in (('organizations', 'id'), ('organization_members', 'organization_id,user_id')):
                for record in conn.execute(f'SELECT * FROM {table}'):
                    payload = dict(record)
                    if payload.get('id') == 'public' or payload.get('organization_id') == 'public':
                        continue
                    upsert('lasermcp_' + table, payload, conflict, ignore=True)
            for record in conn.execute('SELECT * FROM artifacts'):
                payload = dict(record)
                if rows('lasermcp_artifacts', id='eq.' + payload['id'], limit=1):
                    continue
                obj = (source / 'objects' / payload['storage_path']).resolve()
                if not obj.is_relative_to(source / 'objects'):
                    raise ValueError('Object path outside source directory')
                store = StorageService()
                if obj.is_file():
                    store.put(payload['storage_path'], obj.read_bytes(), payload['mime_type'])
                else:
                    # Object may already be in Supabase; verify before registering it.
                    store.get(payload['storage_path'])
                if payload['organization_id'] == 'public':
                    payload['organization_id'] = PUBLIC_ORG_ID
                upsert('lasermcp_artifacts', payload, ignore=True)
                count += 1
    projects = source / 'projects.json'
    if projects.is_file():
        for pid, project in json.loads(projects.read_text(encoding='utf-8')).items():
            upsert('lasermcp_projects', {'id': pid, 'payload': project}, ignore=True)
            count += 1
    print(f'Migration complete: {count} records processed; source preserved')


if __name__ == '__main__':
    main()
