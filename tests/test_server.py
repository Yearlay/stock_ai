import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_ai.eastmoney import QuoteError
from stock_ai.server import create_server


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address[:2]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            status = response.status
            body = response.read().decode("utf-8")
        finally:
            connection.close()
        return status, json.loads(body)

    def request_text(self, path):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            status = response.status
            content_type = response.getheader("Content-Type")
            body = response.read().decode("utf-8")
        finally:
            connection.close()
        return status, content_type, body

    def request_post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        try:
            connection.request(
                "POST", path, body, {"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            status = response.status
            response_body = response.read().decode("utf-8")
        finally:
            connection.close()
        return status, json.loads(response_body)

    def test_health(self):
        status, body = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})

    def test_quote_endpoint(self):
        quote = {"code": "510300", "latest": 4.038, "high": 4.084,
                 "low": 4.032, "volume": 12765805, "amount": 5183304239.0}
        with patch("stock_ai.server.eastmoney.get_quote", return_value=quote) as get_quote:
            status, body = self.request("/api/quote?code=510300")
        self.assertEqual(status, 200)
        self.assertEqual(body, quote)
        get_quote.assert_called_once_with("510300")

    def test_history_endpoint(self):
        history = {"code": "510300", "count": 1, "records": [{"date": "2025-11-24"}]}
        with patch("stock_ai.server.eastmoney.get_history", return_value=history) as get_history:
            status, body = self.request(
                "/api/history?code=510300&start=20251101&end=20251124"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body, history)
        get_history.assert_called_once_with("510300", "20251101", "20251124", 101, 1)

    def test_history_endpoint_force_refresh(self):
        history = {"code": "510300", "count": 3, "records": []}
        with patch("stock_ai.server.eastmoney.get_history", return_value=history) as get_history:
            status, body = self.request(
                "/api/history?code=510300&start=20251124&end=20261124&refresh=1"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body, history)
        get_history.assert_called_once_with(
            "510300", "20251124", "20261124", 101, 1, force=True
        )

    def test_history_endpoint_save_range(self):
        history = {"code": "510300", "count": 1, "records": []}
        with patch("stock_ai.server.eastmoney.get_history", return_value=history) as get_history:
            status, body = self.request(
                "/api/history?code=510300&start=20251124&end=20261124&save_range=1"
            )
        self.assertEqual(status, 200)
        get_history.assert_called_once_with(
            "510300", "20251124", "20261124", 101, 1, save_range=True
        )

    def test_add_symbol_endpoint(self):
        info = {"code": "512480", "name": "半导体ETF", "source": "eastmoney"}
        history = {"code": "512480", "count": 240, "records": []}
        with patch("stock_ai.server.eastmoney.get_stock_data", return_value=info) as get_data, \
                patch("stock_ai.server.eastmoney.get_history", return_value=history) as get_history:
            status, body = self.request(
                "/api/symbols/add?code=512480&start=20251124&end=20261124"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body["info"], info)
        self.assertEqual(body["history_count"], 240)
        get_data.assert_called_once_with("512480")
        get_history.assert_called_once_with(
            "512480", "20251124", "20261124", force=True, save_range=True
        )

    def test_grid_simulate_endpoint(self):
        payload = {"code": "510300", "trades": [], "stats": {"trade_count": 0}}
        with patch("stock_ai.server.grid.simulate", return_value=payload) as simulate:
            status, body = self.request(
                "/api/grid/simulate?code=510300&start=20261102&base_shares=50"
                "&grid_shares=50&up_pct=10&down_pct=10&fee=1&base_price=10"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        simulate.assert_called_once_with(
            "510300", "20261102", "50", "50", "10", "10", "1", "10"
        )

    def test_delete_symbol_endpoint(self):
        with patch("stock_ai.server.cache.delete_cache") as delete:
            status, body = self.request_post(
                "/api/symbols/delete", {"code": "512480"}
            )
        self.assertEqual(status, 200)
        self.assertEqual(body, {"code": "512480", "deleted": True})
        delete.assert_called_once_with("512480")

    def test_grid_settings_post_and_get(self):
        settings = {
            "code": "510300", "start": "2025-11-24", "base_shares": 1000,
            "grid_shares": 100, "up_pct": 2, "down_pct": 2,
            "fee": 5, "base_price": 4.4,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etf").mkdir()
            (root / "etf" / "510300.json").write_text(
                json.dumps({"data": {"code": "510300", "kline_records": []}}),
                encoding="utf-8",
            )
            with patch("stock_ai.server.cache.DATA_DIR", root):
                status, saved = self.request_post("/api/grid/settings", settings)
                status_get, loaded = self.request("/api/grid/settings?code=510300")
        self.assertEqual(status, 200)
        self.assertEqual(saved, settings)
        self.assertEqual(status_get, 200)
        self.assertEqual(loaded, settings)

    def test_unified_endpoint_routes_by_range(self):
        with patch("stock_ai.server.eastmoney.get_quote", return_value={"kind": "quote"}) as quote, \
                patch("stock_ai.server.eastmoney.get_history", return_value={"kind": "history"}) as history:
            status, body = self.request("/api/stock?code=510300")
            self.assertEqual(status, 200)
            self.assertEqual(body, {"kind": "quote"})
            quote.assert_called_once_with("510300")

            status, body = self.request("/api/stock?code=510300&start=20251101&end=20251124")
            self.assertEqual(status, 200)
            self.assertEqual(body, {"kind": "history"})
            history.assert_called_once_with("510300", "20251101", "20251124", 101, 1)

    def test_missing_code_returns_400(self):
        status, body = self.request("/api/quote")
        self.assertEqual(status, 400)
        self.assertIn("code", body["error"])

    def test_invalid_code_returns_400(self):
        status, body = self.request("/api/quote?code=abc")
        self.assertEqual(status, 400)
        self.assertIn("6 位数字", body["error"])

    def test_upstream_failure_returns_502(self):
        with patch("stock_ai.server.eastmoney.get_quote", side_effect=QuoteError("upstream down")):
            status, body = self.request("/api/quote?code=510300")
        self.assertEqual(status, 502)
        self.assertEqual(body, {"error": "upstream down"})

    def test_unknown_path_returns_404(self):
        status, body = self.request("/api/unknown")
        self.assertEqual(status, 404)
        self.assertEqual(body["path"], "/api/unknown")

    def test_symbols_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etf").mkdir()
            (root / "stock").mkdir()
            (root / "etf" / "510300.json").write_text(
                json.dumps({"data": {
                    "code": "510300", "name": "沪深300ETF",
                    "query_begin_time": "2025-11-24", "query_end_time": "2026-11-24",
                }}),
                encoding="utf-8",
            )
            (root / "stock" / "600519.json").write_text(
                json.dumps({"data": {"code": "600519", "name": "贵州茅台"}}),
                encoding="utf-8",
            )
            with patch("stock_ai.server.cache.DATA_DIR", root):
                status, body = self.request("/api/symbols")
        self.assertEqual(status, 200)
        self.assertEqual(body[0]["label"], "ETF")
        self.assertEqual(body[0]["symbols"][0]["code"], "510300")
        self.assertEqual(body[0]["symbols"][0]["query_begin_time"], "2025-11-24")
        self.assertEqual(body[0]["symbols"][0]["query_end_time"], "2026-11-24")
        self.assertEqual(body[1]["label"], "个股")
        self.assertEqual(body[1]["symbols"][0]["name"], "贵州茅台")

    def test_cache_endpoint(self):
        payload = {"code": "510300", "kline_title": [], "records": [{"date": "2026-11-23"}]}
        with patch("stock_ai.server.cache.read_records", return_value=payload) as read:
            status, body = self.request("/api/cache?code=510300")
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        read.assert_called_once_with("510300")

    def test_cache_endpoint_missing(self):
        with patch("stock_ai.server.cache.read_records", return_value=None):
            status, body = self.request("/api/cache?code=999999")
        self.assertEqual(status, 404)
        self.assertIn("999999", body["error"])

    def test_aggregate_endpoint(self):
        payload = {"code": "510300", "period": "week", "count": 1, "records": []}
        with patch("stock_ai.server.aggregate.aggregate", return_value=payload) as agg:
            status, body = self.request("/api/aggregate?code=510300&period=week")
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)
        agg.assert_called_once_with("510300", "week")

    def test_aggregate_invalid_period(self):
        with patch("stock_ai.server.aggregate.aggregate",
                   side_effect=ValueError("不支持的周期")):
            status, body = self.request("/api/aggregate?code=510300&period=bad")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "不支持的周期"})

    def test_index_and_static_files(self):
        status, content_type, body = self.request_text("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("stock_ai 行情看板", body)

        status, content_type, body = self.request_text("/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)
        self.assertIn("StockUI", body)

        status, _, body = self.request_text("/static/echarts.min.js")
        self.assertEqual(status, 200)
        self.assertIn("Apache Software Foundation", body)

        status, _, body = self.request_text("/static/style.css")
        self.assertEqual(status, 200)
        self.assertIn(".sidebar", body)

        status, body = self.request("/static/missing.js")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
