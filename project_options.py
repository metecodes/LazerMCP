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
    if 'repair_cut_gaps' in params and not isinstance(params['repair_cut_gaps'], bool):
        raise ValueError('repair_cut_gaps must be true or false')
    if params.get('repair_cut_gaps') and params.get('holding_nicks') is not False:
        raise ValueError('repair_cut_gaps requires holding_nicks=false')
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
        if params.get('holding_nicks') is False:
            from cut_gap_repair import repair_cut_gaps
            return repair_cut_gaps(svg_bytes,explicit=params.get('repair_cut_gaps',False))
        return svg_bytes
    width = float(params.get('holding_nick_mm', NICK_MM))
    if not math.isfinite(width) or width <= 0:
        raise ValueError('holding_nick_mm must be positive and finite; use holding_nicks=false to disable')
    return nick_cut_svg(svg_bytes, width) or svg_bytes
