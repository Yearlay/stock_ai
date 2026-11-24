import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from stock_ai import eastmoney


class IsolatedCacheTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(eastmoney.cache, "DATA_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

QUOTE_PAYLOAD = {
    "rc": 0,
    "data": {
        "f43": 4038, "f44": 4084, "f45": 4032, "f46": 4050,
        "f47": 12765805, "f48": 5183304239.0, "f57": "510300",
        "f58": "沪深300ETF华泰柏瑞", "f59": 3, "f60": 4020,
        "f86": 1795502133, "f169": 18, "f170": 45,
    },
}

KLINE_PAYLOAD = {
    "rc": 0,
    "data": {
        "code": "510300",
        "name": "沪深300ETF华泰柏瑞",
        "klines": [
            "2025-11-03,4.629,4.640,4.644,4.582,7759881,3674194550.000,1.34,0.15,0.007,1.40",
            "2025-11-04,4.637,4.606,4.650,4.583,12015243,5708778783.000,1.44,-0.73,-0.034,2.16",
            "2025-11-24,4.456,4.434,4.462,4.410,11557477,5269730484.000,1.17,-0.16,-0.007,2.08",
        ],
    },
}


class FakeResponse:
    def __init__(self, text):
        self.text = text.encode("utf-8")

    def read(self):
        return self.text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class QuoteTest(IsolatedCacheTest):
    def test_get_quote_510300_fields(self):
        with patch.object(eastmoney, "_request_json", return_value=QUOTE_PAYLOAD) as request:
            result = eastmoney.get_quote("510300")
        self.assertEqual(request.call_args.args[0], eastmoney.QUOTE_URL)
        self.assertEqual(request.call_args.args[1]["secid"], "1.510300")
        self.assertEqual(result["code"], "510300")
        self.assertEqual(result["name"], "沪深300ETF华泰柏瑞")
        self.assertEqual(result["latest"], 4.038)
        self.assertEqual(result["high"], 4.084)
        self.assertEqual(result["low"], 4.032)
        self.assertEqual(result["volume"], 12765805)
        self.assertEqual(result["amount"], 5183304239.0)
        self.assertEqual(result["timestamp"], "2026-11-24T14:35:33+08:00")

    def test_get_quote_two_decimal_stock(self):
        payload = {"rc": 0, "data": {"f43": 150000, "f44": 151000,
                                     "f45": 149000, "f59": 2, "f57": "600519"}}
        with patch.object(eastmoney, "_request_json", return_value=payload):
            result = eastmoney.get_quote("600519")
        self.assertEqual(result["latest"], 1500.0)
        self.assertEqual(result["high"], 1510.0)
        self.assertIsNone(result["amount"])

    def test_get_quote_upstream_error(self):
        with patch.object(eastmoney, "_request_json", return_value={"rc": -1, "data": None}):
            with self.assertRaises(eastmoney.QuoteError):
                eastmoney.get_quote("510300")

    def test_market_mapping(self):
        self.assertEqual(eastmoney.to_secid("510300"), "1.510300")
        self.assertEqual(eastmoney.to_secid("600519"), "1.600519")
        self.assertEqual(eastmoney.to_secid("000001"), "0.000001")
        self.assertEqual(eastmoney.to_secid("159919"), "0.159919")
        with self.assertRaises(ValueError):
            eastmoney.to_secid("abc")
        with self.assertRaises(ValueError):
            eastmoney.to_secid("5103001")

    def test_jsonp_response_is_parsed(self):
        text = 'jQuery123({"rc":0,"data":{"f43":100}});'
        with patch.object(eastmoney, "urlopen", return_value=FakeResponse(text)):
            result = eastmoney._request_json(eastmoney.QUOTE_URL, {})
        self.assertEqual(result, {"rc": 0, "data": {"f43": 100}})

    def test_network_error_becomes_quote_error(self):
        with patch.object(eastmoney, "urlopen", side_effect=URLError("boom")):
            with self.assertRaises(eastmoney.QuoteError):
                eastmoney._request_json(eastmoney.QUOTE_URL, {})


class HistoryTest(IsolatedCacheTest):
    def test_get_history_parses_klines_and_params(self):
        with patch.object(eastmoney, "_request_json", return_value=KLINE_PAYLOAD) as request:
            result = eastmoney.get_history("510300", "20251101", "20251124")
        params = request.call_args.args[1]
        self.assertEqual(request.call_args.args[0], eastmoney.KLINE_URL)
        self.assertEqual(params["secid"], "1.510300")
        self.assertEqual(params["beg"], "20251101")
        self.assertEqual(params["end"], "20251124")
        self.assertEqual(params["klt"], 101)
        self.assertEqual(params["fqt"], 1)
        self.assertEqual(result["count"], 3)
        first = result["records"][0]
        self.assertEqual(first["date"], "2025-11-03")
        self.assertEqual(first["close"], 4.64)
        self.assertEqual(first["high"], 4.644)
        self.assertEqual(first["low"], 4.582)
        self.assertEqual(first["volume"], 7759881)
        self.assertEqual(first["amount"], 3674194550.0)
        self.assertEqual(first["pct_change"], 0.15)
        self.assertEqual(result["records"][-1]["date"], "2025-11-24")

    def test_date_normalization(self):
        with patch.object(eastmoney, "_request_json", return_value=KLINE_PAYLOAD) as request:
            eastmoney.get_history("510300", "2025-11-01", "2025-11-24")
        self.assertEqual(request.call_args.args[1]["beg"], "20251101")
        self.assertEqual(request.call_args.args[1]["end"], "20251124")

    def test_invalid_range_and_options(self):
        with self.assertRaises(ValueError):
            eastmoney.get_history("510300", "20251124", "20251101")
        with self.assertRaises(ValueError):
            eastmoney.get_history("510300", "2025-11-31", "20251124")
        with self.assertRaises(ValueError):
            eastmoney.get_history("510300", "20250101", "20250102", period=999)
        with self.assertRaises(ValueError):
            eastmoney.get_history("510300", "20250101", "20250102", adjust=3)

    def test_force_refetch_ignores_existing_cache(self):
        eastmoney.cache.write_history("510300", {
            "code": "510300", "start": "20251101", "end": "20251124",
            "period": 101, "adjust": 1, "count": 1,
            "records": [{"date": "2025-11-24", "close": 1.0}],
        })
        with patch.object(eastmoney, "_request_json", return_value=KLINE_PAYLOAD) as request:
            result = eastmoney.get_history(
                "510300", "20251101", "20251124", force=True
            )
        self.assertEqual(result["source"], "eastmoney")
        self.assertEqual(result["count"], 3)
        request.assert_called_once()

    def test_save_range_writes_query_dates(self):
        with patch.object(eastmoney, "_request_json", return_value=KLINE_PAYLOAD):
            eastmoney.get_history("510300", "20251101", "20251124", save_range=True)
        stored = json.loads(eastmoney.cache.cache_path("510300").read_text(encoding="utf-8"))
        self.assertEqual(stored["data"]["query_begin_time"], "2025-11-01")
        self.assertEqual(stored["data"]["query_end_time"], "2025-11-24")

    def test_minute_period(self):
        with patch.object(eastmoney, "_request_json", return_value=KLINE_PAYLOAD) as request:
            eastmoney.get_history("510300", "20251124", "20251124", period=5, adjust=0)
        self.assertEqual(request.call_args.args[1]["klt"], 5)
        self.assertEqual(request.call_args.args[1]["fqt"], 0)


class UnifiedEntrypointTest(unittest.TestCase):
    def test_without_range_uses_quote(self):
        with patch.object(eastmoney, "get_quote", return_value={"kind": "quote"}) as quote, \
                patch.object(eastmoney, "get_history") as history:
            result = eastmoney.get_stock_data("510300")
        self.assertEqual(result, {"kind": "quote"})
        quote.assert_called_once_with("510300")
        history.assert_not_called()

    def test_with_range_uses_history(self):
        with patch.object(eastmoney, "get_history", return_value={"kind": "history"}) as history, \
                patch.object(eastmoney, "get_quote") as quote:
            result = eastmoney.get_stock_data("510300", "20251101", "20251124")
        self.assertEqual(result, {"kind": "history"})
        history.assert_called_once_with("510300", "20251101", "20251124", 101, 1)
        quote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
