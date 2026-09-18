"""Install the existing project storage credential through Vercel CLI stdin."""
import subprocess
from persist.migrate_studio import load_env
from persist.env import supabase_service_role

load_env()
secret = supabase_service_role()
if not secret:
    raise SystemExit('Supabase service-role configuration missing')
command = ['node', r'C:\Users\STEM\AppData\Local\npm-cache\_npx\69f9afb961c37556\node_modules\vercel\dist\index.js',
           'env', 'add', 'SUPABASE_SERVICE_ROLE_KEY', 'production', '--sensitive']
result = subprocess.run(command, input=secret+'\n', text=True, capture_output=True, timeout=90)
print((result.stdout + result.stderr).replace(secret, '[redacted]'))
raise SystemExit(result.returncode)
