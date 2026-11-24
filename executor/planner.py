# -*- coding: utf-8 -*-
"""
executor/planner.py — 建模方案规划器
输入: 用户目标(建什么器型 + 尺寸/工艺要求)
输出: 建模方案(方法id + 步骤 + 参数 + 陶瓷工艺检查)
"""
import re
from learning.method_library import search, PROCESS_BASELINE


def parse_target(target):
    t = target or ""
    info = {"raw": t, "category": None, "params": {}}

    if any(k in t for k in ("瓶", "酒瓶", "花瓶", "bl", "Bottle")):
        info["category"] = "回转体/瓶子"
    elif any(k in t for k in ("杯", "茶杯", "直", "cup", "Cup")):
        info["category"] = "回转体/杯子"
    elif any(k in t for k in ("碗", "盘", "碟")):
        info["category"] = "回转体/碗盘"

    m = re.search(r"(?:高|高度)\s*(\d+(?:\.\d+)?)", t)
    if m: info["params"]["height"] = float(m.group(1))
    m = re.search(r"(?:最大|直径|径|外径)\s*(\d+(?:\.\d+)?)", t)
    if m: info["params"]["diameter"] = float(m.group(1))
    m = re.search(r"(?:口径)\s*(\d+(?:\.\d+)?)", t)
    if m: info["params"]["mouth"] = float(m.group(1))
    m = re.search(r"(?:满口|容量)\s*(\d+)\s*(ml|毫升|cc)", t)
    if m: info["params"]["fill_ml"] = float(m.group(1))
    m = re.search(r"(?:壁厚)\s*(\d+(?:\.\d+)?)", t)
    if m: info["params"]["wall"] = float(m.group(1))
    return info


def plan(target):
    info = parse_target(target)
    category = info["category"]
    methods = search(category=category) if category else []
    if methods:
        method = methods[0]
        params = dict(method.get("params", {}))
        params.update(info["params"])
        plan_doc = {
            "method_id": method["method_id"],
            "name": method["name"],
            "category": category,
            "params": params,
            "steps": method.get("steps", []),
            # ★ 修复: 从方法库读取 learned, 而不是写死 False
            "learned": bool(method.get("learned", False)),
            "notes": method.get("notes", ""),
        }
    else:
        plan_doc = {
            "method_id": "generic_revolve",
            "name": "通用回转体(待从案例学习)",
            "category": category or "回转体/其他",
            "params": info["params"],
            "steps": ["提取母线", "旋转成曲面", "加壁厚挖空", "工艺检查"],
            "learned": False,
            "notes": "方法库暂无此器型方法, 建议先记录一次该类建模以学习",
        }
    plan_doc["process_baseline"] = PROCESS_BASELINE
    return plan_doc


if __name__ == "__main__":
    import json
    for tgt in ["建一个青花瓷瓶 满口600ml 壁厚2",
                "直筒茶杯 高90 外径90",
                "建个盘子"]:
        print("目标:", tgt)
        print(json.dumps(plan(tgt), ensure_ascii=False, indent=2))