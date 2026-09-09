"""Local engraving coordinates -> assembled outside face. Local +X is reading-right."""
OUTSIDE_NORMALS={'Bank Front':(0,-1,0),'Bank Back':(0,1,0),'Bank Left':(-1,0,0),
 'Bank Right':(1,0,0),'Bank Top':(0,0,1),'Bank Bottom':(0,0,-1),
 'Rear Cover':(0,1,0),'Arm Left':(-1,0,0),'Arm Right':(1,0,0)}

def plane(name,x,y):
 if name=='Bank Front':return (3+x,0,15+y)
 if name=='Bank Back':return (117-x,85,15+y)
 if name=='Bank Left':return (0,82-x,15+y)
 if name=='Bank Right':return (120,3+x,15+y)
 if name=='Bank Top':return (3+x,3+y,160)
 # Bottom has no engraving; its drawing remains an inside view for rail coordinates.
 if name=='Bank Bottom':return (3+x,3+y,12)
 if name=='Rear Cover':return (100-x,88,19+y)
 if name=='Arm Left':return (-3,28-x,62+y)
 if name=='Arm Right':return (123,x-16,62+y)
 if name=='Divider':return (x,29,15+y)
 if name=='Battery Shelf':return (44+x,9+y,20)
 if name.startswith('Rail'):
  xx={'Rail L1':12,'Rail L2':36,'Rail R1':84,'Rail R2':108}[name]
  return (xx-1.5,x-16,12-y)
 if name.startswith('Toe'):return ((10.5 if name.endswith('Left') else 82.5)+x,y-13,3)
 raise ValueError(name)

def validate_outside_faces():
 checked=[]
 for name,normal in OUTSIDE_NORMALS.items():
  if name=='Bank Bottom':continue  # blank inside-view machining face
  origin=plane(name,0,0);px=plane(name,1,0);py=plane(name,0,1)
  u=[px[i]-origin[i] for i in range(3)];v=[py[i]-origin[i] for i in range(3)]
  cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
  if cross!=normal:raise ValueError('Mirrored engraving face: '+name)
  if name!='Bank Top' and v!=(0,0,1) and v!=[0,0,1]:raise ValueError('Upside-down engraving: '+name)
  checked.append(name)
 return checked
