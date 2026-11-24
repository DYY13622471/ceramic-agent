# Rhino Python: 按"弧度花瓶"方法建模 (画轮廓曲线 -> 旋转成型)
import math
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

layer = "弧度花瓶"
if not rs.IsLayer(layer):
    rs.AddLayer(layer)
rs.CurrentLayer(layer)

# 轮廓点 (半径, y, z): 底部中心(在轴上) -> 瓶底 -> 鼓腹 -> 收肩 -> 长颈 -> 口沿
pts = [
    (0.0, 0.0, 0.0),
    (30.0, 0.0, 0.0),
    (46.0, 0.0, 28.0),
    (55.0, 0.0, 80.0),
    (44.0, 0.0, 135.0),
    (22.0, 0.0, 178.0),
    (24.0, 0.0, 215.0),
]
crv_id = rs.AddInterpCurve(pts)
crv = rs.coercecurve(crv_id)

# RhinoCommon 旋转成型: 绕 Z 轴 0~360度 (学到的"旋转成型工具")
axis = Rhino.Geometry.Line(Rhino.Geometry.Point3d(0, 0, 0), Rhino.Geometry.Point3d(0, 0, 5))
rev = Rhino.Geometry.RevSurface.Create(crv, axis, 0.0, 2.0 * math.pi)
if rev:
    rid = sc.doc.Objects.AddSurface(rev)
    rs.ObjectLayer(rid, layer)
    rs.ObjectColor(rid, (200, 40, 90))
    rs.UnselectAllObjects()
    rs.SelectObject(rid)
rs.ZoomExtents()
__result__ = "OK rev=%s 高约215mm 最大径110mm" % str(rid)
