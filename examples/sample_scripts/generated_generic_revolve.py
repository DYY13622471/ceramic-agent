# -*- coding: utf-8 -*-
"""由方案规划器生成的"空心回转体"建模脚本(汾杏式瓶型)。"""
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

M = [(0.0, 33.87857142857143), (5.380533333333334, 33.87857142857143), (12.554577777777778, 21.921428571428574), (23.315644444444445, 12.95357142857143), (40.354000000000006, 7.9714285714285715), (89.67555555555556, 5.978571428571429), (103.12688888888889, 15.942857142857143), (125.54577777777779, 35.871428571428574), (143.4808888888889, 41.85), (174.86733333333333, 37.864285714285714), (201.77, 32.88214285714286)]          # 母线 (z, r) mm
WALL = 2.5

def closed_profile(pts2d, base, top):
    p = [Rhino.Geometry.Point3d(0, 0, base)]
    for z, r in pts2d:
        p.append(Rhino.Geometry.Point3d(r, 0, z))
    p.append(Rhino.Geometry.Point3d(0, 0, top))
    p.append(Rhino.Geometry.Point3d(0, 0, base))
    return rs.AddInterpCurve(p, degree=3)

def rev(crv):
    return rs.AddRevSrf(crv, [(0, 0, 0), (0, 0, 1000)])

def main():
    rs.AddLayer("酒瓶", (30, 60, 150))
    outer_pts = M
    inner_pts = [(max(z, WALL), max(r - WALL, 0.5)) for z, r in M]
    outer = rev(closed_profile(outer_pts, 0.0, outer_pts[-1][0]))
    inner = rev(closed_profile(inner_pts, WALL, inner_pts[-1][0]))
    res = rs.BooleanDifference([outer], [inner], delete_input=True)
    if not res:
        rs.DeleteObject(outer); rs.DeleteObject(inner)
        __result__ = {"error": "布尔差失败"}
        return
    bottle = res[0]
    rs.ObjectLayer(bottle, "酒瓶")
    rs.ObjectName(bottle, "瓶身_标准红酒杯")
    g = sc.doc.Objects.Find(bottle).Geometry
    print("瓶身 is_solid=%s is_valid=%s" % (g.IsSolid, g.IsValid))
    print("空心回转体 壁厚=%.1fmm 高=%.1f 最大径=%.1f" % (WALL, 201.77, 83.7))
    __result__ = {"bottle_guid": str(bottle),
                  "note": "空心回转体 壁厚%.1fmm 高%.1f 最大径%.1f" % (WALL, 201.77, 83.7)}
    import json as _json
    print("__GOLEM_RESULT__" + _json.dumps(__result__))
    sc.doc.Views.Redraw()

try:
    main()
except Exception as e:
    import traceback; traceback.print_exc()
    __result__ = {"error": str(e)}
