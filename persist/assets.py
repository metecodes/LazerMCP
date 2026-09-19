import hashlib,json,secrets,uuid
from persist.db import connect
from persist.env import uses_supabase_app_db
from persist.supabase_rest import rest,rows
from studio_store import now_iso

def token_hash(token):return hashlib.sha256(str(token).encode()).hexdigest()
def _table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,organization_id TEXT,name TEXT,asset_type TEXT,storage_path TEXT,default_operation TEXT,bounds TEXT,token_hash TEXT,created_at TEXT,UNIQUE(organization_id,name))''')
class AssetRepository:
    def insert(self,row):
        payload={**row,'id':row.get('id') or str(uuid.uuid4()),'created_at':now_iso()}
        if uses_supabase_app_db():rest('lasermcp_assets',method='POST',body=payload);return payload
        local={**payload,'bounds':json.dumps(payload['bounds'])}
        with connect() as conn:_table(conn);conn.execute('INSERT INTO assets VALUES(:id,:organization_id,:name,:asset_type,:storage_path,:default_operation,:bounds,:token_hash,:created_at)',local);conn.commit()
        return payload
    def list(self,org,token):
        digest=token_hash(token)
        if uses_supabase_app_db():found=rows('lasermcp_assets',organization_id=f'eq.{org}',token_hash=f'eq.{digest}',order='created_at.desc')
        else:
            with connect() as conn:_table(conn);found=[dict(r) for r in conn.execute('SELECT * FROM assets WHERE organization_id=? AND token_hash=? ORDER BY created_at DESC',(org,digest))]
        for row in found:
            if isinstance(row.get('bounds'),str):row['bounds']=json.loads(row['bounds'])
        return found
    def get(self,asset_id,org,token):
        found=[r for r in self.list(org,token) if r['id']==asset_id]
        return found[0] if found else None
    def update(self,asset_id,org,token,changes):
        current=self.get(asset_id,org,token)
        if not current:return None
        allowed={k:v for k,v in changes.items() if k in {'name','asset_type','storage_path','default_operation','bounds'}}
        if uses_supabase_app_db():
            rest('lasermcp_assets',method='PATCH',params={'id':f'eq.{asset_id}','organization_id':f'eq.{org}','token_hash':f'eq.{token_hash(token)}'},body=allowed)
        else:
            local={**allowed}
            if 'bounds' in local:local['bounds']=json.dumps(local['bounds'])
            if local:
                sets=','.join(f'{key}=?' for key in local)
                with connect() as conn:conn.execute(f'UPDATE assets SET {sets} WHERE id=? AND organization_id=? AND token_hash=?',(*local.values(),asset_id,org,token_hash(token)));conn.commit()
        return {**current,**allowed}
def new_token():return secrets.token_urlsafe(32)
