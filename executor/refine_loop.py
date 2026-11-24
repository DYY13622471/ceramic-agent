# -*- coding: utf-8 -*-
"""
executor/refine_loop.py — 自动修正闭环
生成脚本 -> Golem执行 -> 读实测几何 -> 量化自检(vs目标误差)
-> 超阈值则本地LLM归因调参 -> 重新生成执行 -> 直到达标或最大轮数。
"""
import os
import sys
import json
import re
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from executor import exec_plan, self_check
from learning.llm_client import OllamaClient
from recorder.golem_client import GolemClient

GEN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "generated")

_JSON_RE = re.compile(r"\{.*\}", re.S)
_GUID_RE = re.compile(r'"(?:bottle|cup|body)_guid"\s*:\s*"?([0-9a-fA-F\-]+)"?')


def _extract_json(text):
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text)
    m = _JSON_RE.search(t)
    if not m:
        return None
    cand = m.group(0)
    if cand.count("{") > cand.count("}"):
        cand += "}" * (cand.count("{") - cand.count("}"))
    try:
        return json.loads(cand)
    except Exception:
        return None


def _collect_text(resp):
    """把 Golem 响应里所有可能的文本层拼起来(兼容一层/两层/字符串嵌套)。"""
    texts = []
    r = resp.get("result", {}) if isinstance(resp, dict) else {}
    if isinstance(r, dict):
        for k in ("stdout", "text"):
            if r.get(k):
                texts.append(str(r[k]))
        inner = r.get("result")
        if isinstance(inner, dict):
            for k in ("stdout", "text"):
                if inner.get(k):
                    texts.append(str(inner[k]))
        elif isinstance(inner, str):
            texts.append(inner)
    return "\n".join(texts)


def _extract_guid(resp):
    """从 Golem run_script_file 响应(stdout)中提取新建对象 guid。"""
    r = resp.get("result", {}) if isinstance(resp, dict) else {}
    text = _collect_text(resp)
    # 优先解析 __GOLEM_RESULT__ JSON
    m = re.search(r"__GOLEM_RESULT__(.*)", text)
    if m:
        d = _extract_json(m.group(1))
        if d:
            for k in ("bottle_guid", "cup_guid", "body_guid", "guid"):
                if d.get(k):
                    return str(d[k])
    m = _GUID_RE.search(text)
    if m:
        return m.group(1)
    # 兜底: result 层直接给 guid
    if isinstance(r, dict):
        for key in ("bottle_guid", "cup_guid", "body_guid", "guid"):
            if r.get(key):
                return r[key]
        inner = r.get("result")
        if isinstance(inner, dict):
            for key in ("bottle_guid", "cup_guid", "body_guid", "guid"):
                if inner.get(key):
                    return inner[key]
    return None


def _measure(golem, guid):
    resp = golem.call("scene.get_object_info", {"guid": guid})
    r = resp.get("result", {}) or {}
    obj = r.get("object") or r
    return obj


def _proportional_fix(target, report, params):
    """确定性比例修正(优先): 实测=参数*K, 新参数=当前*(目标/实测)。"""
    fix = {}
    err_map = {"高度mm": "height", "直径mm": "diameter"}
    for label, key in err_map.items():
        for e in report["errors"]:
            if e[0] == label and e[2] and e[1]:
                cur = params.get(key)
                if cur and e[1] > 1e-6:
                    fix[key] = round(cur * (e[2] / e[1]), 2)
    return fix or None


def _llm_adjust(llm, target, report, params):
    err_desc = "; ".join(
        "%s 实测%.1f 目标%.1f 误差%+.1f%%" % (e[0], e[1], e[2], e[3] * 100)
        for e in report["errors"])
    prompt = (
        "你是陶瓷建模工程师。下面是一次 Rhino 回转体建模结果 vs 目标的误差和当前参数。\n"
        "请判断应调整哪个参数(如 height 高度 / diameter 直径 / wall 壁厚 / 母线比例)\n"
        "使结果接近目标。只输出严格 JSON，格式:\n"
        '{"调整":"一句话说明","建议参数":{"参数名":新数值}}\n\n'
        "误差:\n%s\n\n当前参数:\n%s\n\n目标:\n%s\n" % (
            err_desc,
            json.dumps(params, ensure_ascii=False),
            json.dumps(target, ensure_ascii=False)))
    try:
        resp = llm.generate(prompt, system="你是陶瓷回转体建模参数优化专家。",
                            temperature=0.1, max_tokens=300)
    except Exception as exc:
        print("  [LLM归因失败] %r" % exc)
        return None
    data = _extract_json(resp)
    if not data:
        return None
    for k in ("建议参数", "params", "new_params", "调整参数"):
        if isinstance(data.get(k), dict) and data[k]:
            return {kk: vv for kk, vv in data[k].items() if isinstance(vv, (int, float))}
    return None


def _log_round(log_path, rnd, params, report, phase="check", adjust=None):
    entry = {
        "t": time.strftime("%Y-%m-%d %H:%M:%S"),
        "round": rnd,
        "phase": phase,
        "params": dict(params),
        "errors": report["errors"] if report else None,
        "max_error_pct": round(report["max_error"] * 100, 2) if report else None,
        "adjustment": adjust,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        print("  [闭环日志写入失败] %r" % exc)


def run_refine(target, plan_doc, golem=None, llm=None, max_rounds=5, tol=0.03):
    """闭环迭代建模。target 例: {"height":210,"diameter":86,"wall":2.0,"volume_ml":600}"""
    golem = golem or GolemClient()
    llm = llm or OllamaClient()
    params = dict(plan_doc.get("params", {}))
    report = None
    final_rnd = max_rounds
    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "store", "refine_log_%s.jsonl"
                            % time.strftime("%Y%m%d_%H%M%S"))
    print("\n[闭环日志] %s" % log_path)
    for rnd in range(1, max_rounds + 1):
        plan_doc["params"] = params
        path = exec_plan.save_script(plan_doc, GEN_DIR)
        print("\n[第%d轮] 执行 %s" % (rnd, os.path.basename(path)))
        resp = golem.run_script_file(path)
        if not golem.ok(resp):
            err = resp.get("result", {}).get("error") or resp
            print("  执行失败: %s" % err)
            break
        guid = _extract_guid(resp)
        if not guid:
            print("  无法定位生成对象 guid")
            print("  响应文本片段:", _collect_text(resp)[-400:])
            break
        obj = _measure(golem, guid)
        report = self_check.analyze_vs_target(obj, target)
        errs = "  ".join("%s %+.1f%%" % (e[0], e[3] * 100) for e in report["errors"])
        print("  自检: %s" % (errs or "无量化指标"))
        print("  最大误差: %.1f%%" % (report["max_error"] * 100))
        _log_round(log_path, rnd, params, report, phase="check")
        if report["max_error"] <= tol:
            _log_round(log_path, rnd, params, report, phase="pass")
            print("  ✓ 达标(误差≤%.1f%%), 第%d轮通过" % (tol * 100, rnd))
            return report, plan_doc, rnd
        adjust = _proportional_fix(target, report, params)
        if adjust:
            print("  比例修正(确定性): %s" % json.dumps(adjust, ensure_ascii=False))
        else:
            adjust = _llm_adjust(llm, target, report, params)
            print("  本地AI归因: %s" % json.dumps(adjust or {}, ensure_ascii=False))
        if not adjust:
            _log_round(log_path, rnd, params, report, phase="stop")
            print("  无有效调整建议, 停止迭代")
            return report, plan_doc, rnd
        params.update(adjust)
        _log_round(log_path, rnd, params, report, phase="adjust", adjust=adjust)
    print("\n⚠️ 未在 %d 轮内达标。" % max_rounds)
    return report, plan_doc, final_rnd


if __name__ == "__main__":
    print("refine_loop 模块就绪 (本地执行: Golem=9876, 归因: Ollama=11434)")