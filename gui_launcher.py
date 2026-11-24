# -*- coding: utf-8 -*-
"""
gui_launcher.py — 陶瓷自学·B站教程一键学(图形界面版)
=====================================================
一个薄壳 GUI: 粘 B站链接 -> 点"开始学习" -> 调用 learning/bili_learn.py 管道
(下载->本机转字幕->Ollama提炼->去重入库), 实时显示进度。

关键设计: 用子进程调用 bili_learn.py(真实Python3.11跑管道, 避免打包后路径/依赖问题),
本文件只负责窗口 + 转发输出, 因此打包成 exe 体积小、不用处理 hidden-import。

用法:
  源码:  python gui_launcher.py
  打包:  运行 build_exe.bat, 得到 dist/ceramic-agent-gui.exe, 把 exe 放到
          本仓库根目录(与 store/ learning/ 同级)后双击。
"""
import os
import sys
import queue
import threading
import subprocess

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ---- 路径锚点: exe 双击运行时要能找到 store/ learning/ ----
def project_root():
    # 从 exe(或脚本)所在目录往上找, 直到发现 learning\bili_learn.py,
    # 避免放错目录(如 dist\ 下)就找不到管道。最多向上找 6 层。
    start = (os.path.dirname(os.path.abspath(sys.executable))
             if getattr(sys, "frozen", False)
             else os.path.dirname(os.path.abspath(__file__)))
    cur = start
    for _ in range(6):
        if os.path.exists(os.path.join(cur, "learning", "bili_learn.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return start  # 兜底: 实在找不到就用 exe 所在目录

# 默认解释器: 源码运行时用当前解释器; 打包成 exe 后退回 PATH 上的 python
PYTHON_DEFAULT = "" if getattr(sys, "frozen", False) else sys.executable

ROOT = project_root()


def resolve_python():
    if os.path.exists(PYTHON_DEFAULT):
        return PYTHON_DEFAULT
    return "python"


class App:
    def __init__(self, master):
        self.master = master
        master.title("陶瓷自学 · B站教程一键学")
        master.geometry("640x560")
        master.configure(bg="#f5f6f8")

        self.q = queue.Queue()
        self.proc = None
        self.python = tk.StringVar(value=resolve_python())
        self.model = tk.StringVar(value="small")

        # 项目根提示
        tk.Label(master, text="项目根: " + ROOT, bg="#f5f6f8", fg="#666",
                 font=("Microsoft YaHei", 9)).pack(anchor="w", padx=12, pady=(10, 0))

        # 链接输入
        tk.Label(master, text="B站教程链接(每行一条, 可多条批量):",
                 bg="#f5f6f8", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=12, pady=(8, 2))
        self.links = scrolledtext.ScrolledText(master, height=5, font=("Consolas", 10))
        self.links.pack(fill="x", padx=12)

        # 参数行
        bar = tk.Frame(master, bg="#f5f6f8")
        bar.pack(fill="x", padx=12, pady=6)
        tk.Label(bar, text="语音模型:", bg="#f5f6f8",
                 font=("Microsoft YaHei", 9)).pack(side="left")
        ttk.Combobox(bar, textvariable=self.model, values=["base", "small", "medium"],
                     width=8, state="readonly").pack(side="left", padx=4)
        tk.Label(bar, text="  Python:", bg="#f5f6f8", font=("Microsoft YaHei", 9)).pack(side="left", padx=(12, 2))
        ttk.Entry(bar, textvariable=self.python, width=46).pack(side="left")

        # 开始按钮
        self.btn = tk.Button(master, text="开始学习", command=self.start,
                             bg="#2f6fed", fg="white", font=("Microsoft YaHei", 11, "bold"),
                             activebackground="#1f56c0", activeforeground="white",
                             padx=24, pady=6, cursor="hand2")
        self.btn.pack(pady=8)

        # 日志区
        tk.Label(master, text="进度:", bg="#f5f6f8", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=12)
        self.log = scrolledtext.ScrolledText(master, height=14, font=("Consolas", 9),
                                             state="disabled", bg="#0d1117", fg="#d8dee9")
        self.log.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        self.poll()

    # ---- 工具 ----
    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        try:
            while True:
                self.write(self.q.get_nowait())
        except queue.Empty:
            pass
        self.master.after(100, self.poll)

    def start(self):
        links = [ln.strip() for ln in self.links.get("1.0", "end").splitlines() if ln.strip()]
        if not links:
            messagebox.showwarning("提示", "请先粘贴至少一条 B站教程链接")
            return
        self.btn.configure(state="disabled", text="学习中...")
        t = threading.Thread(target=self._run, args=(links,), daemon=True)
        t.start()

    def _run(self, links):
        py = self.python.get().strip() or "python"
        cmd = [py, os.path.join(ROOT, "learning", "bili_learn.py"), "--urls"] + links + ["--model", self.model.get()]
        self.q.put(">>> 命令: " + " ".join(cmd) + "\n")
        try:
            self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace",
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            learned = []
            for line in self.proc.stdout:
                line = line.rstrip()
                if line:
                    self.q.put(line + "\n")
                if "已写入方法库" in line:
                    learned.append(line.split("已写入方法库:")[-1].strip())
            self.proc.wait()
            self.q.put("\n" + "=" * 50 + "\n")
            if learned:
                self.q.put("✅ 本次学到 %d 个方法:\n" % len(learned))
                for m in learned:
                    self.q.put("   · " + m + "\n")
            self.q.put("全部完成。" + (" 学到 %d 个方法" % len(learned) if learned else "") + "\n")
        except Exception as exc:
            self.q.put("[启动失败] %r\n请检查 Python 路径与依赖(yt-dlp/faster-whisper)。\n" % exc)
        finally:
            self.q.put(">>> 结束\n")
            self.master.after(0, lambda: (self.btn.configure(state="normal", text="开始学习")))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
#（注：内容由AI生成）
