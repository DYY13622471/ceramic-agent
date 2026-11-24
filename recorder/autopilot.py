# -*- coding: utf-8 -*-
"""
recorder/autopilot.py — 自动记录器(随犀牛启动, 后台持续记录学习)
=====================================================================
犀牛一打开, 由 golem_startup.py 启动本后台守护线程:
  - 每 POLL_SEC 秒轮询命令历史, 有操作就记录并截图
  - 空闲超过 IDLE_SEC 认为一次建模结束 -> 自动存案例(意图自动推断)
  - 之后豆包侧的 learn 会读这些案例, 提炼方法进方法库(学你的手法)

意图: 完全自动推断(本模块做基础规则分类, AI 在 learn 时深入识别器型与手法)。
"""
import os
import sys
import json
import time
import base64
import threading
from datetime import datetime

# 运行在 Rhino 内(Rhino Python3) 时可用 rhinoscriptsyntax
try:
    import rhinoscriptsyntax as rs  # noqa: E402
    IN_RHINO = True
except Exception:
    rs = None
    IN_RHINO = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from golem_client import GolemClient  # noqa: E402

STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store")
STORE_DIR = os.path.normpath(STORE_DIR)

POLL_SEC = 3      # 轮询间隔(秒)
IDLE_SEC = 120    # 空闲多久算一次建模结束(秒)

# 纯视口/管理类命令, 不体现建模手法, 记录时过滤掉(避免案例噪音堆积)
NOISE_COMMANDS = {
    "_Group", "_UngroupAll", "_Scale", "_Align", "_Pause",
    "_Save", "_Hide", "_Show", "_SetDisplayMode", "_Delete",
    "_Open", "_New", "_Export", "_Undo", "_Redo",
}


def _infer_category(cmds):
    """基础规则推断器型类别(完整识别由 AI 在 learn 时做)。"""
    joined = " ".join(cmds).lower()
    if any(k in joined for k in ("revolve", "revsrf", "addrevsrf", "旋转", "瓶")):
        return "回转体/瓶子"
    if any(k in joined for k in ("sweep2", "loft", "放样", "扫掠")):
        return "曲面/扫掠"
    if any(k in joined for k in ("cylinder", "圆柱", "杯", "AddCylinder")):
        return "回转体/杯子"
    if any(k in joined for k in ("bowl", "碗", "plate", "盘", "碟")):
        return "回转体/碗盘"
    return "未分类"


class AutoRecorder(threading.Thread):
    def __init__(self, poll=POLL_SEC, idle=IDLE_SEC, in_rhino=None):
        super().__init__(daemon=True)
        self.poll = poll
        self.idle = idle
        # 独立进程强制 in_rhino=False(经 Golem TCP 轮询, 不碰 rhinoscriptsyntax)
        self.in_rhino = IN_RHINO if in_rhino is None else in_rhino
        self._stop_flag = False
        self._base_len = 0
        self._sess = None
        self._last_activity = time.time()
        self._client = GolemClient()

    def stop(self):
        self._stop_flag = True

    # -- 采集 ------------------------------------------------------------
    def _read_hist(self):
        if self.in_rhino and rs:
            try:
                return rs.CommandHistory() or ""
            except Exception:
                return ""
        # Golem execute_python 响应: result 下再嵌套 result -> 文本在 result.result.text
        r = self._client.command_history()
        res = r.get("result", {})
        inner = res.get("result", {}) or {}
        if isinstance(inner, dict):
            return inner.get("text", "") or ""
        return ""

    def _screenshot(self, tag):
        # 截图按天归档: store/cases/<YYYYMMDD>/<tag>_HHMMSS.png (文件名带时分秒, 同日不同次不覆盖)
        day = datetime.now().strftime("%Y%m%d")
        d = os.path.join(STORE_DIR, "cases", day)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "%s_%s.png" % (tag, datetime.now().strftime("%H%M%S")))
        # 犀牛内: 直接用 RhinoCommon 截图(仅当 in_rhino=True)
        if self.in_rhino:
            try:
                import System
                import Rhino
                view = Rhino.RhinoDoc.ActiveDoc.Views.ActiveView
                bmp = view.CaptureToBitmap(view.ActiveViewport.Size)
                bmp.Save(p, System.Drawing.Imaging.ImageFormat.Png)
                return p
            except Exception as exc:
                print("GOLEM-AUTO: 截图失败: %r" % exc)
                return None
        # 独立进程: 经 Golem 截图
        try:
            b64 = self._client.capture(width=1000, height=1100)
        except Exception:
            b64 = None
        if not b64:
            return None
        with open(p, "wb") as f:
            f.write(base64.b64decode(b64))
        return p

    def _current_view(self):
        """取当前活动视口名(视图, 如 Front/Perspective/Top), 失败返回 None。"""
        try:
            if self.in_rhino and rs:
                return rs.CurrentView() or None
            r = self._client.run_python(
                "import rhinoscriptsyntax as rs\n"
                "__result__ = rs.CurrentView() or ''")
            res = r.get("result", {}) or {}
            inner = res.get("result")
            if isinstance(inner, str) and inner.strip():
                return inner
            return None
        except Exception:
            return None

    def _new_session(self):
        return {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "intent": "",
            "category": "",
            "auto_recorded": True,
            "steps": [],
            "final_screenshot": None,
        }

    # -- 主循环 ----------------------------------------------------------
    def run(self):
        print("GOLEM-AUTO: 自动记录器已启动, 等待连接犀牛Golem(127.0.0.1:9876)...")
        while not self._stop_flag:
            try:
                hist = self._read_hist()
            except Exception as exc:
                # 犀牛未启动 / Golem 未就绪 -> 等待重连, 不退出
                print("GOLEM-AUTO: 未连上犀牛Golem(%s), 等待犀牛启动后自动连接..." % exc)
                time.sleep(self.poll)
                continue
            if self._base_len == 0:
                # 首次连上: 建立历史基线
                self._base_len = len(hist)
                print("GOLEM-AUTO: 已连接犀牛Golem, 开始自动记录 (轮询%ds, 空闲%d秒切分)" % (self.poll, self.idle))
                time.sleep(self.poll)
                continue
            if len(hist) >= self._base_len:
                delta = hist[self._base_len:]
            else:
                delta = hist
            self._base_len = len(hist)

            # 只提取真正的建模命令(指令:/Command:), 过滤 Golem 连接日志 + 视口管理噪音
            raw_lines = [l.strip() for l in delta.splitlines()
                         if l.strip().startswith(("指令:", "Command:"))]
            cmd_lines = [l for l in raw_lines
                         if l.split(":", 1)[1].strip().lstrip("'").strip()
                         not in NOISE_COMMANDS]
            if cmd_lines:
                if self._sess is None:
                    self._sess = self._new_session()
                img = self._screenshot("shot")
                self._sess["steps"].append({
                    "t": time.strftime("%H:%M:%S"),
                    "commands": [l.split(":", 1)[1].strip() for l in cmd_lines],
                    "history_delta": "\n".join(cmd_lines)[-1200:],
                    "screenshot": img,
                    "viewport": self._current_view(),   # 该步所在的活动视图
                })
                self._last_activity = time.time()
            elif self._sess is not None and (time.time() - self._last_activity) > self.idle:
                self._finalize(self._sess)
                self._sess = None
            time.sleep(self.poll)

    def _finalize(self, sess):
        try:
            sess["final_screenshot"] = self._screenshot("final")
            sess["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
            allcmds = [c for s in sess["steps"] for c in s["commands"]]
            sess["category"] = _infer_category(allcmds)
            os.makedirs(STORE_DIR, exist_ok=True)
            # 按天归档到 store/cases/<YYYYMMDD>/; 文件名用完整 session_id(日期_时分秒),
            # 同一天多次建模各存各的, 不再互相覆盖
            day = sess["session_id"][:8]
            d = os.path.join(STORE_DIR, "cases", day)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, "case_%s_auto.json" % sess["session_id"])
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sess, f, ensure_ascii=False, indent=2)
            print("GOLEM-AUTO: 一次建模已记录 -> %s (%d步, %s)"
                  % (path, len(sess["steps"]), sess["category"]))
        except Exception as exc:
            print("GOLEM-AUTO: 存案例失败: %r" % exc)


_recorder = None


def start_autopilot(poll=POLL_SEC, idle=IDLE_SEC, in_rhino=None):
    """启动后台自动记录器(幂等)。"""
    global _recorder
    if _recorder and _recorder.is_alive():
        print("GOLEM-AUTO: 自动记录器已在运行")
        return _recorder
    _recorder = AutoRecorder(poll, idle, in_rhino)
    _recorder.start()
    return _recorder


def stop_autopilot():
    global _recorder
    if _recorder:
        _recorder.stop()
        _recorder = None
        print("GOLEM-AUTO: 自动记录器已停止")


if __name__ == "__main__":
    # 独立进程运行(经 Golem 连 Rhino, 强制 in_rhino=False)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "stop"])
    a = ap.parse_args()
    if a.action == "run":
        r = start_autopilot(in_rhino=False)
        try:
            while r.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            stop_autopilot()
    else:
        stop_autopilot()
