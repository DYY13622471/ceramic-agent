# -*- coding: utf-8 -*-
"""
main.py — 陶瓷建模学习智能体 入口
=====================================================================
三层能力, 对应三个子命令:
  record ...   ① 记录层   start/shot/end   -> 记录你的建模操作, 存案例
  learn        ② 学习层   读案例, 提炼建模方法 -> 沉淀方法库
  model ...    ③ 自主建模  给目标 -> 查方法库生成 Rhino 脚本(本地执行)

架构: 不是固定回放操作, 而是"记录案例 -> AI提炼方法 -> 自主建模"的学习型智能体。
Windows/Rhino 侧运行 record 与生成的模型脚本(经 Golem 连 Rhino 127.0.0.1:9876)。
"""
import os
import sys
import json
import re
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from learning import cases_store
from learning import method_library
from executor import planner
from executor import exec_plan


def _run_recorder(*args):
    """在本地直接跑 recorder/record_session.py(Rhino 开着时)。"""
    rec = os.path.join(ROOT, "recorder", "record_session.py")
    return subprocess.call([sys.executable, rec] + list(args))


def cmd_record(args):
    rec_args = [args.action]
    if args.intent:
        rec_args += ["--intent", args.intent]
    return _run_recorder(*rec_args)


def cmd_learn(args):
    from learning import learner
    summary = cases_store.summary()
    print("=== 案例库现状 ===")
    print("案例数:", summary["case_count"])
    print("高频命令:", ", ".join(c for c, _ in summary["top_commands"][:15]) or "无")
    for intent, p in summary["intent_patterns"].items():
        print("意图[%s]: %d 个案例" % (intent, p["case_count"]))
    if summary["case_count"] == 0:
        print("\n[提示] 方法库暂无可学习案例。先记录一次建模:")
        print("       python main.py record start")
        print("       然后建模, 隔几段 python main.py record shot")
        print("       完成后 python main.py record end --intent \"器型描述\"")
        return 0
    print("\n=== 用本地模型(AI)提炼方法 ===")
    learner.learn_all()
    return 0


def _parse_target(text):
    """从建模目标文本提取量化尺寸 -> target dict(供自检/修正循环)。"""
    t = {}
    for pat, key in [(r"高(\d+(?:\.\d+)?)", "height"),
                     (r"直径(\d+(?:\.\d+)?)", "diameter"),
                     (r"口径(\d+(?:\.\d+)?)", "mouth"),
                     (r"壁厚(\d+(?:\.\d+)?)", "wall"),
                     (r"满口(\d+(?:\.\d+)?)\s*ml", "volume_ml")]:
        m = re.search(pat, text)
        if m:
            t[key] = float(m.group(1))
    return t


def cmd_model(args):
    plan_doc = planner.plan(args.target)
    print("=== 建模方案 ===")
    print("方法: %s [%s] (learned=%s)" % (plan_doc["name"], plan_doc["category"],
                                          plan_doc["learned"]))
    print("参数:", json.dumps(plan_doc["params"], ensure_ascii=False))
    print("步骤:")
    for i, s in enumerate(plan_doc["steps"], 1):
        print("  %d. %s" % (i, s))
    if not plan_doc["learned"]:
        print("\n[提示] 此器型方法是预置模板(未从你的案例学习)。"
              "记录一次同类建模后, learn 会更新方法库, 建模将更贴合你的手法。")

    if args.auto:
        from executor import refine_loop
        target = _parse_target(args.target)
        print("\n=== 自动修正闭环(本地执行 Golem + 本地AI归因 Ollama) ===")
        print("目标尺寸:", json.dumps(target, ensure_ascii=False) or "(无量化尺寸, 无法自检)")
        report, _, rnd = refine_loop.run_refine(target, plan_doc)
        if report:
            print("\n闭环结束: 第%d轮, 最大误差 %.1f%%" % (rnd, report["max_error"] * 100))
        return 0

    gen_dir = os.path.join(ROOT, "generated")
    path = exec_plan.save_script(plan_doc, gen_dir)
    print("\n已生成 Rhino 脚本: %s" % path)
    print("在 Rhino 打开 ScriptEditor(Python3) 运行此脚本, 或由智能体经 Golem 执行。")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="陶瓷建模学习智能体")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("record")
    r.add_argument("action", choices=["start", "shot", "end"])
    r.add_argument("--intent", default="")

    sub.add_parser("learn")

    m = sub.add_parser("model")
    m.add_argument("target", help="如: 建一个青花瓷瓶 满口600ml 壁厚2 高210")
    m.add_argument("--auto", action="store_true",
                   help="自动修正闭环: 本地执行+量化自检+本地AI归因调参, 直到达标")
    args = ap.parse_args()

    if args.cmd == "record":
        return cmd_record(args)
    if args.cmd == "learn":
        return cmd_learn(args)
    if args.cmd == "model":
        return cmd_model(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
