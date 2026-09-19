import hashlib
from xml.etree import ElementTree as ET
from design_engine import import_svg_document
from semantic_cad import inspect_design,create_vector_graphic
from number_match_puzzle import _emit
from shapely.ops import unary_union
from shapely.affinity import translate
from persist.assets import AssetRepository,new_token,token_hash
from persist.storage import StorageService

def upload_asset(organization_id,name,asset_type,svg,library_token=None):
    if asset_type not in {'logo','icon','illustration'}:raise ValueError('asset_type must be logo, icon or illustration')
    token=library_token or new_token();built=import_svg_document(svg,{'svg_default_operation':'ENGRAVE'});doc=inspect_design(built['svg_bytes'])
    geoms=[o['_geom'] for o in doc['_objects'] if o['operation']=='ENGRAVE']
    if not geoms:raise ValueError('asset has no ENGRAVE vector geometry')
    geom=unary_union(geoms);bounds=list(geom.bounds);normalized=translate(geom,-bounds[0],-bounds[1]);body=_emit(normalized,'#FFFF00',.15)
    width,height=bounds[2]-bounds[0],bounds[3]-bounds[1];clean=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}"><g id="ENGRAVE">{body}</g></svg>'.encode()
    aid=__import__('uuid').uuid4().hex;digest=hashlib.sha256(clean).hexdigest();path=StorageService().durable_path(organization_id,aid,digest,'svg');StorageService().put(path,clean,'image/svg+xml')
    row=AssetRepository().insert({'id':aid,'organization_id':organization_id,'name':name[:100],'asset_type':asset_type,'storage_path':path,'default_operation':'ENGRAVE','bounds':[0,0,width,height],'token_hash':token_hash(token)})
    return {'success':True,'asset':{k:v for k,v in row.items() if k!='token_hash'},'library_token':token if not library_token else None}
def list_assets(organization_id,library_token):return [{k:v for k,v in r.items() if k not in {'token_hash','storage_path'}} for r in AssetRepository().list(organization_id,library_token)]
def get_asset(organization_id,library_token,asset_id):
    row=AssetRepository().get(asset_id,organization_id,library_token)
    if not row:raise ValueError('asset not found or access token invalid')
    svg=StorageService().get(row['storage_path']);return row,svg
def get_asset_info(organization_id,library_token,asset_id):
    row,svg=get_asset(organization_id,library_token,asset_id)
    return {'asset':{k:v for k,v in row.items() if k not in {'token_hash','storage_path'}},'svg':svg.decode() if isinstance(svg,bytes) else svg}
def replace_asset(organization_id,library_token,asset_id,svg,name=None,asset_type=None):
    old,_=get_asset(organization_id,library_token,asset_id)
    built=import_svg_document(svg,{'svg_default_operation':'ENGRAVE'});doc=inspect_design(built['svg_bytes']);geoms=[o['_geom'] for o in doc['_objects'] if o['operation']=='ENGRAVE']
    if not geoms:raise ValueError('asset has no ENGRAVE vector geometry')
    geom=unary_union(geoms);bounds=list(geom.bounds);normalized=translate(geom,-bounds[0],-bounds[1]);width,height=bounds[2]-bounds[0],bounds[3]-bounds[1]
    clean=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}"><g id="ENGRAVE">{_emit(normalized,"#FFFF00",.15)}</g></svg>'.encode()
    digest=hashlib.sha256(clean).hexdigest();path=StorageService().durable_path(organization_id,asset_id,digest,'svg');StorageService().put(path,clean,'image/svg+xml')
    row=AssetRepository().update(asset_id,organization_id,library_token,{'name':name or old['name'],'asset_type':asset_type or old['asset_type'],'storage_path':path,'bounds':[0,0,width,height]})
    return {'success':True,'asset':{k:v for k,v in row.items() if k not in {'token_hash','storage_path'}}}
def place_asset(organization_id,library_token,asset_id,parent_part_id,placement='center',width=None,height=None):
    row,svg=get_asset(organization_id,library_token,asset_id);doc=inspect_design(svg);geom=unary_union([o['_geom'] for o in doc['_objects'] if o['operation']=='ENGRAVE']);fragment=ET.fromstring('<svg>'+_emit(geom,'#FFFF00',.15)+'</svg>');d=' '.join(p.get('d','') for p in fragment)
    return create_vector_graphic(d,id='GFX_'+asset_id[:10].upper(),parent_part_id=parent_part_id,graphic_type=row['asset_type'],placement=placement,size={'width':width or 0,'height':height or 0},source='asset:'+asset_id)
