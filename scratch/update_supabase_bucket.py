import re

with open('c:/Project/boxes-mcp/persist/supabase_rest.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''
def storage_create_bucket(bucket: str, public: bool = True) -> None:
    url = f"{supabase_url()}/storage/v1/bucket"
    body = json.dumps({"id": bucket, "name": bucket, "public": public}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError:
        pass

def storage_upload(bucket: str, path: str, data: bytes, mime: str) -> None:
'''

text = text.replace('def storage_upload(bucket: str, path: str, data: bytes, mime: str) -> None:', replacement)

with open('c:/Project/boxes-mcp/persist/supabase_rest.py', 'w', encoding='utf-8') as f:
    f.write(text)
