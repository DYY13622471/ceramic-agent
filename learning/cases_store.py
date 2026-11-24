# -*- coding: utf-8 -*-
"""
learning/cases_store.py — 建模案例库(云端/豆包侧)
=====================================================================
管理 record_session 生成的案例(JSON), 提供:
  - 案例读写/列举/检索
  - 命令使用统计(提炼常用建模手法)
  - 按意图分组的"方法模式"初筛(供 LLM 深入提炼)

学习层的核心职责: 不是存死脚本, 而是从案例中提取"这类器型怎么做"的规律。
规律提炼由 AI 读取案例后完成; 本模块只提供干净的结构化数据。
"""
import os
import json
import glob
from collections import Counter, defaultdict

STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store")
STORE_DIR = os.path.normpath(STORE_DIR)


def list_case_paths():
    os.makedirs(STORE_DIR, exist_ok=True)
    # 旧位置(平铺在 store 根) + 新位置(按天归档 store/cases/<YYYYMMDD>/), 两者都扫, 兼容历史数据
    paths = glob.glob(os.path.join(STORE_DIR, "case_*.json"))
    paths += glob.glob(os.path.join(STORE_DIR, "cases", "*", "case_*.json"))
    return sorted(paths)


def load_case(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_cases():
    return [load_case(p) for p in list_case_paths()]


def all_commands():
    counter = Counter()
    for c in list_cases():
        for step in c.get("steps", []):
            for cmd in step.get("commands", []):
                counter[cmd] += 1
    return counter


def method_patterns():
    groups = defaultdict(list)
    for c in list_cases():
        intent = (c.get("intent") or "未分类").strip()
        flow = []
        for step in c.get("steps", []):
            flow.extend(step.get("commands", []))
        groups[intent].append({"session_id": c["session_id"], "flow": flow,
                               "shots": len(c.get("steps", []))})
    patterns = {}
    for intent, items in groups.items():
        freq = Counter()
        for it in items:
            for cmd in it["flow"]:
                freq[cmd] += 1
        patterns[intent] = {
            "case_count": len(items),
            "top_commands": freq.most_common(15),
            "cases": items,
        }
    return patterns


def summary():
    cases = list_cases()
    cmds = all_commands()
    return {
        "case_count": len(cases),
        "top_commands": cmds.most_common(20),
        "intent_patterns": {k: {"case_count": v["case_count"]}
                            for k, v in method_patterns().items()},
    }


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
