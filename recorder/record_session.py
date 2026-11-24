# -*- coding: utf-8 -*-
"""
recorder/record_session.py — 建模操作记录器
用法(Rhino 开着时):
    python record_session.py start
    python record_session.py shot
    python record_session.py end --intent "建一个本样青花瓶"
"""
import os
import sys
import json
import time
import argparse
import base64
from datetime import datetime

from golem_client import GolemClient


STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store")
STORE_DIR = os.path.normpath(STORE_DIR)
SESS_FILE = os.path.join(STORE_DIR, "_active_session.json")


def _read_history(c):
    """★ 修复: 用 golem_client 的稳健提取(两层 result)。"""
    resp = c.command_history()
    return GolemClient.command_history_text(resp)


def _load_session():
    if os.path.exists(SESS_FILE):
        with open(SESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_session(sess):
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(SESS_FILE, "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=2)


def _store_case(sess):
    os.makedirs(STORE_DIR, exist_ok=True)
    name = "case_%s_%s.json" % (sess["session_id"][:8], sess["intent"][:12] or "no_intent")
    path = os.path.join(STORE_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False, indent=2)
    return path


def cmd_start():
    c = GolemClient()
    hist = _read_history(c)
    sess = {
        "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "intent": "",
        "baseline_len": len(hist),
        "baseline_tail": hist[-200:],
        "steps": [],
        "final_screenshot": None,
    }
    _save_session(sess)
    print("开始记录 session=%s 基线长度=%d" % (sess["session_id"], len(hist)))
    return sess


def cmd_shot(comment=""):
    c = GolemClient()
    sess = _load_session()
    if not sess:
        print("尚未 start"); return None

    hist = _read_history(c)
    base_len = sess.get("baseline_len", 0)
    delta = hist[base_len:] if len(hist) >= base_len else hist
    sess["baseline_len"] = len(hist)

    b64 = c.capture(width=1000, height=1200)
    img_path = None
    if b64:
        os.makedirs(STORE_DIR, exist_ok=True)
        img_path = os.path.join(STORE_DIR, "shot_%s_%d.png" % (sess["session_id"], len(sess["steps"])))
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(b64))

    cmds = []
    for line in delta.splitlines():
        line = line.strip()
        if line.startswith("命令:") or line.startswith("Command:"):
            cmds.append(line.split(":", 1)[1].strip())

    step = {
        "t": time.strftime("%H:%M:%S"),
        "comment": comment,
        "commands": cmds,
        "history_delta": delta[-1500:],
        "screenshot": img_path,
    }
    sess["steps"].append(step)
    _save_session(sess)
    print("记录一步: %d 条命令, 截图=%s" % (len(cmds), img_path))
    return step


def cmd_end(intent):
    c = GolemClient()
    sess = _load_session()
    if not sess:
        print("尚未 start"); return None
    sess["intent"] = intent
    sess["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

    b64 = c.capture(width=1000, height=1200)
    if b64:
        os.makedirs(STORE_DIR, exist_ok=True)
        img_path = os.path.join(STORE_DIR, "final_%s.png" % sess["session_id"])
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(b64))
        sess["final_screenshot"] = img_path

    path = _store_case(sess)
    if os.path.exists(SESS_FILE):
        os.remove(SESS_FILE)
    print("记录完成 -> 案例文件: %s" % path)
    print("步骤数: %d, 意图: %s" % (len(sess["steps"]), intent))
    return path


def main():
    ap = argparse.ArgumentParser(description="陶瓷建模操作记录器")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start")
    sub.add_parser("shot")
    end = sub.add_parser("end")
    end.add_argument("--intent", default="")
    args = ap.parse_args()

    if args.cmd == "start":
        cmd_start()
    elif args.cmd == "shot":
        cmd_shot()
    elif args.cmd == "end":
        cmd_end(args.intent)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()