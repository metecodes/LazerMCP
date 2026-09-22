"""Generate the checked-in standard model using the same compiler as MCP."""
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from standard_models import ROOT, MODEL_ID, model_recipe, model_parameters
from toolbox import render_toolbox
from review import review_built
from dxf_export import svg_bytes_to_dxf


def build():
    parts, params = model_recipe(), model_parameters()
    built = render_toolbox(parts, params)
    review = review_built(built)
    if review['final_status'] != 'PROTOTYPE READY':
        raise RuntimeError(review.get('look_again'))
    preview = built['assembly'].get('assembled_preview_svg')
    if not preview:
        raise RuntimeError('Assembled preview missing')
    dest = ROOT/'web'/'demo'
    (dest/f'{MODEL_ID}.svg').write_bytes(built['svg_bytes'])
    (dest/f'{MODEL_ID}.dxf').write_bytes(svg_bytes_to_dxf(built['svg_bytes']))
    (dest/f'{MODEL_ID}.assembled.svg').write_bytes(preview.encode() if isinstance(preview,str) else preview)
    (dest/f'{MODEL_ID}.recipe.json').write_text(json.dumps({'primitives':parts,'parameters':params},ensure_ascii=False,indent=2),encoding='utf-8')
    manifest = {'id':MODEL_ID,'version':1,'title':'Ev Kalemlik',
                'dimensions_mm':{'width':130,'depth':90,'height':180},'thickness_mm':2.7,
                'holding_nicks':False,'surface_texts':[], 'physical_part_count':len(parts),
                'palette':{'CUT':'#FF0000','ENGRAVE':'#000000'},
                'final_status':review['final_status'],'production_export':'BLOCKED',
                'physical_assembly':'NOT VERIFIED','physical_kerf_test':'NOT VERIFIED',
                'note':'Fotoğraftaki ev biçimli kalemliğin ölçülendirilmiş parametrik sürümü. Yıldız ön yüze yapıştırılır. Fiziksel geçme testi yapılmadı.',
                'tab_slot_pairs':built['assembly']['tab_slot_pairs'],
                'topology':built['topology'],'scorecard':review['scorecard']}
    (dest/f'{MODEL_ID}.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'model':MODEL_ID,'status':review['final_status'],'tab_slot_pairs':manifest['tab_slot_pairs']}))


if __name__=='__main__':
    build()
