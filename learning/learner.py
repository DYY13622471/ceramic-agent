# -*- coding: utf-8 -*-
"""
learning/learner.py — AI 提炼器型方法(第2步: 自我学习)
=====================================================================
读 store 里的建模案例(case_*.json), 用本地 Ollama 模型提炼出"这类器型
怎么建模"的方法(类别/步骤/参数/工艺), 写入方法库(method_library.json)。
此后 planner 生成同类模型时就会用这些提炼出的方法, 而不是固定模板。
"""
import os
import sys
import json
import time
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning import cases_store
from learning import method_library
from learning.llm_client import OllamaClient

SYSTEM = (
    "你是资深陶瓷产品三维建模工程师，精通 Rhino8。用户会给你一段建模师的"
    "Rhino 操作命令序列，请提炼出'这类器型怎么建模'的可复用方法。"
    "只输出严格 JSON，不要多余文字。"
)


def _case_flow(case):
    cmds = []
    for s in case.get("steps", []):
        cmds.extend(s.get("commands", []))
    noise = {"_SetDisplayMode", "_Save", "_Show"}
    return [c for c in cmds if c not in noise and c.startswith("_")]


def _extract_json(text):
    if not text:
        return None
    # 去掉 markdown 代码围栏 ```json ... ```
    t = re.sub(r"```(?:json)?", "", text)
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # 可能被截断: 尝试补全最外层未闭合的括号
        cand = m.group(0)
        if cand.count("{") > cand.count("}"):
            cand += "}" * (cand.count("{") - cand.count("}"))
        try:
            return json.loads(cand)
        except Exception:
            return None


def build_prompt(case):
    flow = " -> ".join(_case_flow(case)) or "(无命令)"
    meta = case.get("category") or case.get("intent") or "未分类"
    prompt = (
        "以下是一次建模操作的命令序列，器型类别线索: %s。\n"
        "请提炼方法，输出严格 JSON(不要多余文字)，格式：\n"
        '{"category":"器型类别","name":"简短方法名",'
        '"params":{"关键参数":"数值或描述"},'
        '"steps":["步骤1","步骤2",...],"notes":"工艺要点"}\n\n'
        "命令序列:\n%s\n" % (meta, flow)
    )
    return prompt


def extract_method(case, client):
    prompt = build_prompt(case)
    try:
        resp = client.generate(prompt, system=SYSTEM, temperature=0.2, max_tokens=1000)
    except Exception as exc:
        print("  [LLM调用失败] %r" % exc)
        return None
    data = _extract_json(resp)
    if not data:
        print("  [未能解析出JSON] 模型输出: %s" % resp[:120])
        return None
    cat = data.get("category") or case.get("category") or "回转体/其他"
    mid = "learned_%s" % str(int(time.time() * 1000) % 100000)
    method = {
        "method_id": mid,
        "category": cat,
        "name": data.get("name") or (cat + "(从案例学习)"),
        "params": data.get("params") or {},
        "steps": data.get("steps") or ["提取母线", "旋转成曲面", "加壁厚挖空", "工艺检查"],
        "notes": data.get("notes") or "由本地AI从案例提炼",
        "learned": True,
        "source_case": case.get("session_id"),
    }
    # ★ 向量技能库: 提炼出的方法先算向量(供 add_method 与语义去重使用)
    method["_embed"] = method_library.compute_embed(method)
    return method


def _semantic_dup(method):
    """在方法库中找同类别且与 method 语义高度相似的方法(向量技能库版去重)。"""
    lib = method_library.load()
    for m in lib["methods"]:
        if m.get("category") != method.get("category"):
            continue
        emb = m.get("_embed_dense") or m.get("_embed") or {}
        s = method_library._cosine(method.get("_embed", {}), emb)
        if s is not None and s > 0.92:
            return m, s
    return None, 0.0


def learn_all(client=None, dedupe=True):
    client = client or OllamaClient()
    cases = cases_store.list_cases()
    if not cases:
        print("案例库为空，无法提炼。先记录一次建模。")
        return 0
    added = 0
    for i, case in enumerate(cases, 1):
        print("[%d/%d] 提炼案例 %s ..." % (i, len(cases), case.get("session_id")))
        method = extract_method(case, client)
        if not method:
            continue
        # 去重按"源案例"判定(同一案例不重复沉淀), 不再按器型类别拦截:
        # 同一类别的不同案例各自都能沉淀自己的方法, 进化更快
        src = method.get("source_case")
        existing_srcs = {m.get("source_case") for m in method_library.load()["methods"]}
        if dedupe and src and src in existing_srcs:
            print("  [跳过] 案例 %s 已提炼过方法(避免重复沉淀)" % src)
            continue
        # ★ 向量技能库: 同类别语义近似去重(避免沉淀同质方法, 进化更纯)
        if dedupe:
            dup, sim = _semantic_dup(method)
            if dup:
                print("  [跳过] 与既有方法[%s]语义高度相似(%.2f), 避免沉淀同质方法"
                      % (dup.get("name"), sim))
                continue
        method_library.add_method(method)
        added += 1
        print("  -> 已写入方法库: %s [%s]" % (method["name"], method["category"]))
    print("\n完成: 新增 %d 个方法。" % added)
    return added


if __name__ == "__main__":
    learn_all()
