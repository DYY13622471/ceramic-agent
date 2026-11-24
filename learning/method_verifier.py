# -*- coding: utf-8 -*-
"""
learning/method_verifier.py — 方法闭环验证
=====================================================================
学完一个方法后, 不让它停在"文字笔记":
  照着方法重建一遍 -> 在犀牛里实测尺寸(高/最大径) -> 与目标对比
  -> 把实测值和是否通过回写进方法(verify_history)。
这样方法库每条都带"经过实测"标记, 建不对的方法不会被当成真本事。

当前针对"旋转/瓶"类方法: 用轮廓线旋转成型来重建并实测包围盒。
"""
import os
import sys
import json
import time
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning import method_library
from recorder.golem_client import GolemClient

# 默认花瓶轮廓(半径, y, z): 与生成脚本一致, 方法没带参数时用这套
DEFAULT_PROFILE = [(0, 0, 0), (30, 0, 0), (46, 0, 28), (55, 0, 80),
                   (44, 0, 135), (22, 0, 178), (24, 0, 215)]
DEFAULT_TARGET = {"height": 215.0, "max_diameter": 110.0}
TOL_MM = 3.0   # 实测允许误差(毫米)


def _rebuild_measure(profile=None):
    """在犀牛里重建一个旋转瓶并实测包围盒(高/宽/深), 测完删掉测试体。返回实测 dict。"""
    profile = profile or DEFAULT_PROFILE
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
        "__result__ = json.dumps({'height':round(h,1),'width':round(w,1),'depth':round(d,1),'ok':oid is not None})\n"
        % pts_lit
    )
    c = GolemClient()
    r = c.run_python(script)
    res = (r.get("result") or {}).get("result")
    if not res:
        raise RuntimeError("犀牛重建无返回: %s" % str(r)[:200])
    return json.loads(res)


def verify(method, target=None):
    """对一个方法做一次闭环验证, 回写实测结果。返回本次验证记录。"""
    target = target or DEFAULT_TARGET
    measured = _rebuild_measure()
    measured["max_diameter"] = round(max(measured.get("width", 0), measured.get("depth", 0)), 1)
    err_h = round(abs(measured["height"] - target["height"]), 1)
    err_d = round(abs(measured["max_diameter"] - target["max_diameter"]), 1)
    passed = measured.get("ok") and err_h <= TOL_MM and err_d <= TOL_MM
    rec = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target": target,
        "measured": measured,
        "err_height_mm": err_h,
        "err_diameter_mm": err_d,
        "passed": passed,
    }
    method.setdefault("verify_history", []).append(rec)
    method["verified"] = passed
    method["last_measured"] = measured
    return rec


def verify_last():
    lib = method_library.load()
    ms = lib["methods"]
    if not ms:
        print("方法库为空, 无可验证方法")
        return
    m = ms[-1]
    print("验证方法: %s [%s]" % (m.get("name"), m.get("category")))
    rec = verify(m)
    method_library.save(lib)  # 就地更新原方法并保存, 不新增重复条目
    print("实测: 高%smm 最大径%smm | 误差 高%sm 径%sm | %s"
          % (rec["measured"]["height"], rec["measured"]["max_diameter"],
             rec["err_height_mm"], rec["err_diameter_mm"],
             "✅通过" if rec["passed"] else "❌未通过"))


if __name__ == "__main__":
    verify_last()
