# -*- coding: utf-8 -*-
"""
executor/self_check.py — 建模自检器(闭环迭代的"眼睛")
=====================================================================
自主建模每一步之后:
  1. 截图视口 + 查对象数据(Golem)
  2. 判断模型是否符合要求(实体? 尺寸? 陶瓷工艺?)
  3. 输出检查报告, 供 LLM 决定: 通过 / 需要修改 / 重建
"""
import math


def analyze_object(obj):
    geo = obj.get("geometry", {})
    report = {
        "guid": obj.get("guid"),
        "name": obj.get("name"),
        "is_solid": geo.get("is_solid"),
        "is_valid": geo.get("is_valid"),
        "volume_mm3": geo.get("volume"),
        "bbox": geo.get("bounding_box"),
    }
    checks = []
    if report["is_solid"] is True and report["is_valid"] is True:
        checks.append("实体有效: OK")
    else:
        checks.append("非有效实体: FAIL (需封闭成实体)")
    bb = report["bbox"]
    if bb:
        h = bb["max"][2] - bb["min"][2]
        checks.append("高度 %.1fmm" % h)
    vol = report["volume_mm3"]
    if vol:
        checks.append("体积 %.0f mm³ (%.0f ml)" % (vol, vol / 1000.0))
    report["checks"] = checks
    report["pass"] = (report["is_solid"] is True and report["is_valid"] is True)
    return report


def analyze_vs_target(obj, target):
    """量化自检: 实测 vs 目标(高度/直径/体积ml)的误差百分比。
    target 例: {"height":210.2,"diameter":86,"volume_ml":600,"wall":2.0}
    返回 report 附带 errors 列表与 max_error; max_error<=tol 即合格。
    """
    report = analyze_object(obj)
    errs = []
    bb = report.get("bbox")
    if bb:
        h = bb["max"][2] - bb["min"][2]
        if target.get("height"):
            errs.append(("高度mm", round(h, 1), target["height"],
                         (h - target["height"]) / target["height"]))
        if target.get("diameter"):
            d = max(bb["max"][0] - bb["min"][0], bb["max"][1] - bb["min"][1])
            errs.append(("直径mm", round(d, 1), target["diameter"],
                         (d - target["diameter"]) / target["diameter"]))
    vol = report.get("volume_mm3")
    if vol and target.get("volume_ml"):
        ml = vol / 1000.0
        errs.append(("体积ml", round(ml, 1), target["volume_ml"],
                     (ml - target["volume_ml"]) / target["volume_ml"]))
    report["errors"] = errs
    report["max_error"] = max((abs(e[3]) for e in errs), default=0.0)
    return report


def fetch_and_check(client, guids):
    reports = []
    for g in guids:
        resp = client.call("scene.get_object_info", {"guid": g})
        obj = resp.get("result", {}).get("object") or resp.get("result", {})
        reports.append(analyze_object(obj))
    return reports


if __name__ == "__main__":
    demo = {
        "guid": "abc", "name": "瓶身", "geometry": {
            "is_solid": True, "is_valid": True, "volume": 83064.0,
            "bounding_box": {"min": [-43, -43, 0], "max": [43, 43, 210]}}}
    import json
    print(json.dumps(analyze_object(demo), ensure_ascii=False, indent=2))
