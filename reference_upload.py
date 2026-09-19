"""Chunked, short-lived reference image transport for MCP clients."""
from __future__ import annotations
import base64,hashlib,ipaddress,json,re,secrets,socket,urllib.request
from urllib.parse import urlparse
from datetime import datetime,timedelta,timezone
from keys import current_auth
from persist.storage import StorageService

MAX_CHUNK_CHARS=500_000
MAX_TOTAL_CHARS=16_000_000
MAX_CHUNKS=64
MAX_IMAGE_BYTES=12_000_000
ID_RE=re.compile(r'^[A-Za-z0-9_-]{32,80}$')

def _owner():
    p=current_auth.get() or {}
    raw='|'.join(str(p.get(k) or '') for k in ('id','owner','email','organization_id')) or 'anonymous'
    return hashlib.sha256(raw.encode()).hexdigest()
def _path(upload_id,name):
    if not ID_RE.fullmatch(str(upload_id)):raise ValueError('invalid reference_upload_id')
    return f'tmp/reference/{upload_id}/{name}'
def _manifest(upload_id):
    try:return json.loads(StorageService().get(_path(upload_id,'manifest.json')))
    except FileNotFoundError:raise ValueError('reference upload not found or expired')
def _check(row):
    if row.get('owner')!=_owner():raise ValueError('reference upload belongs to another MCP session')
    if datetime.fromisoformat(row['expires_at'])<=datetime.now(timezone.utc):raise ValueError('reference upload expired')

def start_reference_upload(expected_chunks=None,mime_type='image/png'):
    if expected_chunks is not None and not 1<=int(expected_chunks)<=MAX_CHUNKS:raise ValueError(f'expected_chunks must be 1..{MAX_CHUNKS}')
    upload_id=secrets.token_urlsafe(32);row={'id':upload_id,'owner':_owner(),'mime_type':mime_type,'expected_chunks':int(expected_chunks) if expected_chunks else None,'chunks':[],'total_chars':0,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    StorageService().put(_path(upload_id,'manifest.json'),json.dumps(row).encode(),'application/json')
    return {'success':True,'reference_upload_id':upload_id,'max_chunk_chars':MAX_CHUNK_CHARS,'expires_at':row['expires_at'],'next':'Call upload_reference_chunk once per chunk, then create_from_reference(reference_upload_id=...).'}
def upload_reference_chunk(upload_id,index,chunk):
    row=_manifest(upload_id);_check(row);index=int(index)
    if not 0<=index<MAX_CHUNKS:raise ValueError(f'chunk index must be 0..{MAX_CHUNKS-1}')
    if not isinstance(chunk,str) or not chunk or len(chunk)>MAX_CHUNK_CHARS:raise ValueError(f'chunk must be 1..{MAX_CHUNK_CHARS} base64 characters')
    if not re.fullmatch(r'[A-Za-z0-9+/=_-]+',chunk):raise ValueError('chunk contains non-base64 characters')
    previous=next((c for c in row['chunks'] if c['index']==index),None);new_total=row['total_chars']-(previous['chars'] if previous else 0)+len(chunk)
    if new_total>MAX_TOTAL_CHARS:raise ValueError('reference upload exceeds 16 MB base64')
    StorageService().put(_path(upload_id,f'{index:02d}.chunk'),chunk.encode('ascii'),'text/plain')
    row['chunks']=[c for c in row['chunks'] if c['index']!=index]+[{'index':index,'chars':len(chunk)}];row['chunks'].sort(key=lambda c:c['index']);row['total_chars']=new_total
    StorageService().put(_path(upload_id,'manifest.json'),json.dumps(row).encode(),'application/json')
    return {'success':True,'reference_upload_id':upload_id,'received_chunks':len(row['chunks']),'received_chars':new_total,'complete':bool(row['expected_chunks'] and len(row['chunks'])==row['expected_chunks'])}
def read_reference_upload(upload_id):
    row=_manifest(upload_id);_check(row);indices=[c['index'] for c in row['chunks']]
    expected=row.get('expected_chunks') or ((max(indices)+1) if indices else 0)
    if indices!=list(range(expected)):raise ValueError(f'reference upload incomplete; received {indices}, expected 0..{expected-1}')
    return ''.join(StorageService().get(_path(upload_id,f'{i:02d}.chunk')).decode('ascii') for i in indices)
def discard_reference_upload(upload_id):
    row=_manifest(upload_id);_check(row);store=StorageService()
    for c in row.get('chunks',[]):store.delete(_path(upload_id,f"{c['index']:02d}.chunk"))
    store.delete(_path(upload_id,'manifest.json'));return {'success':True,'discarded':upload_id}

def fetch_public_image(image_url):
    """Fetch only a public HTTPS image with strict size and network-address checks."""
    def validate(url):
        parsed=urlparse(str(url));host=parsed.hostname
        if parsed.scheme!='https' or not host or parsed.username or parsed.password:raise ValueError('image_url must be a public HTTPS URL')
        for info in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
            ip=ipaddress.ip_address(info[4][0])
            if not ip.is_global:raise ValueError('image_url resolves to a private or reserved address')
    validate(image_url)
    request=urllib.request.Request(image_url,headers={'User-Agent':'LaserMCP/1.0','Accept':'image/png,image/jpeg,image/webp'})
    with urllib.request.urlopen(request,timeout=20) as response:
        validate(response.geturl());kind=(response.headers.get_content_type() or '').lower()
        if kind not in {'image/png','image/jpeg','image/webp'}:raise ValueError('image_url did not return PNG, JPEG or WebP')
        declared=int(response.headers.get('Content-Length') or 0)
        if declared>MAX_IMAGE_BYTES:raise ValueError('image_url exceeds 12 MB')
        data=response.read(MAX_IMAGE_BYTES+1)
    if len(data)>MAX_IMAGE_BYTES:raise ValueError('image_url exceeds 12 MB')
    if not data:raise ValueError('image_url returned an empty body')
    return base64.b64encode(data).decode()
