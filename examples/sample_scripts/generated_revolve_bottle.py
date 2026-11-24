# -*- coding: utf-8 -*-
"""由方案规划器生成的"空心回转体"建模脚本(汾杏式瓶型)。"""
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

M = [(0, 32.58), (10.5, 38.88), (27.3, 43.09), (50.4, 39.93), (75.7, 35.73), (100.9, 30.48), (126.1, 25.22), (151.3, 19.97), (172.3, 15.76), (187.1, 12.61), (199.7, 10.09), (210.2, 9.46)]          # 母线 (z, r) mm
WALL = 2.0

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
    rs.ObjectName(bottle, "瓶身_汾杏青花瓷瓶")
    g = sc.doc.Objects.Find(bottle).Geometry
    print("瓶身 is_solid=%s is_valid=%s" % (g.IsSolid, g.IsValid))
    print("空心回转体 壁厚=%.1fmm 高=%.1f 最大径=%.1f" % (WALL, 210.2, 86.0))
    __result__ = {"bottle_guid": str(bottle),
                  "note": "空心回转体 壁厚%.1fmm 高%.1f 最大径%.1f" % (WALL, 210.2, 86.0)}
    sc.doc.Views.Redraw()

try:
    main()
except Exception as e:
    import traceback; traceback.print_exc()
    __result__ = {"error": str(e)}
