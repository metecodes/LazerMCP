"""Bounded HP-GL/PLT vector importer. Unsupported drawing commands fail explicitly."""
from __future__ import annotations
import math,re
from xml.etree import ElementTree as ET

MAX_BYTES=5_000_000
MAX_POINTS=200_000
NUMBER=re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)')


def import_plt_document(text,parameters=None):
    params=parameters or {}
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_BYTES or not text.strip():
        raise ValueError('PLT must contain HP-GL text, at most 5 MB.')
    for wrapper in ('\x1b%0B','\x1b%1B','\x1b%0A','\x1b%1A','\x1bE'):
        text=text.replace(wrapper,'')
    if any(ord(c)>127 or (ord(c)<32 and c not in '\t\r\n') for c in text):
        raise ValueError('PLT is not supported ASCII HP-GL; binary/DMPL files are not accepted.')
    units=float(params.get('plt_units_per_mm',40))
    if not math.isfinite(units) or not 1<=units<=100000:raise ValueError('plt_units_per_mm must be 1–100000 (HP-GL default 40).')
    default=str(params.get('plt_default_operation','CUT')).upper()
    operations={str(k):str(v).upper() for k,v in (params.get('plt_pen_operations') or {}).items()}
    if any(a not in ('CUT','ENGRAVE') for a in [default,*operations.values()]):raise ValueError('PLT operations must be CUT or ENGRAVE.')
    pos=(0.,0.);absolute=True;down=False;pen=1
    sx=sy=1/units;ox=oy=0.;rotation=0.;ip=None
    paths=[];active=None;warnings=set();count=0;page_ended=False
    def point(x,y):
        a,b=x*sx+ox,y*sy+oy
        c,s=math.cos(rotation),math.sin(rotation)
        return (a*c-b*s,a*s+b*c)
    def inverse(a,b):
        c,s=math.cos(rotation),math.sin(rotation)
        return ((a*c+b*s-ox)/sx,(-a*s+b*c-oy)/sy)
    def stop():
        nonlocal active
        active=None
    def emit(points,standalone=False):
        nonlocal count,active
        if pen==0:return
        if page_ended:raise ValueError('Multi-page PLT is not supported; import one page at a time.')
        count+=len(points)
        if count>MAX_POINTS:raise ValueError('PLT exceeds 200000 vector points.')
        if standalone or active is None:
            active={'pen':pen,'points':list(points)};paths.append(active)
        else:active['points'].extend(points[1:])
        if standalone:stop()
    def move(x,y):
        nonlocal pos
        target=(x,y) if absolute else (pos[0]+x,pos[1]+y)
        if down:emit([point(*pos),point(*target)])
        else:stop()
        pos=target
    def steps(radius,angle,chord):
        r=abs(radius)*max(abs(sx),abs(sy))
        if r<=0:raise ValueError('PLT arc/circle radius must be positive.')
        maxangle=2*math.acos(max(-1,min(1,1-.02/r))) if r>.02 else math.pi/2
        increment=min(math.radians(abs(chord or 5)),maxangle,math.pi/2)
        if increment<=0:raise ValueError('PLT chord angle must be positive.')
        n=max(2,math.ceil(abs(angle)/increment))
        if n>10000:raise ValueError('PLT arc/circle exceeds 10000 segments.')
        return n
    at=0;commands=0
    while at<len(text):
        while at<len(text) and (text[at].isspace() or text[at]==';'):at+=1
        if at==len(text):break
        command=text[at:at+2].upper()
        if len(command)!=2 or not command.isalpha():raise ValueError(f'Invalid HP-GL instruction at offset {at}.')
        at+=2;start=at
        while at<len(text) and text[at]!=';' and not text[at].isalpha():at+=1
        raw=text[start:at].strip()
        if at<len(text) and text[at]==';':at+=1
        commands+=1
        if commands>100000:raise ValueError('PLT exceeds 100000 commands.')
        if command in ('LB','PE','PM','FP','EP','BZ','BR','WG','EW'):
            raise ValueError(f'PLT instruction {command} is not supported; no incomplete drawing was saved.')
        matches=list(NUMBER.finditer(raw))
        residue=NUMBER.sub('',raw)
        if residue.strip(' ,\t\r\n'):raise ValueError(f'Invalid numeric arguments for PLT {command}.')
        vals=[float(m.group()) for m in matches]
        if any(not math.isfinite(v) or abs(v)>1e9 for v in vals):raise ValueError(f'PLT {command} coordinate is invalid or too large.')
        if command in ('IN','DF'):
            if vals:raise ValueError(f'{command} takes no parameters.')
            stop();absolute=True;down=False;sx=sy=1/units;ox=oy=0;rotation=0;ip=None
            if command=='IN':pos=(0.,0.);pen=1
        elif command=='SP':
            if len(vals)>1 or (vals and (vals[0]<0 or vals[0]!=int(vals[0]))):raise ValueError('SP requires a nonnegative integer pen.')
            stop();pen=int(vals[0]) if vals else 0
        elif command in ('PA','PR','PU','PD'):
            if len(vals)%2:raise ValueError(f'{command} requires coordinate pairs.')
            if command=='PA':absolute=True
            elif command=='PR':absolute=False
            elif command=='PU':down=False;stop()
            elif command=='PD':down=True
            for x,y in zip(vals[::2],vals[1::2]):move(x,y)
        elif command in ('AA','AR'):
            if len(vals) not in (3,4):raise ValueError(f'{command} needs center X,Y, sweep and optional chord angle.')
            cx,cy,angle=vals[:3]
            if command=='AR':cx+=pos[0];cy+=pos[1]
            r=math.hypot(pos[0]-cx,pos[1]-cy);startangle=math.atan2(pos[1]-cy,pos[0]-cx);sweep=math.radians(angle)
            n=steps(r,sweep,vals[3] if len(vals)==4 else 5)
            pts=[(cx+r*math.cos(startangle+sweep*i/n),cy+r*math.sin(startangle+sweep*i/n)) for i in range(n+1)]
            if down:emit([point(x,y) for x,y in pts])
            else:stop()
            pos=pts[-1]
        elif command=='CI':
            if len(vals) not in (1,2) or vals[0]<=0:raise ValueError('CI needs positive radius and optional chord angle.')
            r=vals[0];n=steps(r,2*math.pi,vals[1] if len(vals)==2 else 5)
            pts=[point(pos[0]+r*math.cos(2*math.pi*i/n),pos[1]+r*math.sin(2*math.pi*i/n)) for i in range(n)]
            emit(pts+[pts[0]],True)
        elif command in ('EA','ER'):
            if len(vals)!=2:raise ValueError(f'{command} needs one coordinate pair.')
            x,y=vals
            if command=='ER':x+=pos[0];y+=pos[1]
            emit([point(*pos),point(x,pos[1]),point(x,y),point(pos[0],y),point(*pos)],True)
        elif command=='IP':
            if len(vals) not in (0,4):raise ValueError('IP needs four coordinates or no parameters.')
            ip=vals or None
        elif command=='SC':
            physical=point(*pos);stop()
            if not vals:sx=sy=1/units;ox=oy=0
            else:
                if len(vals) not in (4,5) or (len(vals)==5 and vals[4]!=0):raise ValueError('Only linear anisotropic SC scaling is supported.')
                if not ip:raise ValueError('SC needs explicit IP coordinates to recover physical millimetres.')
                xmin,xmax,ymin,ymax=vals[:4]
                if xmax==xmin or ymax==ymin:raise ValueError('SC scaling ranges must be nonzero.')
                sx=(ip[2]-ip[0])/units/(xmax-xmin);sy=(ip[3]-ip[1])/units/(ymax-ymin)
                if sx==0 or sy==0:raise ValueError('IP scaling ranges must be nonzero.')
                ox=ip[0]/units-xmin*sx;oy=ip[1]/units-ymin*sy
            pos=inverse(*physical)
        elif command=='RO':
            if len(vals)>1 or (vals and vals[0] not in (0,90,180,270)):raise ValueError('RO requires 0,90,180 or 270 degrees.')
            physical=point(*pos);stop();rotation=math.radians(vals[0] if vals else 0);pos=inverse(*physical)
        elif command=='PG':
            if vals:raise ValueError('Parameterized PG is not supported.')
            stop();page_ended=True
        elif command in ('LT','VS','PW','PC','LA','WU'):
            warnings.add(f'{command}: plotter styling ignored; vector geometry retained.')
        else:raise ValueError(f'Unsupported PLT instruction {command}; no incomplete drawing was saved.')
    paths=[p for p in paths if len(p['points'])>1 and any(math.dist(p['points'][0],a)>1e-8 for a in p['points'][1:])]
    if not paths:raise ValueError('PLT contains no drawable vectors.')
    points=[a for p in paths for a in p['points']];xs,ys=zip(*points)
    minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys);margin=2.;w=maxx-minx+2*margin;h=maxy-miny+2*margin
    root=ET.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','width':f'{w:.6f}mm','height':f'{h:.6f}mm','viewBox':f'0 0 {w:.6f} {h:.6f}'})
    group=ET.SubElement(root,'g')
    for i,p in enumerate(paths):
        op=operations.get(str(p['pen']),default);pts=p['points'];closed=math.dist(pts[0],pts[-1])<1e-8
        # Bake physical coordinates into paths; grouping may move elements.
        # HP-GL Y-up is converted to SVG Y-down exactly once.
        d='M'+' L'.join(f'{margin+x-minx:.6f},{margin+maxy-y:.6f}' for x,y in pts)+(' Z' if closed else '')
        ET.SubElement(group,'path',{'id':f'plt-path-{i+1}','d':d,'fill':'none','stroke':'#FF0000' if op=='CUT' else '#000000','stroke-width':'.1','data-operation':op,'data-operation-origin':'EXPLICIT','data-semantic-role':'custom','data-plt-pen':str(p['pen'])})
    from manufacturing import finish_manufacturing_svg
    raw, manufacturing = finish_manufacturing_svg(ET.tostring(root,encoding='utf-8'))
    return {'svg_bytes':raw,'manufacturing':manufacturing,'width_mm':w,'height_mm':h,'preset':'import_plt','imported':True,'count':len(paths),'parameters':params,'plt_import':{'format':'HP-GL','units_per_mm':units,'source_bounds_mm':[minx,miny,maxx,maxy],'path_count':len(paths),'closed_paths':sum(math.dist(p['points'][0],p['points'][-1])<1e-8 for p in paths),'arc_tolerance_mm':.02,'default_operation':default,'pen_operations':operations,'warnings':sorted(warnings),'note':'2D vector import; does not infer panel mates or a 3D assembly.'}}
