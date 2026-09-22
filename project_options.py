"""Per-job manufacturing choices; no shared mutable user defaults."""
import math
from xml.etree import ElementTree as ET


def resolve_choices(parameters=None, holding_nicks=None, surface_texts=None):
    params = dict(parameters or {})
    if holding_nicks is not None:
        params['holding_nicks'] = holding_nicks
    if surface_texts is not None:
        params['surface_texts'] = surface_texts
    if 'holding_nicks' in params and not isinstance(params['holding_nicks'], bool):
        raise ValueError('holding_nicks must be true or false')
    if 'surface_texts' in params and not isinstance(params['surface_texts'], list):
        raise ValueError('surface_texts must be a list; [] means no additional text')
    questions = []
    if 'holding_nicks' not in params:
        questions.append({'field':'holding_nicks', 'question':'Kesim noçlu mu, noçsuz mu olsun? Noç, parçayı levhada tutan küçük kesilmemiş köprüdür; geçme dişi değildir.',
                          'choices':[{'label':'Noçlu','value':True},{'label':'Noçsuz','value':False}]})
    if 'surface_texts' not in params and 'product_texts' not in params:
        questions.append({'field':'surface_texts', 'question':'Ürüne hangi yazılar eklensin ve hangi parçaya yazılsın? İlave yazı yoksa [] gönderin; mevcut tasarım yazıları korunur.'})
    if questions:
        return params, {'success':False, 'status':'NEEDS_INPUT', 'ready_to_cut':False,
                        'error_code':'PROJECT_CHOICES_REQUIRED', 'questions':questions,
                        'resolved_parameters':params,
                        'instruction':'Ask the user these questions before generating. Do not invent answers. Retry with their choices.',
                        'palette':{'CUT':'#FF0000','ENGRAVE':'#000000'}}
    return params, None


def apply_holding_nicks(svg_bytes, parameters=None, preserve_source_geometry=False):
    from holding_nicks import nick_cut_svg, NICK_MM
    params = parameters or {}
    enabled = params.get('holding_nicks', not preserve_source_geometry)
    if not isinstance(enabled, bool):
        raise ValueError('holding_nicks must be true or false')
    if not enabled:
        root = ET.fromstring(svg_bytes)
        if params.get('holding_nicks') is False and any(e.get('data-holding-nicks') or e.get('data-holding-bridges') for e in root.iter()):
            raise ValueError('SOURCE_HAS_HOLDING_NICKS: provide the original un-nicked geometry to request a no-nick export')
        return svg_bytes
    width = float(params.get('holding_nick_mm', NICK_MM))
    if not math.isfinite(width) or width <= 0:
        raise ValueError('holding_nick_mm must be positive and finite; use holding_nicks=false to disable')
    return nick_cut_svg(svg_bytes, width) or svg_bytes
