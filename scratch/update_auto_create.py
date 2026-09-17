import re

with open('c:/Project/boxes-mcp/persist/storage.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''    def put(self, storage_path: str, data: bytes, mime_type: str) -> None:
        if uses_supabase_app_db():
            from persist.supabase_rest import storage_upload, storage_create_bucket

            storage_create_bucket(storage_bucket(), public=True)
            storage_upload(storage_bucket(), storage_path, data, mime_type)
            return'''

text = text.replace('''    def put(self, storage_path: str, data: bytes, mime_type: str) -> None:
        if uses_supabase_app_db():
            from persist.supabase_rest import storage_upload

            storage_upload(storage_bucket(), storage_path, data, mime_type)
            return''', replacement)

with open('c:/Project/boxes-mcp/persist/storage.py', 'w', encoding='utf-8') as f:
    f.write(text)
