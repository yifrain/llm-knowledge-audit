"""Loopback-only UI server. No remote assets, arbitrary paths, or paid-run endpoints."""

from __future__ import annotations

import json
import mimetypes
import secrets
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .service import Workbench

ASSETS = Path(__file__).parent / "assets"


def serve(root: Path, port: int = 8765, open_browser: bool = False) -> None:
    workbench = Workbench(root)
    if not (root / "configs/learn.yaml").exists():
        raise ValueError("请在 llm-knowledge-audit 项目目录运行，或使用 --root 指定目录")
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def reply(self, value: Any, status: int = 200) -> None:
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def local_request(self) -> bool:
            expected = f"127.0.0.1:{server.server_port}"
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            return host == expected and origin in (None, "http://" + expected)

        def do_GET(self) -> None:
            if not self.local_request():
                self.reply({"error": "仅接受本机同源访问"}, 403)
                return
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            run = query.get("run", [""])[0]
            try:
                routes: dict[str, Callable[[], Any]] = {
                    "/api/state": lambda: {"runs": workbench.runs(), "token": token},
                    "/api/run": lambda: workbench.overview(run),
                    "/api/trace": lambda: workbench.trace(run, query.get("case", [""])[0]),
                    "/api/cases": lambda: workbench.case_queue(query.get("scope", ["pilot"])[0]),
                    "/api/review": lambda: workbench.review(run),
                }
                if parsed.path in routes:
                    self.reply(routes[parsed.path]())
                    return
                name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(
                    parsed.path
                )
                if not name:
                    self.reply({"error": "页面不存在"}, 404)
                    return
                data = (ASSETS / name).read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    (mimetypes.guess_type(name)[0] or "text/plain") + "; charset=utf-8",
                )
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'self'; script-src 'self'; "
                    "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'self'",
                )
                self.end_headers()
                self.wfile.write(data)
            except (ValueError, KeyError, OSError) as exc:
                self.reply({"error": str(exc)}, 400)

        def do_POST(self) -> None:
            if not self.local_request() or not secrets.compare_digest(
                self.headers.get("X-Review-Token", ""), token
            ):
                self.reply({"error": "请刷新本地工作台后重试"}, 403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if (
                    size < 0
                    or size > 65536
                    or self.headers.get_content_type() != "application/json"
                ):
                    raise ValueError("请求格式不正确")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("请求必须是对象")
                if self.path == "/api/demo":
                    result = workbench.demo()
                elif self.path == "/api/verify-case":
                    result = workbench.verify_case(body)
                elif self.path == "/api/annotate":
                    result = workbench.annotate(str(body.get("run", "")), body)
                else:
                    self.reply({"error": "操作不存在"}, 404)
                    return
                self.reply(result)
            except (ValueError, KeyError, OSError) as exc:
                self.reply({"error": str(exc)}, 400)
            except Exception:
                self.reply({"error": "执行失败；请检查本地实验目录，原始结果未覆盖"}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"本地实验工作台：{address}\n关闭此进程即可停止服务。", flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
