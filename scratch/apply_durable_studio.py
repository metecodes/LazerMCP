"""Apply the user-approved durable studio migration using the existing CLI login."""
import json
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlparse
from persist.migrate_studio import load_env


def main():
    load_env()
    ref = urlparse(os.environ['SUPABASE_URL']).hostname.split('.')[0]
    token = (Path(os.environ['USERPROFILE']) / '.supabase' / 'access-token').read_text().strip()
    sql = (Path(__file__).resolve().parents[1] / 'migrations' / '0002_durable_studio.sql').read_text(encoding='utf-8')
    request = urllib.request.Request(f'https://api.supabase.com/v1/projects/{ref}/database/query',
        data=json.dumps({'query': sql, 'read_only': False}).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        response.read()
        print(f'Durable studio SQL migration applied: HTTP {response.status}')


if __name__ == '__main__':
    main()
