# -*- coding: utf-8 -*-
"""
learning/tutorial_learner.py — 从 B站 Rhino 教程自学升级(第3个学习源)
=====================================================================
在第1个学习源(你的建模案例)之外, 新增"从 B站教程自学":
  B站教程链接 -> 逐字稿/字幕 -> 本地 Ollama 提炼方法 -> 写入方法库(带溯源 + 语义去重)

转写来源(两种):
  1. 已在 store/transcripts/<bvid>.txt 的逐字稿(可由 doubao-video-extract 链路生成, 或你直接放入)
  2. 尚未转写的链接: 提示先用视频转写链路生成逐字稿后放入 transcripts 目录

提炼出的方法带溯源(满足"证据可溯"): source=bilibili:BV号 + provenance{url, bvid}。
语义去重复用 method_library 的向量技能库, 与案例学习共用同一套去重。

用法:
  python -m learning.tutorial_learner --urls "https://www.bilibili.com/video/BVxxx" "https://..."
  python -m learning.tutorial_learner --links-file store/tutorial_links.txt
"""
import os
import sys
import re
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning import method_library
from learning.llm_client import OllamaClient
from learning.learner import _extract_json, _semantic_dup

STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store"))
TRANSCRIPTS_DIR = os.path.join(STORE_DIR, "transcripts")
DEFAULT_LINKS_FILE = os.path.join(STORE_DIR, "tutorial_links.txt")

SYSTEM = (
    "你是资深陶瓷产品三维建模工程师，精通 Rhino8。下面是一段 B站 Rhino 建模教程的"
    "逐字稿/字幕。请提炼出'这类器型怎么建模'的可复用方法，包括建模步骤、关键参数"
    "和工艺要点。只输出严格 JSON，不要多余文字。"
)


def _bv_from_url(url):
    m = re.search(r"[bB][vV][0-9A-Za-z]+", url or "")
    return m.group(0) if m else None


def _load_links(urls, links_file):
    links = list(urls or [])
    if links_file and os.path.exists(links_file):
        with open(links_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    links.append(line.split()[0])
    return links


def _transcript_path(url):
    bv = _bv_from_url(url)
    if not bv:
        return None
    for ext in (".txt", ".md"):
        p = os.path.join(TRANSCRIPTS_DIR, bv + ext)
        if os.path.exists(p):
            return p
    return None


def build_prompt(url, transcript):
    bv = _bv_from_url(url) or "未知"
    return (
        "以下是一段 B站 Rhino 建模教程的逐字稿(来源 bilibili:%s)。\n"
        "请提炼方法，输出严格 JSON(不要多余文字)，格式：\n"
        '{"category":"器型类别","name":"简短方法名",'
        '"params":{"关键参数":"数值或描述"},'
        '"steps":["步骤1","步骤2",...],"notes":"工艺要点"}\n\n'
        "逐字稿:\n%s\n" % (bv, transcript[-12000:])
    )


def distill_method(url, transcript, client):
    bv = _bv_from_url(url) or "unknown"
    prompt = build_prompt(url, transcript)
    try:
        resp = client.generate(prompt, system=SYSTEM, temperature=0.2, max_tokens=1000)
    except Exception as exc:
        print("  [LLM调用失败] %r" % exc)
        return None
    data = _extract_json(resp)
    if not data:
        print("  [未能解析出JSON] 模型输出: %s" % (resp or "")[:120])
        return None
    cat = data.get("category") or "教程/其他"
    method = {
        "method_id": "bili_%s" % str(int(time.time() * 1000) % 100000),
        "category": cat,
        "name": data.get("name") or ("B站教程:" + (cat or "Rhino建模")),
        "params": data.get("params") or {},
        "steps": data.get("steps") or [],
        "notes": data.get("notes") or "由本地AI从B站教程逐字稿提炼",
        "learned": True,
        "source": "bilibili:" + bv,
        "source_case": "bilibili:" + bv,
        "provenance": {"platform": "bilibili", "bvid": bv, "url": url},
    }
    # 向量技能库: 入库前按最终方法文本算向量(供检索与语义去重)
    method["_embed"] = method_library.compute_embed(method)
    return method


def learn_tutorials(urls=None, links_file=DEFAULT_LINKS_FILE, client=None, dedupe=True):
    """对每一条 B站教程链接: 找逐字稿 -> 提炼 -> 语义去重 -> 入库。返回新增条数。"""
    client = client or OllamaClient()
    links = _load_links(urls, links_file)
    if not links:
        print("没有可学的链接。传 --urls，或把链接写进 %s" % links_file)
        return 0
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    added = 0
    for i, url in enumerate(links, 1):
        bv = _bv_from_url(url)
        print("[%d/%d] %s (%s) ..." % (i, len(links), url, bv or "无BV号"))
        tp = _transcript_path(url)
        if not tp:
            print("  [缺逐字稿] 请先用视频转写链路生成 %s/%s.txt 后重试"
                  % (TRANSCRIPTS_DIR, bv or "BV号"))
            continue
        with open(tp, "r", encoding="utf-8") as f:
            transcript = f.read()
        if not transcript or len(transcript) < 50:
            print("  [逐字稿过短] %s" % tp)
            continue
        method = distill_method(url, transcript, client)
        if not method:
            continue
        # 语义近似去重(与案例学习同一策略)
        if dedupe:
            dup, sim = _semantic_dup(method)
            if dup:
                print("  [跳过] 与既有方法[%s]语义高度相似(%.2f)" % (dup.get("name"), sim))
                continue
        method_library.add_method(method)
        added += 1
        print("  -> 已写入方法库: %s [%s] (来源 %s)"
              % (method["name"], method["category"], method["source"]))
    print("\n完成: 新增 %d 个方法。" % added)
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", nargs="*", help="B站教程链接列表")
    ap.add_argument("--links-file", default=DEFAULT_LINKS_FILE, help="链接文件路径")
    ap.add_argument("--no-dedupe", action="store_true", help="关闭语义去重")
    a = ap.parse_args()
    learn_tutorials(urls=a.urls, links_file=a.links_file, dedupe=not a.no_dedupe)
