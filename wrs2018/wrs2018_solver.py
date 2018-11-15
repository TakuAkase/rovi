#!/usr/bin/python

import cv2
import numpy as np
import math
import roslib
import rospy
import yodpy
from rovi.msg import Floats
from rovi.msg import PickingPose
from rospy.numpy_msg import numpy_msg
from std_msgs.msg import Bool
from std_msgs.msg import String
from std_srvs.srv import Trigger,TriggerRequest
from sensor_msgs.msg import PointCloud
from sensor_msgs.msg import ChannelFloat32
from geometry_msgs.msg import Point32
from geometry_msgs.msg import Point
from geometry_msgs.msg import Transform
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../script'))
import tflib
import tf
from jsk_rviz_plugins.msg import OverlayText

scene_ply = "/tmp/wrs2018_scene.ply"

def xyz2quat(e):
  tf=Transform()
  k = math.pi / 180 * 0.5
  cx = math.cos(e.rotation.x * k)
  cy = math.cos(e.rotation.y * k)
  cz = math.cos(e.rotation.z * k)
  sx = math.sin(e.rotation.x * k)
  sy = math.sin(e.rotation.y * k)
  sz = math.sin(e.rotation.z * k)
  tf.translation.x=e.translation.x
  tf.translation.y=e.translation.y
  tf.translation.z=e.translation.z
  tf.rotation.x = cy * cz * sx - cx * sy * sz
  tf.rotation.y = cy * sx * sz + cx * cz * sy
  tf.rotation.z = cx * cy * sz - cz * sx * sy
  tf.rotation.w = sx * sy * sz + cx * cy * cz
  return tf

def check_obst(e):
  global scnPn
  q=xyz2quat(e)
#  print 'base2work quat',e
  i=np.linalg.inv(tflib.toRT(q))
#  print 'base2work inv rt',i
  P=np.vstack((scnPn.T,np.ones((1,len(scnPn)))))
  tp=np.dot(i[:3],P).T
#  print "work2base points",tp.shape,tp
  W=np.where(tp.T[0]>=-6.0)
  tp=tp[W[len(W)-1]]
  W=np.where(tp.T[0]<=+6.0)
  tp=tp[W[len(W)-1]]
  W=np.where(tp.T[1]>=-6.0)
  tp=tp[W[len(W)-1]]
  W=np.where(tp.T[1]<=+6.0)
  tp=tp[W[len(W)-1]]
  W=np.where(tp.T[2]>=+8.0)
  tp=tp[W[len(W)-1]]
  W=np.where(tp.T[2]<=+50.0)
  tp=tp[W[len(W)-1]]
#  d=tp.astype(np.float32)
#  cv2.ppf_match_3d.writePLY(d,'obs.ply')
  print "tp",len(tp),tp.shape
  return True if (len(tp)<100) else False

def get_clps(e,start):
  global scnPn
  print 'pp deg euler',e
  q=xyz2quat(e)
  print 'pp quat',q
  ze=Transform()
  ze.translation.x=0
  ze.translation.y=0
  ze.translation.z=15 * (1 if (start==True) else -1)
  ze.rotation.x=0
  ze.rotation.y=0
  ze.rotation.z=0
  ze.rotation.w=0
#  print 'zoffset+ deg euler',ze
  zq=xyz2quat(ze)
#  print 'zoffset+ quat',zq
  mat=np.dot(tflib.toRT(q),tflib.toRT(zq))
  deg=tflib.fromRTtoEulerCBA(mat)
  deg[2]=deg[2]+20
  # check obstacle
  P=np.vstack((scnPn.T,np.ones((1,len(scnPn)))))
  W=np.where(P.T[0]>=-6.0)
  P=P[W[len(W)-1]]
  W=np.where(P.T[0]<=+6.0)
  P=P[W[len(W)-1]]
  W=np.where(P.T[1]>=-6.0)
  P=P[W[len(W)-1]]
  W=np.where(P.T[1]<=+6.0)
  P=P[W[len(W)-1]]
  W=np.where(P.T[2]>=-2.0)
  P=P[W[len(W)-1]]
  W=np.where(P.T[2]<=+50.0)
  P=P[W[len(W)-1]]
  print "P",len(P),P.shape
  if (len(P)>100):
    deg[0]=-999
    deg[1]=-999
    deg[2]=-999
  print "deg",deg
  return deg

def get_fix_zaxis_rotation(x, y, z, w):  #fix z rotation
  hq=Transform()
  hq.rotation.x=x
  hq.rotation.y=y
  hq.rotation.z=z
  hq.rotation.w=w
  #print 'halcon quat',hq
  hmat=tflib.toRT(hq)
  #print 'halcon mat',hmat
  hcba=tflib.fromRTtoEulerCBA(hmat)
  print 'halcon deg euler',hcba
  ze=Transform()
  ze.rotation.x=0
  ze.rotation.y=0
  ze.rotation.z=-hcba[5]
  ze.rotation.w=0
  #print 'zoffset deg euler',ze
  zq=xyz2quat(ze)
  #print 'zoffset quat',zq
  mat=np.dot(tflib.toRT(hq),tflib.toRT(zq))
  deg=tflib.fromRTtoEulerCBA(mat)
  print 'result deg euler',deg
  return deg[3], deg[4], deg[5]

def robot_rxyzabc_to_rt(rx, ry, rz, a_rad, b_rad, c_rad):
  matrix44 = np.zeros((4, 4))
  x_mat = np.zeros((4, 4))
  y_mat = np.zeros((4, 4))
  z_mat = np.zeros((4, 4))

  matrix44[3, 3] = 1
  matrix44[0, 3] = rx
  matrix44[1, 3] = ry
  matrix44[2, 3] = rz

  x_mat[0, 0] = 1.0
  x_mat[1, 1] = np.cos(a_rad)
  x_mat[1, 2] = -np.sin(a_rad)
  x_mat[2, 1] = np.sin(a_rad)
  x_mat[2, 2] = np.cos(a_rad)

  y_mat[0, 0] = np.cos(a_rad)
  y_mat[0, 2] = np.sin(b_rad)
  y_mat[1, 1] = 1.0
  y_mat[2, 0] = -np.sin(b_rad)
  y_mat[2, 2] = np.cos(b_rad)

  z_mat[0, 0] = np.cos(c_rad)
  z_mat[0, 1] = -np.sin(c_rad)
  z_mat[1, 0] = np.sin(c_rad)

  z_mat[1, 1] = np.cos(c_rad)
  z_mat[2, 2] = 1.0

  temp_mat1 = np.zeros((3, 3))
  temp_mat2 = np.zeros((3, 3))

  for m in range(3):
    for n in range(3):
      for k in range(3):
        temp_mat1[m, n] += y_mat[m, k] * z_mat[k, n]

  for m in range(3):
    for n in range(3):
      for k in range(3):
        temp_mat2[m, n] += x_mat[m, k] * temp_mat1[k, n]

  for m in range(3):
    for n in range(3):
      matrix44[m, n] = temp_mat2[m, n]

  return matrix44

def P0():
  return np.array([]).reshape((-1,3))

def np2Fm(d):  #numpy to Floats (unit is meter for RViZ)
  f=Floats()
  f.data=np.ravel(d) / 1000.0
  return f

def np2FmNoDivide(d):  #numpy to Floats (unit is already meter for RViZ)
  f=Floats()
  f.data=np.ravel(d)
  return f

def prepare_model(stl_file):
  global model, is_prepared
  result = yodpy.train3D(stl_file, relSamplingDistance = 0.03)
  retcode = result[0]
  model = result[1]
  print('train3D retcode=', retcode)
  print('train3D model size=', len(model))
  print('train3D model=', model)
  if retcode == 0:
    is_prepared = True
  return

def cb_ps(msg): #callback of ps_floats
  print "cb_ps called!"

  if not is_prepared:
    print "ERROR: prepare_model() is NOT done. ignore this ps_floats."
    pub_Y1.publish(False)
    return

  global bTmLat, mTc, scnPn
  P=np.reshape(msg.data,(-1,3))
  n,m=P.shape
  #P=voxel(P)
  print "PointCloud In:",n
  print "PC(camera in mm)",P
  n,m=P.shape
  #print "PointCloud Out:",n
  P=np.vstack((P.T,np.ones((1,n))))
  P=np.dot(bTm[:3],np.dot(mTc,P)).T
  #print "P2",P
  print P.shape
  if (not np.isnan(xmin)):
    W = np.where(P.T[0] >= xmin)
    P=P[W[len(W)-1]]
  if (not np.isnan(xmax)):
    W = np.where(P.T[0] <= xmax)
    P=P[W[len(W)-1]]
  if (not np.isnan(ymin)):
    W = np.where(P.T[1] >= ymin)
    P=P[W[len(W)-1]]
  if (not np.isnan(ymax)):
    W = np.where(P.T[1] <= ymax)
    P=P[W[len(W)-1]]
  if (not np.isnan(zmin)):
    W = np.where(P.T[2] >= zmin)
    P=P[W[len(W)-1]]
  if (not np.isnan(zmax)):
    W = np.where(P.T[2] <= zmax)
    P=P[W[len(W)-1]]
  #print "where",P
  n,m=P.shape
  print P.shape
  #print "PC",P
  P=P.reshape((-1,3))
  scnPn=np.vstack((scnPn,P))
  pub_scf.publish(np2Fm(scnPn))

  cv2.ppf_match_3d.writePLY(scnPn.astype(np.float32), scene_ply)
  pub_Y1.publish(True)
  return

def cb_X0(f):
  global scnPn, mfoPn, mnpPn, mpiPn
  print "X0:scene reset"
  scnPn=P0()
  mfoPn=P0()
  mnpPn=P0()
  mpiPn=P0()
  pub_scf.publish(np2Fm(scnPn))
  pub_mfof.publish(np2FmNoDivide(mfoPn))
  pub_mnpf.publish(np2FmNoDivide(mnpPn))
  pub_mpif.publish(np2FmNoDivide(mpiPn))
  return

def cb_X1(f):
  cb_X0(True)
  global bTm,bTmLat
  bTmLat=np.copy(bTm)
  print "bTm latched",bTmLat
  genpc=None
  try:
    genpc=rospy.ServiceProxy('/rovi/pshift_genpc',Trigger)
    req=TriggerRequest()
    ret=genpc(req)      #will continue to callback cb_ps
    print "genpc result: ",ret
    if (ret.success==False):
      pub_Y1.publish(False)
  except rospy.ServiceException, e:
    print 'Genpc proxy failed:',e
    pub_Y1.publish(False)
  return

def cb_X2(f):
  global mfoPn, mnpPn, mpiPn

  # Picking Pose to be returned
  pp = PickingPose()
  pp.ok = False
  pp.errorreason = ""
  pp.x = 0
  pp.y = 0
  pp.z = 0
  pp.a = 0
  pp.b = 0
  pp.c = 0

  # To Pick Candidate List (Picking Pose and tmP_xyz (see below))
  tpcl_pp = []
  tpcl_tp = []

  # match rate to return
  match_rate_ret = 0

  maxz = -10000
  maxz_tpli = -1

  result = yodpy.loadPLY(scene_ply, scale="mm")
  retcode = result[0]
  scene = result[1]
  print('loadPLY retcode=',retcode)
  print('loadPLY scene=',scene)

  if retcode != 0:
    print "ERROR: X2 loadPLY() failed."
    pub_Y2.publish(pp)
    return

  sP = scene.reshape((-1,3))
  sPn, sPm = sP.shape
  print "sPn=", sPn
  if (sPn < sparse_threshold):
    print "ERROR: X2 loadPLY() and PC is sparse."
    pp.errorreason = "SPARSE"
    pub_Y2.publish(pp)
    return

  # TODO
  #result = yodpy.match3D(scene)
  #result = yodpy.match3D(scene,relSamplingDistance=0.03,keyPointFraction=0.1,minScore=0.11) # 0.25?
#  result = yodpy.match3D(scene,relSamplingDistance=0.03,keyPointFraction=0.3,minScore=0.25)
  #result = yodpy.match3D(scene,relSamplingDistance=0.03,keyPointFraction=0.05,minScore=0.11)
  #result = yodpy.match3D(scene,relSamplingDistance=0.05,keyPointFraction=0.1,minScore=0.11)
  result = yodpy.match3D(scene,relSamplingDistance=0.03,keyPointFraction=0.1,minScore=0.095) # 0.25?

  retcode = result[0]
  transforms = result[1]
  quats = result[2]
  matchRates = result[3]
  print('match3D retcode=',retcode)

  if retcode != 0:
    print "ERROR: X2 match3D() failed."
    pub_Y2.publish(pp)
    return

  if (len(matchRates) <= 0):
    print "ERROR: X2 match3D() no match."
    pub_Y2.publish(pp)
    return

  isCL=False
  for i, (transform, quat, matchRate) in enumerate(zip(transforms, quats, matchRates)):
    # NOTE:
    # 1. 'matchRates' are in descending order.
    # 2. 'quat' means a picking Pose.
    #    'quat' consists of 7 numpy.float64 values. They are x, y, z of Point position, and x, y, z, w of Quaternion orientation.
    # 3. Unit of x, y, z of Point position of 'quat' is meter. (transform's xyz unit is also meter.)
    #
    #print('match3D quat=', quat)
    print('i=', i, 'match3D matchRate=', matchRate)

    tm_xyz_nvxyz = np.reshape(transform, (-1, 3))
    tmP_xyz = tm_xyz_nvxyz[::2, :] 
    #print "tmP_xyz=", tmP_xyz

    isRateOK=True
    if (matchRate<=0.25):
      isRateOK=False

    qx = quat[3]
    qy = quat[4]
    qz = quat[5]
    qw = quat[6]
    #print "from HALCON quat.x=", qx, "quat.y=", qy, "quat.z=", qz, "quat.w=", qw

    fixz_rot = get_fix_zaxis_rotation(qx, qy, qz, qw)
    ppx = quat[0] * 1000.0
    ppy = quat[1] * 1000.0
    ppz = quat[2] * 1000.0
    pprx = fixz_rot[0]
    ppry = fixz_rot[1]
    pprz = fixz_rot[2]

    print "****[", i, "]**** Picking Pose: x=", ppx, "y=", ppy, "z=", ppz, "roll=", pprx, "pitch=", ppry, "yaw=", pprz

    me=Transform()
    me.translation.x=ppx
    me.translation.y=ppy
    me.translation.z=ppz
    me.rotation.x=pprx
    me.rotation.y=ppry
    me.rotation.z=pprz
    if (isRateOK==True):
      # check obstacles
      if (check_obst(me)==False):
        print "  [", i, "]   check_obst NG"
        mnpPn = np.vstack((mnpPn, tmP_xyz))
        continue
      else:
        print "  [", i, "]   check_obst OK"

    rad_euler = tf.transformations.euler_from_quaternion((qx, qy, qz, qw))
    m2b44 = robot_rxyzabc_to_rt(ppx, ppy, ppz, rad_euler[0], rad_euler[1], rad_euler[2])
    #print "m2b44=\n", m2b44

    radian = m2b44[0, 2] * 0 + m2b44[1, 2] * 0 + m2b44[2, 2] * 1
    radian = radian / np.sqrt((np.power(m2b44[0, 2], 2) + np.power(m2b44[1, 2], 2) + np.power(m2b44[2, 2], 2)) * (0 + 0 + 1))
    radian = np.arccos(radian)
    degree = radian * 180.0 / np.pi
    abs_deg = np.abs(degree)
    deg_threshold = 35.0
    deg_stand=85.0
    cs=[0,0,0]
    print "--[", i, "]-- angle between Picking Vector and Z-Axis=", degree, "its abs=", abs_deg
    if (abs_deg >= deg_threshold):
      print "==[", i, "]== angle between Picking Vector and Z-Axis abs(", abs_deg, ") >= ", deg_threshold, "can NOT Pick"
      if (isRateOK==True):
        mnpPn = np.vstack((mnpPn, tmP_xyz))
      if ((isCL==False) and (abs_deg>=deg_stand)):
        print "cl detected!"
        isCL=True
        cs=get_clps(me,True)
        ce=get_clps(me,False)
        if (cs[0]==-999 and ce[0]==-999):
          isCL=False
      continue

    else:
      if (isRateOK==False):
        continue

      print "^^[", i, "]^^ angle between Picking Vector and Z-Axis abs(", abs_deg, ") < ", deg_threshold, "can Pick (...append to candidate list)"
      # TODO more check
      cpp = PickingPose()
      cpp.ok = True
      cpp.errorreason = ""
      cpp.x = ppx
      cpp.y = ppy
      cpp.z = ppz
      cpp.a = pprx
      cpp.b = ppry
      cpp.c = pprz
      tpcl_pp.append(cpp)
      tpcl_tp.append(tmP_xyz)
      if (i == 0 or ppz > maxz):
        maxz = ppz
        maxz_tpli = len(tpcl_tp) - 1
        match_rate_ret = matchRate
        print "now maxz=", maxz, "maxz_tpli=", maxz_tpli, "match_rate_ret=", match_rate_ret
      continue

  if (maxz_tpli >= 0):
    maxz_tp = tpcl_tp.pop(maxz_tpli)
    maxz_pp = tpcl_pp.pop(maxz_tpli)
    mpiPn = np.vstack((mpiPn, maxz_tp))
    pp = maxz_pp
    print "*=*=*=*maxz_tpli[", maxz_tpli, "]*=*=*=* Picking Pose to return (maxz): x=", pp.x, "y=", pp.y, "z=", pp.z, "roll=", pp.a, "pitch=", pp.b, "yaw=", pp.c
    for fo_tp in tpcl_tp:
      mfoPn = np.vstack((mfoPn, fo_tp))
  else:
    if (isCL==True):
      pp.errorreason="CL"
      pp.x=cs[0]
      pp.y=cs[1]
      pp.z=cs[2]
      pp.a=ce[0]
      pp.b=ce[1]
      pp.c=ce[2]
      pub_Y2.publish(pp)
      return

  text=OverlayText()
  text.text="Matching Rate %.1f %%" %(match_rate_ret * 100)
  pub_msg.publish(text)

  pub_mfof.publish(np2FmNoDivide(mfoPn))
  pub_mnpf.publish(np2FmNoDivide(mnpPn))
  pub_mpif.publish(np2FmNoDivide(mpiPn))

  pub_Y2.publish(pp)

  return

def cb_tf(tf):
  global bTm
  bTm=tflib.toRT(tf)
  return

########################################################

rospy.init_node("solver",anonymous=True)
###Input topics
rospy.Subscriber("/robot/tf",Transform,cb_tf)
rospy.Subscriber("/rovi/ps_floats",numpy_msg(Floats),cb_ps)
#rospy.Subscriber("/solver/X0",Bool,cb_X0)  #Clear scene
rospy.Subscriber("/solver/X1",Bool,cb_X1)  #Capture and genpc into scene
rospy.Subscriber("/solver/X2",Bool,cb_X2)  #Recognize work and calc picking pose

###Output topics
pub_tf=rospy.Publisher("/solver/tf",Transform,queue_size=1)
pub_scf=rospy.Publisher("/scene/floats",numpy_msg(Floats),queue_size=1)
pub_mfof=rospy.Publisher("/model/found/floats",numpy_msg(Floats),queue_size=1)
pub_mnpf=rospy.Publisher("/model/cannotpick/floats",numpy_msg(Floats),queue_size=1)
pub_mpif=rospy.Publisher("/model/picking/floats",numpy_msg(Floats),queue_size=1)
pub_Y1=rospy.Publisher('/solver/Y1',Bool,queue_size=1)    #X1 done
pub_Y2=rospy.Publisher('/solver/Y2',PickingPose,queue_size=1)    #X2 done
pub_msg=rospy.Publisher('/solver/message',OverlayText,queue_size=1)

###Transform
mTc=tflib.toRT(tflib.dict2tf(rospy.get_param('/robot/calib/mTc')))  # arM tip To Camera
#print "mTc=", mTc
bTmLat=np.eye(4).astype(float)  #robot RT when captured
bTm=np.eye(4).astype(float) 

###Globals
scnPn=P0()  #Scene points
mfoPn=P0()  # Model Found points
mnpPn=P0()  # Model Cannot Pick points
mpiPn=P0()  # Model Picking points
is_prepared = False

xmin = float(rospy.get_param('/volume_of_interest/xmin'))
xmax = float(rospy.get_param('/volume_of_interest/xmax'))
ymin = float(rospy.get_param('/volume_of_interest/ymin'))
ymax = float(rospy.get_param('/volume_of_interest/ymax'))
zmin = float(rospy.get_param('/volume_of_interest/zmin'))
zmax = float(rospy.get_param('/volume_of_interest/zmax'))
print "xmin=", xmin, "xmax=", xmax, "ymin=", ymin, "ymax=", ymax, "zmin=", zmin, "zmax=", zmax

sparse_threshold = int(rospy.get_param('/dense_sparse/threshold'))
print "sparse_threshold=", sparse_threshold

try:
  prepare_model(os.environ['ROVI_PATH'] + '/wrs2018/model/Gear.stl')
  rospy.spin()
except KeyboardInterrupt:
  print "Shutting down"
