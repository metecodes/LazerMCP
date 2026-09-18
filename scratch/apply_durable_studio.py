"""Apply the user-approved durable studio migration using the existing CLI login."""
import json
import argparse
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlparse
from persist.migrate_studio import load_env


def query(sql, *, parameters=None, read_only=False):
    load_env()
    ref = urlparse(os.environ['SUPABASE_URL']).hostname.split('.')[0]
    token = (Path(os.environ['USERPROFILE']) / '.supabase' / 'access-token').read_text().strip()
    request = urllib.request.Request(f'https://api.supabase.com/v1/projects/{ref}/database/query',
        data=json.dumps({'query': sql, 'read_only': read_only, 'parameters': parameters or []}).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--retention', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    if args.status:
        result = query("SELECT j.jobname, j.active, d.status, d.end_time FROM cron.job j LEFT JOIN LATERAL (SELECT status, end_time FROM cron.job_run_details WHERE jobid=j.jobid ORDER BY runid DESC LIMIT 1) d ON true WHERE j.jobname='lasermcp-artifact-cleanup'", read_only=True)
        print(json.dumps(result))
        return
    root = Path(__file__).resolve().parents[1]
    filename = '0003_artifact_retention.sql' if args.retention else '0002_durable_studio.sql'
    query((root / 'migrations' / filename).read_text(encoding='utf-8'))
    if args.retention:
        from persist.env import supabase_service_role, supabase_url, storage_bucket
        for name, value in (('lasermcp_storage_url', supabase_url()),
                            ('lasermcp_storage_key', supabase_service_role()),
                            ('lasermcp_storage_bucket', storage_bucket())):
            existing = query('SELECT id FROM vault.secrets WHERE name = $1', parameters=[name], read_only=True)
            if existing:
                query('SELECT vault.update_secret($1::uuid, $2, $3)', parameters=[existing[0]['id'], value, name])
            else:
                query('SELECT vault.create_secret($1, $2)', parameters=[value, name])
        result = query("SELECT jobname, schedule, active FROM cron.job WHERE jobname = 'lasermcp-artifact-cleanup'", read_only=True)
        print('Retention migration and encrypted cleanup configuration applied')
        print(json.dumps(result))
    else:
        print('Durable studio SQL migration applied')


if __name__ == '__main__':
    main()
