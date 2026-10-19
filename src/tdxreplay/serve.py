"""tdxreplay.serve — 以 HTTP SSE 流对外提供模拟实时行情（仅标准库）。

回测系统的"实时模式"只需连一个 SSE 接口即可吃到与实盘同构的逐根行情，
用于验证它在实时条件下的真实行为。
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .engine import ReplaySession


def _event_payload(ev) -> str:
    return json.dumps({
        "code": ev.code, "market": ev.market,
        "datetime": ev.bar.datetime,
        "open": ev.bar.open, "high": ev.bar.high,
        "low": ev.bar.low, "close": ev.bar.close,
        "amount": ev.bar.amount, "vol": ev.bar.vol,
        "index": ev.index, "pace_seconds": ev.pace_seconds,
    }, ensure_ascii=False)


def serve(session: ReplaySession, host: str = "127.0.0.1", port: int = 8640,
          on_end: Optional[Callable[[], None]] = None) -> None:  # type: ignore[name-defined]
    """阻塞式启动 SSE 服务并开始回放。GET /stream 订阅行情。"""
    holders = {"gen": session.__iter__(), "done": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.rstrip("/") not in ("/stream", ""):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for ev in holders["gen"]:
                try:
                    self.wfile.write(f"data: {_event_payload(ev)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionAbortedError):
                    return
            holders["done"] = True

        def log_message(self, *a):  # 静默访问日志
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[tdxreplay] SSE 行情流: http://{host}:{port}/stream  "
          f"({len(session.codes)} 只, {len(session.timeline)} 根, speed={session.speed})")
    try:
        server.serve_forever()
    finally:
        if on_end:
            on_end()
