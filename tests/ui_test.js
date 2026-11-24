const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const file = path.join(__dirname, "..", "static", "app.js");
const sandbox = {};
vm.runInNewContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
const ui = sandbox.StockUI;

assert.ok(ui, "StockUI 未导出");
assert.equal(ui.FIELD_KEYS.join(","), [
  "date", "open", "close", "high", "low", "volume",
  "amount", "amplitude", "pct_change", "change", "turnover_rate",
].join(","));
assert.equal(ui.formatCell("close", null), "-");
assert.equal(ui.formatCell("close", undefined), "-");
assert.equal(ui.formatCell("date", "2026-11-02"), "2026-11-02");
assert.equal(ui.formatCell("volume", 1234567), "1,234,567");
assert.equal(ui.formatCell("amount", 5183304239), "5,183,304,239");
assert.equal(ui.formatCell("close", 4.084), "4.084");
assert.equal(
  ui.buildUpdateUrl("510300", "20251124", "20261124", true, true),
  "/api/history?code=510300&start=20251124&end=20261124&refresh=1&save_range=1"
);
assert.equal(
  ui.buildUpdateUrl("510300", "20251124", "20261124", false, false),
  "/api/history?code=510300&start=20251124&end=20261124"
);
assert.equal(
  ui.queryRange({ query_begin_time: "2025-11-24", query_end_time: "2026-11-24" }).join(","),
  "2025-11-24,2026-11-24"
);
assert.equal(ui.queryRange({}).join(","), ",");
assert.equal(
  ui.gridUrl({ code: "510300", start: "2026-11-02", base_shares: 50,
    grid_shares: 50, up_pct: 1, down_pct: 2, fee: 5, base_price: 4.1 }),
  "/api/grid/simulate?code=510300&start=2026-11-02&base_shares=50" +
  "&grid_shares=50&up_pct=1&down_pct=2&fee=5&base_price=4.1"
);

const chart = ui.chartData([
  { date: "2026-01-02", period_label: "2026-W01", open: 10, close: 12,
    low: 9, high: 13, volume: 100, ma30: 11, ma60: 12,
    month_start: true, month_label: "2026-01" },
  { date: "2026-01-05", open: 12, close: 11, low: 10, high: 13,
    volume: 200, ma30: 13 },
  { date: "bad", open: null, close: 1, low: 0, high: 2, volume: 1 },
], "day");
assert.equal(chart.categories.join(","), "2026-01-05,2026-W01");
assert.equal(chart.dates.join(","), "2026-01-05,2026-01-02");
assert.equal(chart.labels.join(","), ",2026-01-02");
assert.equal(chart.axisMarkIndices.join(","), "1");
assert.equal(chart.candles[0].join(","), "12,11,10,13");
assert.equal(chart.volumes.join(","), "200,100");
assert.equal(chart.ma30.join(","), "13,11");
assert.equal(chart.ma60.join(","), ",12");
assert.equal(chart.volumeBars[0].itemStyle.color, "#16a34a");
assert.equal(chart.volumeBars[1].itemStyle.color, "#dc2626");
assert.equal(ui.volumeColor({ pct_change: 1 }), "#dc2626");
assert.equal(ui.volumeColor({ pct_change: -1 }), "#16a34a");
assert.equal(ui.volumeColor({ pct_change: 0 }), "#94a3b8");
assert.equal(ui.volumeColor({ open: 10, close: 11 }), "#dc2626");

const many = [];
for (let i = 1; i <= 21; i += 1) {
  many.push({
    date: "2026-01-" + String(i).padStart(2, "0"),
    open: 1, close: 1, low: 1, high: 1, volume: 1,
  });
}
const dayAxis = ui.chartData(many, "day");
assert.equal(dayAxis.axisMarkIndices.join(","), "0,20");
assert.equal(dayAxis.labels[0], "2026-01-21");
assert.equal(dayAxis.labels[1], "");
assert.equal(dayAxis.labels[20], "2026-01-01");
assert.equal(ui.markStep("week"), 20);
assert.equal(ui.markStep("month"), 12);
assert.equal(ui.markStep("year"), 1);
assert.equal(ui.axisDateLabel("2026-01-21", "week"), "2026-01");
assert.equal(ui.axisDateLabel("2026", "year"), "2026");

const layout = ui.chartLayout(450, 24, 0.75);
assert.equal(layout.mainTop, 28);
assert.equal(layout.mainHeight.toFixed(1), "280.5");
assert.equal(layout.volumeHeight.toFixed(1), "93.5");
assert.equal(layout.volumeTop.toFixed(1), (28 + 280.5 + 24).toFixed(1));
assert.equal(layout.gap, 24);

const zoomAll = ui.chartZoom(700, 330);
assert.equal(zoomAll.start.toFixed(3), "52.857");
assert.equal(zoomAll.end, 100);
assert.equal(zoomAll.maxValueSpan, 330);
const zoomFew = ui.chartZoom(100, 330);
assert.equal(zoomFew.start, 0);
assert.equal(zoomFew.minValueSpan, 20);
assert.equal(zoomFew.maxValueSpan, 330);

const rows = ui.buildRows(ui.DEFAULT_TITLE, [{
  date: "2026-11-02", open: 4.084, close: null, volume: 1234567,
}]);
assert.equal(rows.length, 1);
assert.equal(rows[0].length, ui.DEFAULT_TITLE.length);
assert.equal(rows[0][0], "2026-11-02");
assert.equal(rows[0][1], "4.084");
assert.equal(rows[0][2], "-");
assert.equal(rows[0][5], "1,234,567");

console.log("ui_test OK");
