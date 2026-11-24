# -*- coding: utf-8 -*-
"""
learning/bili_learn.py — B站链接 -> 自学入库(一键管道, 全本机闭环)
=====================================================================
输入一条 B站教程链接(或本地音视频文件), 自动完成:
  ① yt-dlp 下载音轨        (本机, 无需助手/云端)
  ② faster-whisper 离线转字幕 -> store/transcripts/<BV号>.txt   (本机离线语音识别)
  ③ Ollama 提炼方法          (本机)
  ④ 语义去重 + 写入方法库    (本机, 带溯源 source=bilibili:BV号)

用法(Python 3.11):
  python bili_learn.py --urls "https://www.bilibili.com/video/BVxxx"
  python bili_learn.py --links-file store/tutorial_links.txt
  python bili_learn.py --local "D:\\xxx.mp4"    # 本机已有音视频, 跳过下载
  python bili_learn.py --urls "..." --model small --no-dedupe

使用边界: 远程下载仅用于处理你本人拥有权利或已获授权的素材。
第三方视频的逐字稿与音轨属他人版权内容, 请勿随仓库分发;
本仓库不包含任何第三方转录稿与音轨。请遵守对应平台的服务条款。
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning import method_library
from learning.llm_client import OllamaClient
from learning.learner import _semantic_dup
from learning.tutorial_learner import (_bv_from_url, distill_method, TRANSCRIPTS_DIR)

STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store"))
WORK_DIR = os.path.join(STORE_DIR, "tmp_download")

# faster-whisper 模型(首次自动下载)。small 中文足够且快; 要更准用 medium(更慢/更大)
DEFAULT_MODEL = "small"


def download_audio(url, workdir=WORK_DIR):
    """① yt-dlp 下载视频音轨, 返回本地音频路径。失败返回 None 并给出原因。"""
    import yt_dlp
    os.makedirs(workdir, exist_ok=True)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            req = info.get("requested_downloads") or []
            p = req[0].get("filepath") if req else info.get("_filename")
            if not p:
                # 兜底: 找 workdir 下最新音频文件
                cands = sorted((os.path.join(workdir, f) for f in os.listdir(workdir)),
                               key=os.path.getmtime, reverse=True)
                p = cands[0] if cands else None
            return p
    except Exception as exc:
        print("  [下载失败] %r" % exc)
        print("  提示: B站部分视频需登录/风控。可改用 --local 直接转本机已有文件。")
        return None


def transcribe_local(audio_path, model_name=DEFAULT_MODEL, language="zh"):
    """② faster-whisper 离线转字幕, 写入 store/transcripts/<BV>.txt, 返回字幕文本。"""
    # 国内网络 HuggingFace 常连不上, 默认走 hf-mirror 镜像下载模型
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    # 镜像不支持 xet 加速协议(会报401), 强制普通 HTTP 下载
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    # 模型缓存放到项目内 store/models(既可写, 也让一键程序自包含, 不依赖用户 .cache)
    os.environ.setdefault("HF_HOME", os.path.join(STORE_DIR, "models", "hf_cache"))
    from faster_whisper import WhisperModel
    bv = _bv_from_url(audio_path) or os.path.splitext(os.path.basename(audio_path))[0]
    print("  [转字幕] 加载模型 %s (首次会自动下载)... " % model_name, flush=True)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, language=language, vad_filter=True)
    lines = []
    for seg in segments:
        lines.append(seg.text.strip())
    text = "\n".join(l for l in lines if l)
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    out = os.path.join(TRANSCRIPTS_DIR, bv + ".txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print("  [转字幕] 完成: %s (%s 字符)" % (out, len(text)))
    return out


def learn_one(url, client, dedupe, model):
    """对一条来源(URL 或本地文件)完整执行 ①②③④。"""
    print("\n== %s ==" % url)
    if url.lower().startswith(("http://", "https://")):
        audio = download_audio(url)
        if not audio:
            return 0
    else:  # 本地音视频文件
        audio = url
    transcript_file = transcribe_local(audio, model)
    with open(transcript_file, "r", encoding="utf-8") as f:
        transcript = f.read()
    if len(transcript) < 50:
        print("  [逐字稿过短] 可能无有效语音, 跳过")
        return 0
    method = distill_method(url, transcript, client)
    if not method:
        return 0
    if dedupe:
        dup, sim = _semantic_dup(method)
        if dup:
            print("  [跳过] 与既有方法[%s]语义高度相似(%.2f)" % (dup.get("name"), sim))
            return 0
    method_library.add_method(method)
    print("  -> 已写入方法库: %s [%s] (来源 %s)"
          % (method["name"], method["category"], method["source"]))
    return 1


def main():
    ap = argparse.ArgumentParser(description="B站链接->自学入库 一键管道")
    ap.add_argument("--urls", nargs="*", help="B站教程链接(或本地音视频路径)")
    ap.add_argument("--links-file", default=os.path.join(STORE_DIR, "tutorial_links.txt"))
    ap.add_argument("--local", help="转本机已有音视频文件(跳过下载)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper 模型: base/small/medium")
    ap.add_argument("--no-dedupe", action="store_true")
    a = ap.parse_args()

    items = list(a.urls or [])
    if a.local:
        items.append(a.local)
    if a.links_file and os.path.exists(a.links_file):
        with open(a.links_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    items.append(line.split()[0])
    if not items:
        print("没有输入。用 --urls/--local/--links-file 提供链接或本地文件。")
        return
    client = OllamaClient()
    added = 0
    for it in items:
        added += learn_one(it, client, dedupe=not a.no_dedupe, model=a.model)
    print("\n完成: 共学习 %d 条, 新增方法 %d 个。" % (len(items), added))


if __name__ == "__main__":
    main()
