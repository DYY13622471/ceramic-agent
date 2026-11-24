# -*- coding: utf-8 -*-
"""
learning/method_library.py — 陶瓷建模方法库(云端/豆包侧)
=====================================================================
存"建模方法"(不是死脚本): 每类器型怎么建模、关键参数习惯、工艺要点。
来源:
  1. 预置基础方法(回转体/放样/浮雕底胚等通用陶瓷建模套路)
  2. 从 record_session 案例中提炼(AI 读案例 -> 提取规律 -> 存成新方法)

planner 建模型时查这个方法库: 命中方法 -> 用它的步骤和参数习惯去建。
这就是"通过记录学习, 然后自主建模"的存储载体。
"""
import json
import os
import re
import time
import math

LIB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "store", "method_library.json")
LIB_PATH = os.path.normpath(LIB_PATH)

# 陶瓷生产通用参数(作为方法库的工艺基准, 全部面向陶瓷生产优先)
PROCESS_BASELINE = {
    "wall_min_mm": 2.0,
    "draft_angle_deg": 3.0,
    "stl_binary": True,
    "stl_tol_mm": 0.01,
    "relief_min_depth_mm": 0.6,
    "relief_min_width_mm": 0.8,
    "grayscale_bits": "8-16",
}


# ============================================================================
# 语义向量技能库(embedding): 让"学到的建模方法"能被按语义检索复用, 替代原来
# 只有"类别精确匹配"的搜索。这是"进化更快、学得更准"的存储/检索升级。
#   - 默认 EMBED_MODEL="" : 用内置纯 Python 字符 n-gram 向量(确定性、离线、零依赖)
#   - 若本机 Ollama 已装嵌入模型(如 nomic-embed-text / bge-m3 / mxbai-embed-large),
#     把 EMBED_MODEL 设为该模型名, 会自动改走真实语义向量(检索更准)。
# ============================================================================
EMBED_MODEL = ""   # 留空=内置词袋向量; 填入 Ollama 嵌入模型名则用真实 embedding


def embed_text(text):
    """把一段文本编码成稀疏向量 dict{token: 归一化权重}(纯标准库, 无需依赖)。
    中文按字符 1-gram + 2-gram, 英文/数字按词。确定性、离线可跑。"""
    vec = {}
    for w in re.findall(r"[a-z0-9_]+", (text or "").lower()):
        vec.setdefault("w:" + w, 0)
        vec["w:" + w] += 1
    for seg in re.findall(r"[\u4e00-\u9fff]+", text or ""):
        for ch in seg:
            vec.setdefault("c1:" + ch, 0)
            vec["c1:" + ch] += 1
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                b = "c2:" + seg[i:i + 2]
                vec.setdefault(b, 0)
                vec[b] += 1
    if not vec:
        return {}
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {k: v / norm for k, v in vec.items()}


def _cosine(a, b):
    """两向量余弦相似度(兼容稀疏 dict 与稠密 list 两种表示)。"""
    if not a or not b:
        return 0.0
    if isinstance(a, list) and isinstance(b, list):      # 稠密(真实embedding)
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)
    keys = set(a) & set(b)                              # 稀疏
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (na * nb)


def _method_text(m):
    """把一条方法压成可检索的文本签名(用于算向量)。"""
    p = m.get("params") or {}
    pstr = " ".join("%s=%s" % (k, v) for k, v in p.items())
    return "%s %s %s %s %s" % (
        m.get("category", ""), m.get("name", ""),
        " ".join(m.get("steps", [])), pstr, m.get("notes", ""),
    )


def compute_embed(m):
    """为单条方法计算向量: 有 _embed_dense(真实embedding)用之, 否则用内置稀疏向量。"""
    dense = m.get("_embed_dense")
    if dense:
        return list(dense)
    return embed_text(_method_text(m))


def _default_lib():
    return {
        "_meta": {
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "process_baseline": PROCESS_BASELINE,
        },
        "methods": [
            {
                "method_id": "revolve_bottle",
                "category": "回转体/瓶子",
                "name": "汾杏青花瓷瓶(回转体)",
                "params": {
                    "profile_src": "参考图提取母线 或 关键尺寸",
                    "wall_mm": 2.0,
                    "fill_ml": 600,
                    "draft": 3,
                },
                "steps": [
                    "提取瓶型母线(口->颈->肩->最大腹径->收腹->底)",
                    "母线绕 Z 轴旋转成外曲面",
                    "外曲面向内偏移壁厚成内曲面, 布尔差 -> 空心容器",
                    "瓶口开口(留口沿), 底面留底厚",
                    "瓶盖单独回转体(鼓形), 直径略大于瓶口",
                    "图层管理 + 实体有效性检查(is_solid/is_valid)",
                ],
                "notes": "满口容量按内腔容积标定; 肩部注意拔模; 壁厚≥2.0",
            },
            {
                "method_id": "revolve_cup",
                "category": "回转体/杯子",
                "name": "直筒茶杯(回转体+壁厚)",
                "params": {
                    "outer_d": 90, "height": 90, "wall_mm": 2.5,
                    "base_thick": 2.5,
                },
                "steps": [
                    "外圆柱(径90 高90) + 内圆柱(径85) -> 布尔差 = 空心筒",
                    "底厚2.5(内圆柱抬底)",
                    "口沿圆角(烧制防崩)",
                    "检查壁厚≥2.0",
                ],
                "notes": "陶瓷3D打印/开模: 壁厚≥2.0mm, 薄壁处加强",
            },
        ],
    }


def load():
    if os.path.exists(LIB_PATH):
        with open(LIB_PATH, "r", encoding="utf-8") as f:
            lib = json.load(f)
    else:
        lib = _default_lib()
        save(lib)
    # ★ 向量技能库: 旧方法缺 _embed 时自动回填(仅内存, 下次 add_method/save 落盘)
    for m in lib.get("methods", []):
        if "_embed" not in m and "_embed_dense" not in m:
            m["_embed"] = compute_embed(m)
    return lib


def save(lib):
    os.makedirs(os.path.dirname(LIB_PATH), exist_ok=True)
    with open(LIB_PATH, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)


def add_method(method_dict):
    if "_embed" not in method_dict and "_embed_dense" not in method_dict:
        method_dict["_embed"] = compute_embed(method_dict)
    lib = load()
    lib["methods"].append(method_dict)
    save(lib)
    return method_dict["method_id"]


def search(category=None, keyword=None, query=None, top_k=None):
    """按条件检索方法库。
    兼容原(category/keyword)精确检索; 新增 query: 语义向量排序返回最相似 top_k。
    """
    lib = load()
    methods = lib["methods"]
    if category:
        methods = [m for m in methods if m.get("category") == category]
    if keyword:
        methods = [m for m in methods
                   if keyword in m.get("name", "") or keyword in m.get("category", "")]
    if query:
        q = compute_embed({"category": "", "name": "", "steps": [query],
                           "params": {}, "notes": ""})
        scored = []
        for m in methods:
            emb = m.get("_embed_dense") or m.get("_embed") or {}
            scored.append((_cosine(q, emb), m))
        scored.sort(key=lambda t: t[0], reverse=True)
        methods = []
        for s, m in scored:
            m["_score"] = round(s, 4)
            methods.append(m)
        if top_k:
            methods = methods[:top_k]
    return methods


def retrieve(query, top_k=3, category=None):
    """便捷入口: 按语义查最相似方法(供 planner/refine 复用手法)。"""
    return search(query=query, top_k=top_k, category=category)


def get(method_id):
    lib = load()
    for m in lib["methods"]:
        if m["method_id"] == method_id:
            return m
    return None


if __name__ == "__main__":
    lib = load()
    print("方法数:", len(lib["methods"]))
    for m in lib["methods"]:
        print(" -", m["method_id"], m["name"])
