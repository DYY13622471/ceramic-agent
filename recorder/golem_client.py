# -*- coding: utf-8 -*-
"""
recorder/golem_client.py — Golem-3DMCP TCP 客户端
协议: [4字节大端uint32长度][UTF-8 JSON]
  请求  {"id":..., "method":"...", "params":{...}}
  响应  {"id":..., "result":{...}, "error":null}
注意: success 标志嵌在 result 内, 需用 r["result"].get("success") 判断。
"""
import socket
import struct
import json


class GolemClient:
    def __init__(self, host="127.0.0.1", port=9876, timeout=60):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _connect(self):
        return socket.create_connection((self.host, self.port), timeout=self.timeout)

    @staticmethod
    def _recv_exact(sock, n):
        buf = b""
        while len(buf) < n:
            c = sock.recv(n - len(buf))
            if not c:
                break
            buf += c
        return buf

    def call(self, method, params=None, rid="x"):
        params = params or {}
        req = {"id": rid, "method": method, "params": params}
        payload = json.dumps(req, ensure_ascii=False).encode("utf-8")
        sock = self._connect()
        try:
            sock.sendall(struct.pack("!I", len(payload)) + payload)
            (n,) = struct.unpack("!I", self._recv_exact(sock, 4))
            raw = self._recv_exact(sock, n)
            return json.loads(raw.decode("utf-8"))
        finally:
            sock.close()

    def ok(self, resp):
        return bool(resp and resp.get("result", {}).get("success"))

    def ping(self):
        return self.call("ping", {}, "ping1")

    def list_objects(self, object_type="all", limit=0, layer=None):
        return self.call("scene.list_objects",
                         {"object_type": object_type, "limit": limit, "layer": layer})

    def command_history(self):
        code = ("import rhinoscriptsyntax as rs\n"
                "h = rs.CommandHistory()\n"
                "__result__ = {'len': len(h), 'text': h}")
        return self.call("scripting.execute_python", {"code": code})

    @staticmethod
    def command_history_text(resp):
        """从 command_history 响应中稳健提取历史文本(兼容多层 result)。"""
        r = resp.get("result", {}) if isinstance(resp, dict) else {}
        if not isinstance(r, dict):
            return ""
        inner = r.get("result")
        if isinstance(inner, dict) and "text" in inner:
            return inner.get("text", "") or ""
        if "text" in r:
            return r.get("text", "") or ""
        return ""

    def capture(self, width=1000, height=1200):
        resp = self.call("viewport.capture",
                         {"width": width, "height": height, "display_mode": "shaded"})
        r = resp.get("result", {}) if isinstance(resp, dict) else {}
        img = r.get("image") if isinstance(r, dict) else None
        if not img and isinstance(r, dict):
            inner = r.get("result")
            if isinstance(inner, dict):
                img = inner.get("image")
        return img

    def run_python(self, code):
        return self.call("scripting.execute_python", {"code": code})

    def run_script_file(self, file_path):
        return self.call("scripting.run_rhino_script", {"file_path": file_path})

    def zoom_extents(self):
        return self.call("viewport.zoom_extents", {})

    def save_as(self, file_path):
        return self.call("files.save_document_as",
                         {"file_path": file_path, "overwrite": True})


if __name__ == "__main__":
    c = GolemClient()
    print("ping:", c.call("ping", {}))
    print("对象数:", c.list_objects().get("result", {}).get("total"))