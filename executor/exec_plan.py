# -*- coding: utf-8 -*-
"""
executor/exec_plan.py — 方案执行脚本生成器
把 planner 的建模方案转成一段可在 Rhino(ScriptEditor, Python3) 运行的脚本。
"""
import os


def _default_bottle_profile(H, R, mouth_r):
    """未提供母线时, 按本样式瓶型比例生成母线点 (z, r) 列表。"""
    return [
        (0.0, R * 0.72),
        (H * 0.15, R * 0.95),
        (H * 0.42, R),
        (H * 0.62, R * 0.88),
        (H * 0.74, R * 0.62),
        (H * 0.80, R * 0.42),
        (H * 0.86, mouth_r * 1.25),
        (H * 0.92, mouth_r * 1.05),
        (H, mouth_r),
    ]


_REVOLVE_TPL = r'''# -*- coding: utf-8 -*-
"""由方案规划器生成: 空心回转体 建模脚本(瓶型式)。"""
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

M = [@@PTS@@]          # 母线 (z, r) mm
WALL = @@WALL@@

def closed_profile(pts2d, base, top):
    p = [Rhino.Geometry.Point3d(0, 0, base)]
    for z, r in pts2d:
        p.append(Rhino.Geometry.Point3d(r, 0, z))
    p.append(Rhino.Geometry.Point3d(0, 0, top))
    p.append(Rhino.Geometry.Point3d(0, 0, base))
    crv = rs.AddInterpCurve(p, degree=3)
    if not crv:
        crv = rs.AddInterpCurve(p, degree=1)
    return crv

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
        import json as _json
        print("__GOLEM_RESULT__" + _json.dumps(__result__))
        return
    bottle = res[0]
    rs.ObjectLayer(bottle, "酒瓶")
    rs.ObjectName(bottle, "瓶身_@@NAME@@")
    g = sc.doc.Objects.Find(bottle).Geometry
    print("瓶身 is_solid=%s is_valid=%s" % (g.IsSolid, g.IsValid))
    print("空心回转体 壁厚=%.1fmm 高%.1f 最大径=%.1f" % (WALL, @@H@@, @@D@@))
    __result__ = {"bottle_guid": str(bottle),
                  "note": "空心回转体 壁厚%.1fmm 高%.1f 最大径%.1f" % (WALL, @@H@@, @@D@@)}
    import json as _json
    print("__GOLEM_RESULT__" + _json.dumps(__result__))
    sc.doc.Views.Redraw()

try:
    main()
except Exception as e:
    import traceback; traceback.print_exc()
    __result__ = {"error": str(e)}
    import json as _json
    print("__GOLEM_RESULT__" + _json.dumps(__result__))
'''


_CUP_TPL = r'''# -*- coding: utf-8 -*-
"""直筒茶杯(空心)建模脚本。"""
import rhinoscriptsyntax as rs

H = @@H@@
outer_r = @@OUTER_R@@
inner_r = @@INNER_R@@
WALL = @@WALL@@
INNER_H = @@INNER_H@@

def main():
    rs.AddLayer("茶杯", (150, 90, 60))
    outer = rs.AddCylinder((0, 0, 0), H, outer_r, cap=True)
    inner = rs.AddCylinder((0, 0, WALL), INNER_H, inner_r, cap=True)
    cup = rs.BooleanDifference([outer], [inner], delete_input=True)
    if cup:
        rs.ObjectLayer(cup[0], "茶杯")
        rs.ObjectName(cup[0], "直筒茶杯")
        print("茶杯 is_solid OK, 壁厚=%.2fmm" % WALL)
        __result__ = {"cup_guid": str(cup[0]), "note": "壁厚%.2fmm" % WALL}
        import json as _json
        print("__GOLEM_RESULT__" + _json.dumps(__result__))
    else:
        __result__ = {"error": "布尔差失败"}
        import json as _json
        print("__GOLEM_RESULT__" + _json.dumps(__result__))

try:
    main()
except Exception as e:
    import traceback; traceback.print_exc()
    __result__ = {"error": str(e)}
    import json as _json
    print("__GOLEM_RESULT__" + _json.dumps(__result__))
'''


def _get_wall(p, default):
    """兼容 wall / wall_mm 两种 key。"""
    return float(p.get("wall", p.get("wall_mm", default)))


def build_revolve_script(plan):
    p = plan["params"]
    H = float(p.get("height", p.get("H", 212.0)))
    D = float(p.get("diameter", p.get("outer_d", 86.0)))
    mouth = float(p.get("mouth", D * 0.37))
    wall = _get_wall(p, 2.0)
    profile = p.get("profile_pts")
    if profile:
        base_z = profile[0][0]
        top_z = profile[-1][0]
        span = (top_z - base_z) or 1.0
        max_r = max(r for _z, r in profile) or 1.0
        target_r = D / 2.0
        profile = [((z - base_z) / span * H, r / max_r * target_r)
                   for z, r in profile]
    else:
        profile = _default_bottle_profile(H, D / 2.0, mouth / 2.0)
    m_pts = ", ".join("(%s, %s)" % (z, r) for z, r in profile)
    name = plan["name"].split("(")[0].strip()

    code = (_REVOLVE_TPL
            .replace("@@PTS@@", m_pts)
            .replace("@@WALL@@", str(wall))
            .replace("@@NAME@@", name)
            .replace("@@H@@", str(H))
            .replace("@@D@@", str(D)))
    return code


def build_cup_script(plan):
    p = plan["params"]
    wall = _get_wall(p, 2.5)
    H = float(p.get("height", 90))
    H = max(H, wall + 1.0)  # ★ 防止杯高 <= 壁厚
    outer_d = float(p.get("outer_d", p.get("diameter", 90)))
    outer_r = outer_d / 2.0
    inner_r = max(outer_r - wall, 0.5)  # ★ 防止内半径 <= 0
    inner_h = max(H - wall, 0.5)
    code = (_CUP_TPL
            .replace("@@H@@", str(H))
            .replace("@@OUTER_R@@", str(outer_r))
            .replace("@@INNER_R@@", str(inner_r))
            .replace("@@WALL@@", str(wall))
            .replace("@@INNER_H@@", str(inner_h)))
    return code


def plan_to_script(plan):
    mid = plan["method_id"]
    if mid in ("revolve_bottle", "generic_revolve") or str(mid).startswith("learned_"):
        return build_revolve_script(plan)
    if mid == "revolve_cup":
        return build_cup_script(plan)
    return ("# 方法库暂无此器型生成模板: %s.\n"
            "__result__ = {'error': '未知方法 %s'}" % (mid, mid))


def save_script(plan, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "generated_%s.py" % plan["method_id"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(plan_to_script(plan))
    return path


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from executor.planner import plan
    for tgt in ["建一个青花瓷瓶 满口600ml 壁厚2 高210",
                "直筒茶杯 高90 外径90"]:
        p = plan(tgt)
        print("方案:", p["name"])
        script = plan_to_script(p)
        print("脚本行数:", script.count("\n"))
        out = save_script(p, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generated"))
        print("已生成:", out)