"""Strict ASCII DXF geometry import for semantic composition."""
import math
from xml.etree import ElementTree as ET

def dxf_to_svg(text):
    if not isinstance(text,str) or len(text)>10_000_000:raise ValueError('ASCII DXF text required (max 10 MB)')
    lines=text.replace('\r','').split('\n');pairs=[]
    for i in range(0,len(lines)-1,2):
        try:pairs.append((int(lines[i].strip()),lines[i+1].strip()))
        except ValueError:continue
    units=next((v for i,(c,v) in enumerate(pairs) if c==9 and v=='$INSUNITS' for c2,v in pairs[i+1:i+4] if c2 in {70,280}),None)
    if units not in {None,'4'}:raise ValueError('DXF composition currently requires millimetres ($INSUNITS=4)')
    try:start=next(i for i,p in enumerate(pairs) if p==(2,'ENTITIES'))+1;end=next(i for i in range(start,len(pairs)) if pairs[i]==(0,'ENDSEC'))
    except StopIteration:raise ValueError('DXF ENTITIES section missing')
    chunks=[];i=start
    while i<end:
        if pairs[i][0]!=0:i+=1;continue
        typ=pairs[i][1].upper();j=i+1
        if typ=='POLYLINE':
            head=[];verts=[];j=i+1
            while j<end and pairs[j]!=(0,'SEQEND'):
                if pairs[j]==(0,'VERTEX'):
                    k=j+1;row=[]
                    while k<end and pairs[k][0]!=0:row.append(pairs[k]);k+=1
                    verts.append(row);j=k
                else:head.append(pairs[j]);j+=1
            chunks.append((typ,head,verts));i=j+1;continue
        k=j
        while k<end and pairs[k][0]!=0:k+=1
        chunks.append((typ,pairs[j:k],[]));i=k
    entities=[];bounds=[]
    def first(rows,code,default=0):return next((v for c,v in rows if c==code),default)
    for index,(typ,row,verts) in enumerate(chunks):
        layer=first(row,8,'UNKNOWN').upper();op=layer if layer in {'CUT','ENGRAVE','SCORE','GUIDE'} else 'UNKNOWN';pts=[];closed=False
        if typ=='POLYLINE':pts=[(float(first(v,10)),float(first(v,20))) for v in verts];closed=int(first(row,70,'0'))&1==1
        elif typ=='LWPOLYLINE':
            x=None
            for c,v in row:
                if c==10:x=float(v)
                elif c==20 and x is not None:pts.append((x,float(v)));x=None
            closed=int(first(row,70,'0'))&1==1
        elif typ=='LINE':pts=[(float(first(row,10)),float(first(row,20))),(float(first(row,11)),float(first(row,21)))]
        elif typ in {'CIRCLE','ARC'}:
            cx,cy,r=float(first(row,10)),float(first(row,20)),float(first(row,40));a0=0 if typ=='CIRCLE' else math.radians(float(first(row,50)));a1=math.tau if typ=='CIRCLE' else math.radians(float(first(row,51)))
            if a1<=a0:a1+=math.tau
            n=max(16,math.ceil((a1-a0)*r/.35));pts=[(cx+r*math.cos(a0+(a1-a0)*n0/n),cy+r*math.sin(a0+(a1-a0)*n0/n)) for n0 in range(n+1)];closed=typ=='CIRCLE'
        else:continue
        if len(pts)<2:continue
        if closed and pts[-1]!=pts[0]:pts.append(pts[0])
        bounds.extend(pts);entities.append((index,op,pts,closed))
    if not entities:raise ValueError('No supported DXF geometry (POLYLINE/LWPOLYLINE/LINE/CIRCLE/ARC)')
    minx=min(x for x,y in bounds);maxx=max(x for x,y in bounds);miny=min(y for x,y in bounds);maxy=max(y for x,y in bounds);margin=5;w=maxx-minx+2*margin;h=maxy-miny+2*margin
    root=ET.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','width':f'{w}mm','height':f'{h}mm','viewBox':f'0 0 {w} {h}'})
    groups={op:ET.SubElement(root,'g',{'id':op}) for op in {'CUT','ENGRAVE','SCORE','GUIDE','UNKNOWN'}}
    for index,op,pts,closed in entities:
        coords=[(x-minx+margin,maxy-y+margin) for x,y in pts];d='M '+' L '.join(f'{x:.6f} {y:.6f}' for x,y in coords)+(' Z' if closed else '')
        ET.SubElement(groups[op],'path',{'id':f'DXF_{index}','d':d,'fill':'none','data-operation':op,'data-operation-origin':'EXPLICIT' if op!='UNKNOWN' else 'UNKNOWN','stroke':'#FF0000' if op=='CUT' else '#FFFF00'})
    return ET.tostring(root,encoding='unicode')
