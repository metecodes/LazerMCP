"""Editor previews use the existing compiler; no external service calls."""
from __future__ import annotations
import copy
import math
from typing import Any


def validate_draft(body: dict[str, Any], context: dict[str, Any]) -> tuple[list, dict]:
    parts = copy.deepcopy(body.get('primitives'))
    if not isinstance(parts, list) or not 1 <= len(parts) <= 100 or any(not isinstance(p, dict) for p in parts):
        raise ValueError('1–100 parça gerekli.')
    params = copy.deepcopy(body.get('parameters') or {})
    if not isinstance(params, dict):
        raise ValueError('Parametreler nesne olmalı.')
    params = {k: v for k, v in params.items() if not k.startswith('_')}
    params['project_id'] = context['project_id']
    params['project'] = context.get('name') or 'Editör projesi'
    # Stored primitives have already been compiled into millimetres.
    params['scale'] = 1
    # A changed design must be physically tested again.
    for key in ('physical_assembly', 'movement_test', 'use_test'):
        params[key] = 'not_verified'
    labels = [str(p.get('label') or p.get('type') or '') for p in parts]
    if any(not label.strip() for label in labels) or len(set(labels)) != len(labels):
        raise ValueError('Parça adları boş olamaz ve benzersiz olmalı.')
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Ölçüler sonlu sayı olmalı.')
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        elif isinstance(value, list):
            for v in value: finite(v)
    finite(parts)
    finite(params)
    connections = params.get('editor_connections') or []
    if not isinstance(connections, list) or len(connections) > 200 or any(not isinstance(c, dict) for c in connections):
        raise ValueError('En fazla 200 bağlantı tanımlanabilir.')
    for c in connections:
        if any(type(c.get(key)) is not int or c[key] not in range(4) for key in ('edge_a', 'edge_b')):
            raise ValueError('Bağlantı kenarı 0–3 olmalı.')
    for p in parts:
        for key in ('w', 'h', 'x', 'y', 'd'):
            if key in p and (not isinstance(p[key], (int, float)) or not 0 < p[key] <= 2000):
                raise ValueError('Parça ölçüleri 0–2000 mm aralığında olmalı.')
        if int(p.get('count') or 1) > 20:
            raise ValueError('Parça adedi en fazla 20 olabilir.')
    return parts, params


def connection_checks(parts, params):
    """Declared edge mates are checked independently of inferred assembly pairs."""
    lookup = {str(p.get('label') or p.get('type')): p for p in parts}
    result = []
    for i, c in enumerate(params.get('editor_connections') or []):
        if not isinstance(c, dict):
            continue
        a, b = lookup.get(c.get('a')), lookup.get(c.get('b'))
        note, status = 'Geçme kenarları ve nominal uzunluklar uyumlu; fiziksel montaj doğrulanmadı.', 'PASS'
        ea, eb = c.get('edge_a', 0), c.get('edge_b', 0)
        if not a or not b or c.get('a') == c.get('b'):
            note, status = 'Bağlantı için iki farklı mevcut parça seçin.', 'FAIL'
        elif type(ea) is not int or type(eb) is not int or ea not in range(4) or eb not in range(4):
            note, status = 'Geçersiz kenar.', 'FAIL'
        elif a.get('type') != 'panel' or b.get('type') != 'panel':
            note, status = 'Elle kenar bağlantısı panel parçalarında destekleniyor.', 'NOT_VERIFIED'
        else:
            ae, be = str(a.get('edges') or 'eeee'), str(b.get('edges') or 'eeee')
            al = float(a.get('w', 0) if ea % 2 == 0 else a.get('h', 0))
            bl = float(b.get('w', 0) if eb % 2 == 0 else b.get('h', 0))
            if len(ae) != 4 or len(be) != 4 or {ae[ea], be[eb]} != {'f', 'F'} or abs(al-bl) > .1:
                note, status = 'Kenarlar f/F olmalı ve uzunlukları eşleşmeli.', 'FAIL'
        result.append({**c, 'id': f'E{i+1:02}', 'a_name': c.get('a'), 'b_name': c.get('b'), 'status': status, 'note': note})
    return result


def editor_action(action, body, context, public_base_url=''):
    from projects import project_history
    if action == 'history':
        history = project_history(context['project_id']) or {}
        return {'success': True, 'versions': [{k: v.get(k) for k in ('n', 'at', 'file_id', 'primitives', 'parameters', 'final_status')} for v in history.get('versions', []) if v.get('primitives')]}
    if action not in ('preview', 'save'):
        raise ValueError('Bilinmeyen editör işlemi.')
    parts, params = validate_draft(body, context)
    checks = connection_checks(parts, params)
    if action == 'save':
        if any(c['status'] == 'FAIL' for c in checks):
            raise ValueError('Kaydetmeden önce elle tanımlanan bağlantıları düzeltin.')
        from payas_cad import create_design
        result = create_design(primitives=parts, parameters=params, public_base_url=public_base_url)
        result['editor_connections'] = checks
        return result
    from toolbox import render_toolbox
    from pipeline import review_only
    built = review_only(render_toolbox(parts, params))
    return {'success': True, 'svg': built['svg_bytes'].decode('utf-8'), 'assembled_preview_svg': (built.get('assembly') or {}).get('assembled_preview_svg'), 'review': built['review'], 'surface_content': built.get('surface_content'), 'editor_connections': checks, 'primitives': built['primitives']}
