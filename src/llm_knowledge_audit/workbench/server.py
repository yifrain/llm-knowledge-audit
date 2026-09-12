"""Loopback-only UI server. Controlled runs with same-origin, memory-only credentials.

仅监听回环地址的本地 UI 服务器：
- 不加载任何远程资源，不暴露任意路径读取，付费运行必须显式审批；
- 只允许本机同源访问（Host/Origin 校验），写操作还需携带每次启动随机生成的 token。
"""

from __future__ import annotations

import errno
import json
import mimetypes
import secrets
import urllib.request
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..env import loaded_env
from .runs import ConsoleError
from .service import Workbench

# 前端静态资源目录（index.html / app.js / style.css）
ASSETS = Path(__file__).parent / "assets"


def env_state() -> dict[str, Any]:
    """网页端可见的 .env 状态：文件路径 + 载入的变量名，**不含任何值**。

    路径必须转成 str：Path 无法被 json.dumps 序列化，否则整个 /api/state 会 400，
    页面起不来、幂等启动探测也会误判。
    """
    path, names = loaded_env()
    return {"path": str(path) if path else None, "names": list(names)}


def _is_workbench_running(port: int) -> bool:
    """探测该端口上是否已经运行着本工作台实例（用于幂等启动）。

    通过 GET /api/state 判断：能返回带 runs/token 字段的 JSON 才是本工作台。
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1) as resp:
            payload = json.loads(resp.read())
        return isinstance(payload, dict) and "runs" in payload and "token" in payload
    except (OSError, ValueError):
        return False


def serve(root: Path, port: int = 8765, open_browser: bool = False) -> None:
    """启动本地工作台 HTTP 服务（阻塞直到 Ctrl+C）。

    幂等启动：若端口上已有本工作台实例，则直接复用并（按需）打开浏览器。
    """
    workbench = Workbench(root)
    # 工作台只面向本项目目录；用 configs/learn.yaml 作为项目根目录的标识
    if not (root / "configs/learn.yaml").exists():
        raise ValueError("请在 llm-knowledge-audit 项目目录运行，或使用 --root 指定目录")
    # 每次启动随机生成写操作 token：页面脚本持有它，POST 必须携带，防止被其他网页冒用
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # 静默默认请求日志，保持控制台输出干净

        def reply(self, value: Any, status: int = 200) -> None:
            """统一的 JSON 响应助手，附带安全响应头。"""
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def local_request(self) -> bool:
            """同源校验：Host 必须精确匹配 127.0.0.1:端口，Origin 只能是本站或缺省。

            用于抵御 DNS rebinding（恶意域名解析到本机）与跨站请求。
            """
            expected = f"127.0.0.1:{server.server_port}"
            host = self.headers.get("Host")
            origin = self.headers.get("Origin")
            return host == expected and origin in (None, "http://" + expected)

        def do_GET(self) -> None:
            if not self.local_request():
                self.reply({"error": "local_only"}, 403)
                return
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            run = query.get("run", [""])[0]
            try:
                # 只读 API 路由：全部映射到 Workbench 的只读方法
                routes: dict[str, Callable[[], Any]] = {
                    "/api/state": lambda: {
                        "runs": workbench.runs(),
                        "token": token,
                        "env": env_state(),
                    },
                    "/api/defaults": workbench.defaults,
                    "/api/progress": lambda: workbench.progress(run),
                    "/api/run": lambda: workbench.overview(run),
                    "/api/trace": lambda: workbench.trace(run, query.get("case", [""])[0]),
                    "/api/cases": lambda: workbench.case_queue(query.get("scope", ["pilot"])[0]),
                    "/api/review": lambda: workbench.review(run),
                }
                if parsed.path in routes:
                    self.reply(routes[parsed.path]())
                    return
                if parsed.path == "/api/export":
                    data, filename = workbench.export(run, query.get("name", [""])[0])
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                # Explicit static asset allowlist; no arbitrary paths.
                name = {
                    "/": "index.html",
                    "/app.js": "app.js",
                    "/style.css": "style.css",
                    "/i18n.js": "i18n.js",
                }.get(parsed.path)
                if not name:
                    self.reply({"error": "not_found"}, 404)
                    return
                data = (ASSETS / name).read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    (mimetypes.guess_type(name)[0] or "text/plain") + "; charset=utf-8",
                )
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                # 严格 CSP：仅允许本站资源，禁止外链脚本与框架嵌入
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'self'; script-src 'self'; "
                    "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'self'",
                )
                self.end_headers()
                self.wfile.write(data)
            except ConsoleError as exc:
                self.reply({"error": exc.code}, 400)
            except (ValueError, KeyError, OSError, TypeError):
                self.reply({"error": "invalid_request"}, 400)

        def do_POST(self) -> None:
            # 写操作双重校验：同源 + 携带本次启动的 token
            if not self.local_request() or not secrets.compare_digest(
                self.headers.get("X-Review-Token", ""), token
            ):
                self.reply({"error": "refresh_required"}, 403)
                return
            try:
                # 请求体限制：必须为 JSON 对象，大小不超过 64KB
                size = int(self.headers.get("Content-Length", "0"))
                if (
                    size < 0
                    or size > 65536
                    or self.headers.get_content_type() != "application/json"
                ):
                    raise ConsoleError("invalid_request")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ConsoleError("invalid_request")
                # Background runs and credential writes retain the same origin/token checks.
                if self.path == "/api/preview":
                    result = workbench.preview(body)
                elif self.path == "/api/credentials":
                    result = workbench.credentials(body)
                elif self.path == "/api/start":
                    result = workbench.start(body)
                elif self.path == "/api/verify-batch":
                    result = workbench.verify_batch(body)
                elif self.path == "/api/verify-case":
                    result = workbench.verify_case(body)
                elif self.path == "/api/annotate":
                    result = workbench.annotate(str(body.get("run", "")), body)
                else:
                    self.reply({"error": "not_found"}, 404)
                    return
                self.reply(result)
            except ConsoleError as exc:
                self.reply({"error": exc.code}, 400)
            except (ValueError, KeyError, OSError, TypeError):
                self.reply({"error": "invalid_request"}, 400)
            except Exception:
                # 兜底：未知错误不外泄细节，并强调原始结果未被覆盖
                self.reply({"error": "execution_failed"}, 500)

    try:
        # 只绑定回环地址 127.0.0.1，局域网内其他机器无法访问
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        # 端口被占用：若已是本工作台实例则直接复用（幂等启动），否则给出清晰报错
        if exc.errno != errno.EADDRINUSE:
            raise
        if not _is_workbench_running(port):
            raise OSError(f"端口 {port} 已被其他程序占用：{exc}") from exc
        address = f"http://127.0.0.1:{port}"
        print(f"工作台已在运行：{address}（复用现有实例，不重复启动）", flush=True)
        if open_browser:
            webbrowser.open(address)
        return
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"本地实验工作台：{address}\n关闭此进程即可停止服务。", flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass  # Ctrl+C 优雅退出
    finally:
        server.server_close()
