# -*- coding: utf-8 -*-
"""
learning/memory_corrector.py — 记忆 + 自动修正(越建越准)
=====================================================================
把"上次哪里建歪了"存成记忆(每条方法的修正系数), 下次建模自动套用,
建完实测后再按误差更新系数, 逐轮收敛:

  记忆 correction = {height_scale, radius_scale, trials}
  建: 轮廓 z*height_scale, 半径*radius_scale -> 犀牛实测高/最大径
  比: 实测 vs 目标(高/最大径)
  改: height_scale *= 目标高/实测高; radius_scale *= 目标径/实测径
  存: 写回方法的 correction 与 converge_history
"""
import os
import sys
import json
import time
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning import method_library
from recorder.golem_client import GolemClient

DEFAULT_PROFILE = [(0, 0, 0), (30, 0, 0), (46, 0, 28), (55, 0, 80),
                   (44, 0, 135), (22, 0, 178), (24, 0, 215)]
DEFAULT_TARGET = {"height": 215.0, "max_diameter": 110.0}
ITERS = 3   # 自动修正轮数(演示收敛)


def _scale_profile(profile, height_scale, radius_scale):
    """按修正系数缩放轮廓: z 方向调高度, x(半径)方向调直径。"""
    return [(r * radius_scale, y, z * height_scale) for (r, y, z) in profile]


def _rebuild_measure(profile):
    """犀牛里旋转成型并实测包围盒, 测完删测试体。返回实测 dict。"""
    pts_lit = ",\n".join("(%s)" % ",".join(str(v) for v in p) for p in profile)
    script = (
        "import rhinoscriptsyntax as rs, scriptcontext as sc, Rhino, math, json\n"
        "pts = [%s]\n"
        "crv = rs.AddInterpCurve(pts)\n"
        "g = rs.coercecurve(crv)\n"
        "axis = Rhino.Geometry.Line(Rhino.Geometry.Point3d(0,0,0), Rhino.Geometry.Point3d(0,0,5))\n"
        "rev = Rhino.Geometry.RevSurface.Create(g, axis, 0.0, 2.0*math.pi)\n"
        "oid = sc.doc.Objects.AddSurface(rev)\n"
        "bb = rs.BoundingBox(oid)\n"
        "xs=[p.X for p in bb]; ys=[p.Y for p in bb]; zs=[p.Z for p in bb]\n"
        "h=max(zs)-min(zs); w=max(xs)-min(xs); d=max(ys)-min(ys)\n"
        "rs.DeleteObject(oid)\n"
        "if crv: rs.DeleteObject(crv)\n"
        "__result__ = json.dumps({'height':round(h,2),'width':round(w,2),'depth':round(d,2)})\n"
        % pts_lit
    )
    r = GolemClient().run_python(script)
    res = (r.get("result") or {}).get("result")
    if not res:
        raise RuntimeError("犀牛重建无返回: %s" % str(r)[:200])
    m = json.loads(res)
    m["max_diameter"] = round(max(m["width"], m["depth"]), 2)
    return m


def correct_last(iters=ITERS):
    """对最近一条方法做记忆修正: 多轮建-测-改, 演示误差收敛。"""
    lib = method_library.load()
    ms = lib["methods"]
    if not ms:
        print("方法库为空")
        return
    m = ms[-1]
    tgt = DEFAULT_TARGET
    corr = m.setdefault("correction", {"height_scale": 1.0, "radius_scale": 1.0, "trials": 0})
    hist = m.setdefault("converge_history", [])
    print("记忆修正方法: %s" % m.get("name"))
    print("初始记忆系数: 高x%.4f 径x%.4f" % (corr["height_scale"], corr["radius_scale"]))

    for i in range(iters):
        prof = _scale_profile(DEFAULT_PROFILE, corr["height_scale"], corr["radius_scale"])
        meas = _rebuild_measure(prof)
        eh = round(abs(meas["height"] - tgt["height"]), 2)
        ed = round(abs(meas["max_diameter"] - tgt["max_diameter"]), 2)
        rec = {"time": time.strftime("%H:%M:%S"), "round": i + 1,
               "height_scale": round(corr["height_scale"], 4),
               "radius_scale": round(corr["radius_scale"], 4),
               "measured": meas, "err_h": eh, "err_d": ed}
        hist.append(rec)
        print("  第%d轮: 实测高%sm 径%sm | 误差 高%sm 径%sm"
              % (i + 1, meas["height"], meas["max_diameter"], eh, ed))
        # 按误差更新记忆系数(线性几何, 乘性修正, 下一轮即收敛)
        corr["height_scale"] *= tgt["height"] / meas["height"]
        corr["radius_scale"] *= tgt["max_diameter"] / meas["max_diameter"]
        corr["trials"] += 1

    method_library.save(lib)
    print("已存记忆: 高x%.4f 径x%.4f (下次建同类瓶自动套用)"
          % (corr["height_scale"], corr["radius_scale"]))


if __name__ == "__main__":
    correct_last()
