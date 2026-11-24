# -*- coding: utf-8 -*-
"""
learning/llm_client.py — 本地 Ollama LLM 客户端(全本地, 不碰云端)
=====================================================================
通过 Ollama 本地服务(127.0.0.1:11434)调用已安装的本地模型(如 qwen2.5:7b)，
供 learn 提炼方法、refine_loop 归因修正使用。纯标准库 urllib，无第三方依赖。
"""
import json
import urllib.request


class OllamaClient:
    """连接本机 Ollama 的最小客户端。"""

    def __init__(self, host="127.0.0.1", port=11434, model="qwen2.5:7b", timeout=600):
        self.url = "http://%s:%s/api/generate" % (host, port)
        self.model = model
        self.timeout = timeout

    def generate(self, prompt, system="", temperature=0.2, max_tokens=1000):
        """单次生成(流式接收, 长任务稳定)。返回模型文本响应。"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,  # 流式接收, 避免长生成时连接被重置
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            parts = []
            buf = b""
            for raw in resp:
                buf += raw
                # 逐行解析 NDJSON
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    parts.append(obj.get("response", ""))
                    if obj.get("done"):
                        return "".join(parts).strip()
        return "".join(parts).strip()

    def available(self):
        """探测本地服务是否可用。"""
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8")).get("models", [])
        except Exception:
            return []


if __name__ == "__main__":
    c = OllamaClient()
    print("本地模型:", [m["name"] for m in c.available()] or "无")
    r = c.generate("一句话: 陶瓷建模时壁厚一般不小于多少毫米?")
    print("测试:", r)
