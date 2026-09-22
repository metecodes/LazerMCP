"""Six structural panels and a separate glued star, no hidden box."""
import math

def recipe(width=130,depth=90,height=180,thickness=3):
    w,d,h,t=map(float,(width,depth,height,thickness))
    if not all(math.isfinite(v) for v in (w,d,h,t)) or w<100 or d<60 or h<140 or not 2<=t<=4:
        raise ValueError('Reference recipe requires width>=100, depth>=60, height>=140 and 2–4 mm material.')
    e=h-50; span=e-40; mid=e/2
    def pose(o,u,v): return {'origin':o,'u':u,'v':v}
    frontpose=pose([0,t,0],[1,0,0],[0,0,1]); backpose=pose([0,d,0],[1,0,0],[0,0,1])
    def slot(x,y,sw,sh,part,tab): return {'x':x,'y':y,'w':sw,'h':sh,'mate':{'part':part,'tab':tab}}
    def tab(name,x,y,tw,th): return {'id':name,'x':x,'y':y,'w':tw,'h':th}
    house=[[0,0],[w,0],[w,e],[w/2,h],[0,e]]
    slots=[slot(1.5*t,mid,t,span,'left-side','front'),slot(w-1.5*t,mid,t,span,'right-side','front'),slot(w/2,5+t/2,14,t,'floor','front'),slot(w/2,17+t,t,16,'divider','front')]
    front={'type':'contour','label':'front-house-face','points':house,'placement':frontpose,'slots':slots,'markings':[{'kind':'icon','icon':'star','x':w/2,'y':h-29,'width':24,'operation':'ENGRAVE'}]}
    for x in (w*.2,w*.6):
        for y in (e*.22,e*.60):
            front['slots'] += [{'x':x,'y':y,'w':18,'h':30},{'x':x+22,'y':y-8,'w':14,'h':14},{'x':x+22,'y':y+8,'w':14,'h':14}]
    back={'type':'contour','label':'back-house-face','points':house,'placement':backpose,'slots':[slot(s['x'],s['y'],s['w'],s['h'],s['mate']['part'],'back') for s in slots[:4]]}
    length=d-2*t; sidepts=[[0,0],[length,0],[length,20],[length+t,20],[length+t,e-20],[length,e-20],[length,e],[0,e],[0,e-20],[-t,e-20],[-t,20],[0,20]]
    sides=[]
    for name,x in [('left-side',t),('right-side',w-2*t)]:
        sides.append({'type':'contour','label':name,'points':sidepts,'placement':pose([x,t,0],[0,1,0],[0,0,1]),'tabs':[tab('front',-t/2,mid,t,span),tab('back',length+t/2,mid,t,span)],'slots':[slot(length/2,5+t/2,22,t,'floor','left' if name=='left-side' else 'right')]})
    fw=w-4*t; cx=w/2-2*t; cy=length/2
    floorpts=[[0,0],[cx-7,0],[cx-7,-t],[cx+7,-t],[cx+7,0],[fw,0],[fw,cy-11],[fw+t,cy-11],[fw+t,cy+11],[fw,cy+11],[fw,length],[cx+7,length],[cx+7,length+t],[cx-7,length+t],[cx-7,length],[0,length],[0,cy+11],[-t,cy+11],[-t,cy-11],[0,cy-11]]
    floor={'type':'contour','label':'floor','points':floorpts,'placement':pose([2*t,t,5],[1,0,0],[0,1,0]),'tabs':[tab('front',cx,-t/2,14,t),tab('back',cx,length+t/2,14,t),tab('left',-t/2,cy,t,22),tab('right',fw+t/2,cy,t,22)],'slots':[slot(cx,cy,t,22,'divider','bottom')]}
    dh=e-(5+t)
    dividerpts=[[0,0],[cy-11,0],[cy-11,-t],[cy+11,-t],[cy+11,0],[length,0],[length,4],[length+t,4],[length+t,20],[length,20],[length,dh],[0,dh],[0,20],[-t,20],[-t,4],[0,4]]
    divider={'type':'contour','label':'divider','points':dividerpts,'placement':pose([w/2-t/2,t,5+t],[0,1,0],[0,0,1]),'tabs':[tab('front',-t/2,12,t,16),tab('back',length+t/2,12,t,16),tab('bottom',cy,-t/2,22,t)],'holes':[{'x':cy,'y':dh*.65,'d':30}]}
    front.pop('markings')
    starpts=[[w/2+12*(1 if i%2==0 else .45)*math.cos(math.pi/2+i*math.pi/5),h-29+12*(1 if i%2==0 else .45)*math.sin(math.pi/2+i*math.pi/5)] for i in range(10)]
    star={'type':'contour','label':'raised-star','points':starpts,'placement':pose([0,0,0],[1,0,0],[0,0,1]),'attachment':{'kind':'glue','to':'front-house-face'}}
    return [front,back,*sides,floor,divider,star]
