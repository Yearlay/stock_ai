import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stock_ai import cache, eastmoney

LEGACY_CACHE = {
    "data": {
        "code": "510300",
        "name": "沪深300ETF华泰柏瑞",
        "kline_title": ["日期", "开盘价", "收盘价", "最高价", "最低价", "成交量", "成交额"],
        "klines": [
            "2025-11-03,4.629,4.640,4.644,4.582,7759881,3674194550.000,1.34,0.15,0.007,1.40",
            "2025-11-04,4.637,4.606,4.650,4.583,12015243,5708778783.000,1.44,-0.73,-0.034,2.16",
            "2025-11-24,4.456,4.434,4.462,4.410,11557477,5269730484.000,1.17,-0.16,-0.007,2.08",
        ],
    },
}

RECORDS_CACHE = {
    "data": {
        "code": "510300",
        "name": "沪深300ETF华泰柏瑞",
        "kline_records": [
            {"date": "2026-11-02", "open": 4.084, "close": 4.085, "high": 4.12,
             "low": 4.065, "volume": 29514531, "amount": 12066215573.0,
             "amplitude": 1.35, "pct_change": 0.49, "change": 0.02, "turnover_rate": 5.31},
            {"date": "2026-11-03", "open": 4.076, "close": 4.092, "high": 4.106,
             "low": 4.041, "volume": 46539654, "amount": 19007473545.0,
             "amplitude": 1.59, "pct_change": 0.17, "change": 0.007, "turnover_rate": 8.37},
            {"date": "2026-11-23", "open": 3.997, "close": 4.023, "high": 4.045,
             "low": 3.976, "volume": 13939903, "amount": 5589278193.0,
             "amplitude": 1.72, "pct_change": 0.12, "change": 0.005, "turnover_rate": 2.51},
        ],
    },
}

QUOTE_PAYLOAD = {
    "rc": 0,
    "data": {
        "f43": 4038, "f44": 4084, "f45": 4032, "f47": 12765805,
        "f48": 5183304239.0, "f57": "510300", "f58": "沪深300ETF华泰柏瑞",
        "f59": 3, "f86": 1795502133,
    },
}

KLINE_PAYLOAD = {
    "rc": 0,
    "data": {
        "code": "510300",
        "name": "沪深300ETF华泰柏瑞",
        "klines": LEGACY_CACHE["data"]["klines"],
    },
}

NEW_KLINE_PAYLOAD = {
    "rc": 0,
    "data": {
        "code": "510300",
        "name": "沪深300ETF华泰柏瑞",
        "klines": [
            "2026-11-23,3.990,4.030,4.050,3.980,14000000,5600000000.000,1.75,0.17,0.007,2.52",
            "2026-11-24,4.030,4.100,4.120,4.010,15000000,6100000000.000,2.68,1.74,0.070,2.70",
        ],
    },
}


class CachePathTest(unittest.TestCase):
    def test_path_by_code_type(self):
        self.assertEqual(cache.cache_path("510300").name, "510300.json")
        self.assertEqual(cache.cache_path("510300").parent.name, "etf")
        self.assertEqual(cache.cache_path("513130").parent.name, "etf")
        self.assertEqual(cache.cache_path("600519").parent.name, "stock")
        self.assertEqual(cache.cache_path("510300").suffix, ".json")


class CacheReadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(cache, "DATA_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = cache.cache_path("510300")

    def write_payload(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def write_legacy(self):
        self.write_payload(LEGACY_CACHE)

    def write_records(self):
        self.write_payload(RECORDS_CACHE)

    def test_read_records_history(self):
        self.write_records()
        result = cache.read_history("510300", "20261101", "20261123", 101, 1)
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["records"][0]["date"], "2026-11-02")
        self.assertEqual(result["records"][-1]["close"], 4.023)

    def test_read_records_filters_range(self):
        self.write_records()
        result = cache.read_history("510300", "20261101", "20261102", 101, 1)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["date"], "2026-11-02")

    def test_read_records_miss_outside_range(self):
        self.write_records()
        self.assertIsNone(cache.read_history("510300", "20251201", "20251231", 101, 1))

    def test_read_records_quote_from_last_record(self):
        self.write_records()
        result = cache.read_quote("510300")
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["date"], "2026-11-23")
        self.assertEqual(result["latest"], 4.023)
        self.assertEqual(result["high"], 4.045)
        self.assertEqual(result["low"], 3.976)
        self.assertEqual(result["volume"], 13939903)
        self.assertEqual(result["amount"], 5589278193.0)

    def test_read_legacy_still_supported(self):
        self.write_legacy()
        result = cache.read_history("510300", "20251101", "20251124", 101, 1)
        self.assertEqual(result["count"], 3)
        self.assertEqual(cache.read_quote("510300")["latest"], 4.434)

    def test_trailing_comma_json_is_accepted(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            '{"data":{"code":"510300","klines":['
            '"2025-11-24,4.4,4.5,4.6,4.3,100,1000.0,1.0,0.1,0.01,1.0",]}}',
            encoding="utf-8",
        )
        self.assertEqual(cache.read_quote("510300")["latest"], 4.5)

    def test_missing_empty_and_broken_cache(self):
        self.assertIsNone(cache.read_quote("510300"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self.assertIsNone(cache.read_quote("510300"))
        self.path.write_text("{broken", encoding="utf-8")
        self.assertIsNone(cache.read_history("510300", "20251101", "20251124", 101, 1))

    def test_write_query_range(self):
        self.write_records()
        cache.write_query_range("510300", "20251124", "20261124")
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["data"]["query_begin_time"], "2025-11-24")
        self.assertEqual(stored["data"]["query_end_time"], "2026-11-24")
        self.assertEqual(len(stored["data"]["kline_records"]), 3)

    def test_write_quote_preserves_records(self):
        self.write_records()
        cache.write_quote("510300", {"code": "510300", "latest": 9.9})
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(stored["data"]["kline_records"]), 3)
        self.assertEqual(stored["quote"]["latest"], 9.9)
        self.assertEqual(cache.read_quote("510300")["latest"], 9.9)

    def test_write_history_appends_and_dedupes_records(self):
        self.write_records()
        result = {"code": "510300", "start": "20261123", "end": "20261124",
                  "period": 101, "adjust": 1, "count": 2,
                  "records": [
                      {"date": "2026-11-23", "close": 4.03},
                      {"date": "2026-11-24", "close": 4.10},
                  ]}
        cache.write_history("510300", result)
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        records = stored["data"]["kline_records"]
        self.assertEqual([r["date"] for r in records],
                         ["2026-11-02", "2026-11-03", "2026-11-23", "2026-11-24"])
        self.assertEqual(records[2]["close"], 4.03)
        self.assertEqual(stored["data"]["source"], "eastmoney")
        self.assertNotIn("history", stored)

    def test_write_history_other_options_use_history_key(self):
        self.write_records()
        result = {"code": "510300", "start": "20261123", "end": "20261124",
                  "period": 5, "adjust": 0, "count": 1,
                  "records": [{"date": "2026-11-23 10:30", "close": 4.03}]}
        cache.write_history("510300", result)
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("5:0:20261123:20261124", stored["history"])
        self.assertEqual(len(stored["data"]["kline_records"]), 3)

    def test_write_history_creates_records_for_new_file(self):
        result = {"code": "510300", "start": "20261124", "end": "20261124",
                  "period": 101, "adjust": 1, "count": 1,
                  "records": [{"date": "2026-11-24", "close": 4.10}]}
        cache.write_history("510300", result)
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["data"]["code"], "510300")
        self.assertEqual(stored["data"]["kline_title"], cache.KLINE_TITLE)
        self.assertEqual(stored["data"]["source"], "eastmoney")
        self.assertEqual(stored["data"]["query_begin_time"], "2026-11-24")
        self.assertEqual(stored["data"]["query_end_time"], "2026-11-24")
        self.assertEqual(stored["data"]["kline_records"][0]["close"], 4.10)


class CacheIntegrationTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(cache, "DATA_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = cache.cache_path("510300")

    def write_payload(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def write_records(self):
        self.write_payload(RECORDS_CACHE)

    def test_quote_hit_does_not_call_network(self):
        self.write_records()
        with patch.object(eastmoney, "_request_json", side_effect=AssertionError("不应联网")):
            result = eastmoney.get_quote("510300")
        self.assertEqual(result["latest"], 4.023)
        self.assertEqual(result["source"], "cache")

    def test_history_hit_does_not_call_network(self):
        self.write_records()
        with patch.object(eastmoney, "_request_json", side_effect=AssertionError("不应联网")):
            result = eastmoney.get_history("510300", "2026-11-01", "2026-11-23")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["source"], "cache")

    def test_quote_miss_fetches_and_writes_then_hits_cache(self):
        with patch.object(eastmoney, "_request_json", return_value=QUOTE_PAYLOAD) as request:
            first = eastmoney.get_quote("510300")
        self.assertEqual(first["latest"], 4.038)
        request.assert_called_once()
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["quote"]["latest"], 4.038)

        with patch.object(eastmoney, "_request_json", side_effect=AssertionError("不应联网")):
            second = eastmoney.get_quote("510300")
        self.assertEqual(second["latest"], 4.038)
        self.assertEqual(second["source"], "cache")

    def test_history_miss_fetches_appends_records_then_hits_cache(self):
        self.write_records()
        with patch.object(eastmoney, "_request_json", return_value=NEW_KLINE_PAYLOAD) as request:
            first = eastmoney.get_history("510300", "2026-11-24", "2026-11-24")
        self.assertEqual(first["count"], 2)
        request.assert_called_once()

        stored = json.loads(self.path.read_text(encoding="utf-8"))
        dates = [r["date"] for r in stored["data"]["kline_records"]]
        self.assertEqual(dates, ["2026-11-02", "2026-11-03", "2026-11-23", "2026-11-24"])

        with patch.object(eastmoney, "_request_json", side_effect=AssertionError("不应联网")):
            second = eastmoney.get_history("510300", "2026-11-01", "2026-11-24")
        self.assertEqual(second["count"], 4)
        self.assertEqual(second["source"], "cache")
        self.assertEqual(second["records"][-1]["close"], 4.10)


if __name__ == "__main__":
    unittest.main()
