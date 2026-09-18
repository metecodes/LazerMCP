"""Create the user's corrected version, preserving the original artifact organization."""
from persist.migrate_studio import load_env
load_env()
from persist.artifacts import ArtifactRepository
from keys import current_auth
from payas_cad import create_design
from house_holder import recipe
import json
old=ArtifactRepository().by_source('create-design-20260918-111746-d06e69b6.svg')
assert old, 'Original artifact metadata unavailable; cannot preserve access scope.'
token=current_auth.set({'organization_id':old['organization_id']})
try:
 r=create_design(primitives=recipe(),parameters={'project_id':'payas-stem-house-pencil-holder-p-fb28','project':'Payas STEM House Pencil Holder Reference Joint Style v12','format':'both','material':'poplar_3mm','thickness':3,'burn':.15,'what_you_see':'Ev biçimli ön ve arka yüz, iki yan panel, taban ve orta bölme. Açık üst, dört pencere grubu. Büyük tırnak-slot bağlantıları; ayrıca gizli box gövdesi yok.'},public_base_url='https://mcp.metehanavci.com')
 assert r.get('file_id'),r.get('look_again')
 assert r.get('artifact_persistence')=='ARTIFACT_PERSISTENCE_SUCCESS'
 assert r['assembly']['ok']
 from pathlib import Path
 Path('scratch/house-result.json').write_text(json.dumps({k:r.get(k) for k in ('file_id','svg_url','dxf_id','assembled_preview_url','final_status','artifacts')},ensure_ascii=False))
 print(json.dumps({k:r.get(k) for k in ('file_id','svg_url','assembled_preview_url','final_status','artifact_persistence')},ensure_ascii=True))
finally:current_auth.reset(token)
