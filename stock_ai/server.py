"""单只股票/ETF 行情查询与看板 HTTP 服务。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import aggregate, cache, eastmoney, grid
from .eastmoney import QuoteError

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "echarts.min.js": "application/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
}


def list_symbols() -> list:
    groups = []
    for key, label in (("etf", "ETF"), ("stock", "个股")):
        directory = cache.DATA_DIR / key
        symbols = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                obj = cache.load_file(path)
                data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
                code = data.get("code") or path.stem
                symbols.append({
                    "code": code,
                    "name": data.get("name") or code,
                    "query_begin_time": data.get("query_begin_time") or "",
                    "query_end_time": data.get("query_end_time") or "",
                })
        groups.append({"key": key, "label": label, "symbols": symbols})
    return groups


def _year_ago(end_text: str) -> str:
    try:
        end = date.fromisoformat(end_text[:10])
    except ValueError:
        end = date.today()
    try:
        return end.replace(year=end.year - 1).isoformat()
    except ValueError:
        return end.replace(year=end.year - 1, day=28).isoformat()


class StockHandler(BaseHTTPRequestHandler):
    server_version = "StockAI/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in
                 parse_qs(parsed.query, keep_blank_values=True).items()}
        try:
            if parsed.path == "/":
                self._send_static("index.html")
                return
            if parsed.path.startswith("/static/"):
                name = parsed.path.split("/static/", 1)[1]
                if name not in STATIC_TYPES:
                    self._send_json(404, {"error": "未找到静态资源", "path": name})
                    return
                self._send_static(name)
                return
            if parsed.path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            if parsed.path == "/api/symbols/add":
                code = self._require(query, "code")
                end_text = query.get("end") or date.today().isoformat()
                start_text = query.get("start") or _year_ago(end_text)
                info = eastmoney.get_stock_data(code)
                history = eastmoney.get_history(
                    code, start_text, end_text, force=True, save_range=True
                )
                self._send_json(200, {
                    "code": code,
                    "info": info,
                    "history_count": history["count"],
                    "start": start_text,
                    "end": end_text,
                })
                return
            if parsed.path == "/api/symbols":
                self._send_json(200, list_symbols())
                return
            if parsed.path == "/api/cache":
                code = self._require(query, "code")
                payload = cache.read_records(code)
                if payload is None:
                    self._send_json(404, {"error": f"本地无缓存数据: {code}"})
                else:
                    self._send_json(200, payload)
                return
            if parsed.path == "/api/aggregate":
                code = self._require(query, "code")
                result = aggregate.aggregate(code, query.get("period", "day"))
                self._send_json(200, result)
                return
            if parsed.path == "/api/grid/settings":
                self._send_json(200, grid.load_settings(self._require(query, "code")))
                return
            if parsed.path == "/api/grid/simulate":
                result = grid.simulate(
                    self._require(query, "code"),
                    self._require(query, "start"),
                    query.get("base_shares", 1000),
                    query.get("grid_shares", 100),
                    query.get("up_pct", 1),
                    query.get("down_pct", 1),
                    query.get("fee", 5),
                    query.get("base_price"),
                )
                self._send_json(200, result)
                return
            if parsed.path == "/api/quote":
                self._send_json(200, eastmoney.get_quote(self._require(query, "code")))
                return
            if parsed.path == "/api/history":
                truthy = ("1", "true", "yes")
                force = str(query.get("refresh", query.get("force", "0"))).lower() in truthy
                save_range = str(query.get("save_range", "0")).lower() in truthy
                args = (
                    self._require(query, "code"),
                    query.get("start"),
                    query.get("end"),
                    query.get("period", 101),
                    query.get("adjust", 1),
                )
                if force or save_range:
                    options = {}
                    if force:
                        options["force"] = True
                    if save_range:
                        options["save_range"] = True
                    result = eastmoney.get_history(*args, **options)
                else:
                    result = eastmoney.get_history(*args)
                self._send_json(200, result)
                return
            if parsed.path == "/api/stock":
                code = self._require(query, "code")
                if query.get("start") or query.get("end"):
                    result = eastmoney.get_history(
                        code, query.get("start"), query.get("end"),
                        query.get("period", 101), query.get("adjust", 1),
                    )
                else:
                    result = eastmoney.get_quote(code)
                self._send_json(200, result)
                return
            self._send_json(404, {"error": "未找到接口", "path": parsed.path})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except LookupError as exc:
            self._send_json(404, {"error": str(exc)})
        except QuoteError as exc:
            self._send_json(502, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": f"服务器内部错误: {exc}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/grid/settings", "/api/symbols/delete"):
            self._send_json(404, {"error": "未找到接口", "path": parsed.path})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            self._send_json(400, {"error": f"请求体不是合法 JSON: {exc}"})
            return
        try:
            if parsed.path == "/api/symbols/delete":
                code = str(payload.get("code") or "").strip()
                cache.delete_cache(code)
                self._send_json(200, {"code": code, "deleted": True})
                return
            self._send_json(200, grid.save_settings(payload))
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": f"服务器内部错误: {exc}"})

    @staticmethod
    def _require(query: dict, key: str) -> str:
        value = query.get(key, "").strip()
        if not value:
            raise ValueError(f"缺少必填参数: {key}")
        return value

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _send_static(self, name: str):
        path = STATIC_DIR / name
        try:
            body = path.read_bytes()
        except OSError:
            self._send_json(404, {"error": "未找到静态资源", "path": name})
            return
        self._send_bytes(200, STATIC_TYPES[name], body)

    def _send_bytes(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def create_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), StockHandler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="单只股票/ETF 行情查询与看板服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000")
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port)
    print(f"stock_ai 看板已启动: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
