"""Operation-level laser intent. Relative values require a machine/material coupon."""
from __future__ import annotations
from copy import deepcopy
import math

DEFAULTS={
 'CUT':{'mode':'through_cut','speed_scale':1.0,'power_scale':1.0,'passes':1,'through_cut':True},
 'ENGRAVE':{'mode':'surface_engrave','speed_scale':2.0,'power_scale':0.30,'passes':1,'through_cut':False},
 'SCORE':{'mode':'surface_score','speed_scale':0.8,'power_scale':0.35,'passes':1,'through_cut':False},
 'GUIDE':{'mode':'preview_only','speed_scale':1.0,'power_scale':0.0,'passes':0,'through_cut':False},
}

def resolve_operation_settings(parameters=None):
    settings=deepcopy(DEFAULTS);custom=(parameters or {}).get('operation_settings') or {}
    for op,values in custom.items():
        op=str(op).upper()
        if op not in settings or not isinstance(values,dict):continue
        for key in ('speed_scale','power_scale','speed_mm_s','power_percent','passes'):
            if key in values:settings[op][key]=float(values[key]) if key!='passes' else int(values[key])
    for op,row in settings.items():
        if any(not math.isfinite(row[key]) for key in ('speed_scale','power_scale','speed_mm_s','power_percent','passes') if key in row):
            raise ValueError(f'{op} laser settings must be finite')
        if row['speed_scale'] <= 0:raise ValueError(f'{op} speed_scale must be >0')
        if not 0 <= row['power_scale'] <= 1:raise ValueError(f'{op} power_scale must be between 0 and 1')
        if row['passes'] < 0:raise ValueError(f'{op} passes must be >=0')
        if 'speed_mm_s' in row and row['speed_mm_s'] <= 0:raise ValueError(f'{op} speed_mm_s must be >0')
        if 'power_percent' in row and not 0 <= row['power_percent'] <= 100:raise ValueError(f'{op} power_percent must be between 0 and 100')
    engrave=settings['ENGRAVE'];cut=settings['CUT']
    if engrave['speed_scale']<=0:raise ValueError('ENGRAVE speed_scale must be >0')
    if not 0<=engrave['power_scale']<cut['power_scale']:raise ValueError('ENGRAVE power must be lower than CUT power')
    if 'power_percent' in engrave and 'power_percent' in cut and engrave['power_percent'] >= cut['power_percent']:
        raise ValueError('ENGRAVE power_percent must be lower than CUT power_percent')
    if engrave['passes']!=1:raise ValueError('ENGRAVE must use exactly one surface pass')
    engrave['through_cut']=False
    return {'operations':settings,'requires_coupon':True,'note':'Relative speed/power scales are starting intent. Calibrate absolute machine values with a material coupon before production.'}

def stamp_operation_settings(svg_bytes,profile):
    from xml.etree import ElementTree as ET
    root=ET.fromstring(svg_bytes);ops=profile['operations']
    for group in root.iter():
        op=str(group.get('data-operation') or group.get('id') or '').upper()
        if op not in ops:continue
        row=ops[op];group.set('data-laser-mode',row['mode']);group.set('data-speed-scale',str(row['speed_scale']));group.set('data-power-scale',str(row['power_scale']));group.set('data-passes',str(row['passes']));group.set('data-through-cut',str(bool(row['through_cut'])).lower())
        if 'speed_mm_s' in row:group.set('data-speed-mm-s',str(row['speed_mm_s']))
        if 'power_percent' in row:group.set('data-power-percent',str(row['power_percent']))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
