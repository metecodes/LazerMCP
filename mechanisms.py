"""Semantic mechanism classification with explicit metadata taking priority."""
from __future__ import annotations

MECHANISMS={'wheel','road_roller_drum','pulley','gear','disc','propeller','rotor','flywheel'}

def mechanism_type(part):
    if not isinstance(part,dict):return None
    explicit=part.get('mechanism')
    value=explicit.get('type') if isinstance(explicit,dict) else explicit
    value=str(value or '').strip().lower()
    if value in MECHANISMS:return value
    kind=str(part.get('type') or part.get('kind') or '').strip().lower()
    aliases={'pervane':'propeller','fan':'propeller','blades':'propeller','disk':'disc','circle':'disc','teker':'wheel'}
    kind=aliases.get(kind,kind)
    return kind if kind in MECHANISMS else None

def classify(primitives):
    return [{'part':str(p.get('label') or p.get('id') or p.get('type') or ''),'type':mechanism_type(p),'rotating':bool((p.get('mechanism') or {}).get('rotating')) if isinstance(p.get('mechanism'),dict) else mechanism_type(p) in {'wheel','road_roller_drum','propeller','rotor','pulley','gear','flywheel'}} for p in primitives or [] if isinstance(p,dict) and mechanism_type(p)]
