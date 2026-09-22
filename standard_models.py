"""Versioned site models, independent of expiring user-job storage."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
MODEL_ID = 'house-pencil-holder'


def model_recipe():
    from house_holder import recipe
    return recipe(width=130, depth=90, height=180, thickness=2.7)


def model_parameters():
    return {'project':'Standart ev kalemlik', 'thickness':2.7, 'burn':.15,
            'holding_nicks':False, 'surface_texts':[], 'format':'both',
            'allow_part_rotation':False,
            'machine':'desktop_400',
            'assembly_request':'Ev kalemliğini taban, yanlar, ön ve arka yüz ve bölücü ile dik monte et.'}


def get_standard_model(model_id=MODEL_ID, base_url=''):
    if model_id != MODEL_ID:
        return {'success':False,'error_code':'STANDARD_MODEL_NOT_FOUND'}
    manifest = ROOT/'web'/'demo'/f'{MODEL_ID}.json'
    if not manifest.is_file():
        return {'success':False,'error_code':'STANDARD_MODEL_NOT_BUILT'}
    result = json.loads(manifest.read_text(encoding='utf-8'))
    base = base_url.rstrip('/')
    result.update(success=True, model_url=base+'/models/'+MODEL_ID,
                  svg_url=base+f'/demo/{MODEL_ID}.svg',
                  dxf_url=base+f'/demo/{MODEL_ID}.dxf',
                  assembled_preview_url=(base+f'/demo/{MODEL_ID}.assembled.svg' if result.get('assembled_preview_available', True) else None),
                  source_svg_url=base+f'/demo/{MODEL_ID}.source.svg',
                  recipe_url=base+f'/demo/{MODEL_ID}.recipe.json',
                  expires_at=None, storage='versioned_site_asset')
    return result
