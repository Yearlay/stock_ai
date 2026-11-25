(function (root) {
  "use strict";

  const FIELD_KEYS = [
    "date", "open", "close", "high", "low", "volume",
    "amount", "amplitude", "pct_change", "change", "turnover_rate",
  ];
  const DEFAULT_TITLE = [
    "日期", "开盘价", "收盘价", "最高价", "最低价", "成交量",
    "成交额", "振幅", "涨跌幅", "涨跌额", "换手率",
  ];

  function formatCell(key, value) {
    if (value === null || value === undefined || value === "") return "-";
    if (typeof value === "number" && !Number.isFinite(value)) return "-";
    if (key === "volume" || key === "amount") {
      return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
    }
    if (typeof value === "number") {
      return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
    }
    return String(value);
  }

  function buildRows(title, records) {
    const keys = title && title.length === FIELD_KEYS.length
      ? title.map(function (_, index) { return FIELD_KEYS[index]; })
      : FIELD_KEYS;
    return (records || []).map(function (record) {
      return keys.map(function (key) {
        return formatCell(key, record ? record[key] : null);
      });
    });
  }

  function volumeColor(record) {
    if (!record) return "#94a3b8";
    const change = typeof record.pct_change === "number"
      ? record.pct_change
      : (Number(record.close) || 0) - (Number(record.open) || 0);
    if (change > 0) return "#dc2626";
    if (change < 0) return "#16a34a";
    return "#94a3b8";
  }

  const MARK_STEPS = { day: 20, week: 20, month: 12, year: 1 };

  function markStep(period) {
    return MARK_STEPS[period] || 20;
  }

  function axisDateLabel(date, period) {
    const text = String(date || "");
    if (period === "day") return text.slice(0, 10);
    if (period === "week" || period === "month") return text.slice(0, 7);
    return text.slice(0, 4);
  }

  function chartData(records, period) {
    const rows = (records || []).filter(function (record) {
      return record && record.open !== null && record.open !== undefined &&
        record.close !== null && record.close !== undefined &&
        record.low !== null && record.low !== undefined &&
        record.high !== null && record.high !== undefined;
    }).reverse();
    const step = markStep(period);
    const lastIndex = rows.length - 1;
    const axisMarkIndices = [];
    const labels = rows.map(function (record, index) {
      if ((lastIndex - index) % step !== 0) return "";
      axisMarkIndices.push(index);
      return axisDateLabel(record.date, period);
    });
    return {
      categories: rows.map(function (record) {
        return record.period_label || record.date || "";
      }),
      dates: rows.map(function (record) {
        return record.date || "";
      }),
      labels: labels,
      axisMarkIndices: axisMarkIndices,
      candles: rows.map(function (record) {
        return [record.open, record.close, record.low, record.high];
      }),
      volumes: rows.map(function (record) {
        return record.volume || 0;
      }),
      volumeBars: rows.map(function (record) {
        return {
          value: record.volume || 0,
          itemStyle: { color: volumeColor(record) },
        };
      }),
      ma30: rows.map(function (record) {
        return record.ma30 === undefined || record.ma30 === null ? null : record.ma30;
      }),
      ma60: rows.map(function (record) {
        return record.ma60 === undefined || record.ma60 === null ? null : record.ma60;
      }),
    };
  }

  function chartLayout(height, gap, ratio) {
    const totalHeight = height || 450;
    const spacing = gap === undefined ? 24 : gap;
    const mainRatio = ratio === undefined ? 0.75 : ratio;
    const topReserve = 28;
    const sliderReserve = 24;
    const usable = Math.max(120, totalHeight - topReserve - sliderReserve - spacing);
    const mainHeight = usable * mainRatio;
    const volumeHeight = usable - mainHeight;
    return {
      mainTop: topReserve,
      mainHeight: mainHeight,
      volumeTop: topReserve + mainHeight + spacing,
      volumeHeight: volumeHeight,
      gap: spacing,
    };
  }

  function visibleRange(candles, startPct, endPct) {
    const list = candles || [];
    const start = Math.max(0, Math.floor((startPct || 0) / 100 * list.length));
    const end = Math.min(
      list.length,
      Math.ceil(((endPct === undefined ? 100 : endPct) / 100) * list.length)
    );
    let high = null;
    let low = null;
    list.slice(start, end).forEach(function (candle) {
      if (!candle) return;
      if (candle[3] !== null && candle[3] !== undefined && (high === null || candle[3] > high)) {
        high = candle[3];
      }
      if (candle[2] !== null && candle[2] !== undefined && (low === null || candle[2] < low)) {
        low = candle[2];
      }
    });
    return { high: high, low: low };
  }

  function chartZoom(total, limit) {
    const maxBars = limit || 330;
    const size = Math.min(total, maxBars);
    return {
      start: total > size ? (total - size) / total * 100 : 0,
      end: 100,
      minValueSpan: Math.min(20, size),
      maxValueSpan: maxBars,
    };
  }

  function addSymbolUrl(code, start, end) {
    return "/api/symbols/add?code=" + encodeURIComponent(code) +
      "&start=" + encodeURIComponent(start) +
      "&end=" + encodeURIComponent(end);
  }

  function gridUrl(settings) {
    const pairs = [
      ["code", settings.code],
      ["start", settings.start],
      ["base_shares", settings.base_shares],
      ["grid_shares", settings.grid_shares],
      ["up_pct", settings.up_pct],
      ["down_pct", settings.down_pct],
      ["fee", settings.fee],
      ["base_price", settings.base_price],
    ];
    return "/api/grid/simulate?" + pairs.map(function (pair) {
      return encodeURIComponent(pair[0]) + "=" + encodeURIComponent(pair[1]);
    }).join("&");
  }

  function buildUpdateUrl(code, start, end, force, saveRange) {
    return "/api/history?code=" + encodeURIComponent(code) +
      "&start=" + encodeURIComponent(start) +
      "&end=" + encodeURIComponent(end) +
      (force ? "&refresh=1" : "") +
      (saveRange ? "&save_range=1" : "");
  }

  function queryRange(symbol) {
    return [
      symbol && symbol.query_begin_time ? symbol.query_begin_time : "",
      symbol && symbol.query_end_time ? symbol.query_end_time : "",
    ];
  }

  function suggestedGridValues(low, high) {
    const bottom = Number(low);
    const top = Number(high);
    if (!Number.isFinite(bottom) || !Number.isFinite(top) || bottom <= 0 || top <= bottom) {
      return null;
    }
    const basePrice = Number((bottom + (top - bottom) * 0.382).toFixed(3));
    const gridShares = Math.floor(5000 / basePrice / 100) * 100;
    if (gridShares <= 0) return null;
    const baseShares = gridShares * 5;
    const percent = (((top - bottom) / bottom) / 20 * 100).toFixed(2);
    return {
      base_price: basePrice.toFixed(3),
      grid_shares: gridShares,
      base_shares: baseShares,
      up_pct: percent,
      down_pct: percent,
    };
  }

  root.StockUI = {
    FIELD_KEYS: FIELD_KEYS,
    DEFAULT_TITLE: DEFAULT_TITLE,
    formatCell: formatCell,
    buildRows: buildRows,
    chartData: chartData,
    markStep: markStep,
    axisDateLabel: axisDateLabel,
    volumeColor: volumeColor,
    chartLayout: chartLayout,
    chartZoom: chartZoom,
    visibleRange: visibleRange,
    suggestedGridValues: suggestedGridValues,
    gridUrl: gridUrl,
    addSymbolUrl: addSymbolUrl,
    buildUpdateUrl: buildUpdateUrl,
    queryRange: queryRange,
  };

  if (typeof document === "undefined") return;

  const state = {
    code: "", name: "", period: "day",
    gridSettings: null, gridResult: null, deleteTarget: null,
  };
  const byId = function (id) { return document.getElementById(id); };
  let chart = null;
  let rangeHandler = null;

  function dateText(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function setStatus(text, isError) {
    const node = byId("status");
    node.textContent = text || "";
    node.className = isError ? "status error" : "status";
  }

  async function fetchJson(url) {
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || ("HTTP " + response.status));
    }
    return payload;
  }

  function renderChart(payload) {
    const node = byId("chart");
    if (typeof echarts === "undefined") {
      node.className = "chart chart-empty";
      node.textContent = "图表组件未加载";
      return;
    }
    const data = chartData(payload.records, payload.period);
    state.candles = data.candles;
    if (!chart) chart = echarts.init(node);
    node.className = "chart";
    if (!data.categories.length) {
      chart.clear();
      return;
    }
    const zoom = chartZoom(data.categories.length, 330);
    const layout = chartLayout(node.clientHeight, 24, 0.75);
    chart.setOption({
      animation: false,
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      legend: {
        data: ["MA30", "MA60"], top: 0, right: 24,
        itemWidth: 12, textStyle: { fontSize: 10 },
      },
      grid: [
        { left: 64, right: 24, top: layout.mainTop, height: layout.mainHeight },
        { left: 64, right: 24, top: layout.volumeTop, height: layout.volumeHeight },
      ],
      dataZoom: [
        {
          type: "inside", xAxisIndex: [0, 1],
          start: zoom.start, end: zoom.end,
          minValueSpan: zoom.minValueSpan, maxValueSpan: zoom.maxValueSpan,
          zoomOnMouseWheel: false, moveOnMouseMove: true, moveOnMouseWheel: true,
        },
        {
          type: "slider", xAxisIndex: [0, 1],
          start: zoom.start, end: zoom.end,
          minValueSpan: zoom.minValueSpan, maxValueSpan: zoom.maxValueSpan,
          bottom: 6, height: 18,
          borderColor: "#e2e8f0",
          fillerColor: "rgba(37, 99, 235, 0.12)",
          handleStyle: { color: "#2563eb" },
        },
      ],
      xAxis: [
        {
          type: "category", data: data.dates, gridIndex: 0,
          axisLabel: {
            interval: 0, fontSize: 10, hideOverlap: true,
            formatter: function (value, index) {
              return data.labels[index] || "";
            },
          },
          axisTick: { show: false },
        },
        {
          type: "category", data: data.dates, gridIndex: 1,
          axisLabel: { show: false }, axisTick: { show: false },
        },
      ],
      yAxis: [
        {
          scale: true, gridIndex: 0,
          splitLine: { lineStyle: { color: "#f1f5f9" } },
        },
        {
          scale: true, gridIndex: 1, splitNumber: 2,
          axisLabel: {
            fontSize: 10,
            formatter: function (value) {
              return value >= 10000 ? Math.round(value / 10000) + "万" : value;
            },
          },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: "K线", type: "candlestick", data: data.candles,
          xAxisIndex: 0, yAxisIndex: 0,
          itemStyle: {
            color: "#dc2626", color0: "#16a34a",
            borderColor: "#dc2626", borderColor0: "#16a34a",
          },
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: "#cbd5e1", type: "dashed", width: 1 },
            data: data.axisMarkIndices.map(function (index) {
              return { xAxis: index };
            }),
          },
        },
        {
          name: "MA30", type: "line", data: data.ma30,
          xAxisIndex: 0, yAxisIndex: 0,
          showSymbol: false, connectNulls: false,
          lineStyle: { width: 1.2, color: "#f59e0b" },
          itemStyle: { color: "#f59e0b" },
        },
        {
          name: "MA60", type: "line", data: data.ma60,
          xAxisIndex: 0, yAxisIndex: 0,
          showSymbol: false, connectNulls: false,
          lineStyle: { width: 1.2, color: "#8b5cf6" },
          itemStyle: { color: "#8b5cf6" },
        },
        {
          name: "成交量", type: "bar", data: data.volumeBars,
          xAxisIndex: 1, yAxisIndex: 1,
          itemStyle: { color: "#94a3b8" },
        },
      ],
    }, true);

    function updateRangeLabels() {
      const option = chart.getOption();
      const zoom = (option.dataZoom && option.dataZoom[0]) || {};
      const range = visibleRange(
        data.candles,
        zoom.start === undefined ? 0 : zoom.start,
        zoom.end === undefined ? 100 : zoom.end
      );
      chart.setOption({
        graphic: [
          {
            type: "text", left: 72, top: 34, silent: true,
            style: {
              text: "区间最高: " + (range.high === null ? "-" : range.high),
              fill: "#dc2626", font: "12px sans-serif",
            },
          },
          {
            type: "text", left: 72, top: 52, silent: true,
            style: {
              text: "区间最低: " + (range.low === null ? "-" : range.low),
              fill: "#16a34a", font: "12px sans-serif",
            },
          },
        ],
      });
    }

    if (rangeHandler) chart.off("datazoom", rangeHandler);
    rangeHandler = updateRangeLabels;
    chart.on("datazoom", rangeHandler);
    updateRangeLabels();
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || ("HTTP " + response.status));
    }
    return body;
  }

  function render(payload, label) {
    const title = payload.kline_title || DEFAULT_TITLE;
    const records = payload.records || [];
    byId("title").textContent = state.name
      ? state.name + " (" + state.code + ")"
      : (payload.code || "行情");
    byId("meta").textContent = [
      label,
      records.length + " 条",
      payload.period || "",
      payload.source || "",
    ].filter(Boolean).join(" · ");

    const head = byId("thead");
    const body = byId("tbody");
    head.innerHTML = "";
    body.innerHTML = "";

    const headRow = document.createElement("tr");
    title.forEach(function (text) {
      const th = document.createElement("th");
      th.textContent = text;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);

    const rows = buildRows(title, records);
    rows.forEach(function (cells, rowIndex) {
      const tr = document.createElement("tr");
      cells.forEach(function (text, columnIndex) {
        const td = document.createElement("td");
        td.textContent = text;
        const key = FIELD_KEYS[columnIndex];
        const raw = records[rowIndex] ? records[rowIndex][key] : null;
        if (key === "pct_change" && typeof raw === "number") {
          td.className = raw < 0 ? "down" : (raw > 0 ? "up" : "");
        }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    renderChart(payload);
  }

  function setActivePeriod(period) {
    document.querySelectorAll(".period").forEach(function (button) {
      button.classList.toggle("active", button.dataset.period === period);
    });
  }

  async function loadPeriod(period) {
    if (!state.code) {
      setStatus("请先选择标的", true);
      return;
    }
    state.period = period;
    setActivePeriod(period);
    setStatus("加载中...");
    try {
      const payload = await fetchJson(
        "/api/aggregate?code=" + encodeURIComponent(state.code) +
        "&period=" + encodeURIComponent(period)
      );
      render(payload, period.toUpperCase());
      setStatus("");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function setProgress(text, percent) {
    byId("progressText").textContent = text;
    byId("progressBar").style.width = percent + "%";
  }

  function showProgress(text) {
    byId("progressDialog").hidden = false;
    setProgress(text, 5);
  }

  function hideProgress() {
    byId("progressDialog").hidden = true;
  }

  async function updateFromRange() {
    if (!state.code) {
      setStatus("请先选择标的", true);
      return;
    }
    const startDisplay = byId("startDate").value;
    const endDisplay = byId("endDate").value;
    const start = startDisplay.replace(/-/g, "");
    const end = endDisplay.replace(/-/g, "");
    if (!start || !end) {
      setStatus("请选择开始和结束日期", true);
      return;
    }

    showProgress("正在请求 " + startDisplay + " ~ " + endDisplay + " 的数据...");
    let timer = setInterval(function () {
      const bar = byId("progressBar");
      const current = parseFloat(bar.style.width) || 5;
      if (current < 88) bar.style.width = Math.min(88, current + 7) + "%";
    }, 180);

    try {
      const payload = await fetchJson(
        buildUpdateUrl(state.code, start, end, true, true)
      );
      setProgress("已抓取 " + (payload.records || []).length + " 条，正在合并缓存...", 92);
      await loadPeriod(state.period || "day");
      setProgress("更新完成", 100);
      setStatus("已更新 " + startDisplay + " ~ " + endDisplay);
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      clearInterval(timer);
      timer = null;
      setTimeout(hideProgress, 250);
    }
  }

  function closeSymbolMenus() {
    document.querySelectorAll(".symbol-menu").forEach(function (node) {
      node.classList.remove("open");
    });
  }

  function selectSymbol(symbol, row) {
    state.code = symbol.code;
    state.name = symbol.name;
    loadSavedGridSettings(symbol.code);
    loadGridResult(symbol.code);
    const range = queryRange(symbol);
    if (range[0]) byId("startDate").value = range[0];
    if (range[1]) byId("endDate").value = range[1];
    document.querySelectorAll(".symbol-row").forEach(function (node) {
      node.classList.toggle("active", node === row);
    });
    loadPeriod("day");
  }

  function openDeleteDialog(symbol) {
    state.deleteTarget = symbol;
    byId("deleteMessage").textContent = "确认删除 " + symbol.code +
      " (" + symbol.name + ") 的本地缓存吗？";
    byId("deleteDialog").hidden = false;
  }

  function renderMenu(groups) {
    const menu = byId("menu");
    menu.innerHTML = "";
    groups.forEach(function (group) {
      const section = document.createElement("div");
      section.className = "group";
      const heading = document.createElement("div");
      heading.className = "group-title";
      heading.textContent = group.label + " (" + group.symbols.length + ")";
      section.appendChild(heading);

      group.symbols.forEach(function (symbol) {
        const row = document.createElement("div");
        row.className = "symbol-row";
        row.dataset.code = symbol.code;

        const button = document.createElement("button");
        button.className = "symbol";
        button.type = "button";
        button.dataset.code = symbol.code;
        const code = document.createElement("span");
        code.className = "code";
        code.textContent = symbol.code;
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = symbol.name;
        button.appendChild(code);
        button.appendChild(name);
        button.addEventListener("click", function () {
          closeSymbolMenus();
          selectSymbol(symbol, row);
        });

        const more = document.createElement("button");
        more.className = "symbol-more";
        more.type = "button";
        more.textContent = "⋯";
        more.title = "更多操作";
        more.addEventListener("click", function (event) {
          event.stopPropagation();
          const menuNode = row.querySelector(".symbol-menu");
          const willOpen = !menuNode.classList.contains("open");
          closeSymbolMenus();
          menuNode.classList.toggle("open", willOpen);
        });

        const menuNode = document.createElement("div");
        menuNode.className = "symbol-menu";
        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.textContent = "删除";
        deleteButton.addEventListener("click", function (event) {
          event.stopPropagation();
          closeSymbolMenus();
          openDeleteDialog(symbol);
        });
        menuNode.appendChild(deleteButton);

        row.appendChild(button);
        row.appendChild(more);
        row.appendChild(menuNode);
        section.appendChild(row);
      });
      menu.appendChild(section);
    });
  }

  function renderGridTable(headers, rows, append) {
    const container = byId("gridContent");
    if (!append) container.innerHTML = "";
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    headers.forEach(function (text) {
      const th = document.createElement("th");
      th.textContent = text;
      th.title = text;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    const body = document.createElement("tbody");
    rows.forEach(function (cells) {
      const tr = document.createElement("tr");
      cells.forEach(function (value) {
        const td = document.createElement("td");
        td.textContent = value === null || value === undefined ? "-" : value;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    container.appendChild(table);
  }

  function renderGridTrades(result, append) {
    const container = byId("gridContent");
    const trades = result.trades || [];
    if (!trades.length) {
      if (!append) container.textContent = "无模拟交易记录";
      return;
    }
    renderGridTable(
      ["交易日期", "交易类型", "成交价格", "交易份额", "最新持仓", "持仓成本", "持仓收益"],
      trades.map(function (trade) {
        return [
          trade.date, trade.type, trade.price, trade.shares, trade.holdings,
          trade.holding_cost, trade.profit,
        ];
      }),
      append
    );
  }

  async function loadGridResult(code) {
    if (!code) {
      byId("gridContent").textContent = "无模拟交易记录";
      return;
    }
    try {
      const result = await fetchJson(
        "/api/grid/result?code=" + encodeURIComponent(code)
      );
      state.gridResult = result.trades && result.trades.length ? result : null;
      renderGridTrades(result, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function renderGridStats(result) {
    const container = byId("statsContent");
    container.innerHTML = "";
    const stats = result.stats || {};
    const lines = [
      "初始仓位: " + stats.initial_position,
      "初始金额: " + stats.initial_amount,
      "最大持仓: " + stats.max_position,
      "最大持仓金额: " + stats.max_position_amount,
      "交易周期: " + stats.period_days + " 天",
      "税佣金合计: " + stats.fee_total,
      "最终收益额: " + stats.final_profit,
      "交易次数: 合计" + stats.trade_count + "次；买入" +
        stats.buy_count + "次；卖出" + stats.sell_count + "次",
      "月平均交易次数: " + stats.avg_trades_per_month + "次",
    ];
    if (stats.current_cost !== null && stats.current_cost !== undefined) {
      lines.push("当前成本: " + stats.current_cost);
    }
    lines.push("网格结束日期: " + stats.end_date);
    container.textContent = lines.join("\n");
    byId("statsDialog").hidden = false;
  }

  async function fillGridBasePrice(code, start) {
    if (!code || !start) return;
    try {
      const payload = await fetchJson("/api/cache?code=" + encodeURIComponent(code));
      const records = payload.records || [];
      const record = records.find(function (item) { return item.date === start; }) ||
        records.find(function (item) { return item.date >= start; });
      if (record && record.open !== null && record.open !== undefined) {
        byId("gridBasePrice").value = record.open;
      }
    } catch (error) {
      byId("gridBasePrice").value = "";
    }
  }

  function fillGridForm(settings) {
    byId("gridCode").value = settings.code || "";
    byId("gridStart").value = settings.start || "";
    byId("gridBaseShares").value = settings.base_shares;
    byId("gridFee").value = settings.fee;
    byId("gridBasePrice").value = settings.base_price;
    byId("gridShare").value = settings.grid_shares;
    byId("gridUpPct").value = settings.up_pct;
    byId("gridDownPct").value = settings.down_pct;
  }

  function applySuggestedGrid() {
    const option = chart && typeof chart.getOption === "function" ? chart.getOption() : null;
    const zoom = (option && option.dataZoom && option.dataZoom[0]) || {};
    const range = visibleRange(
      state.candles,
      zoom.start === undefined ? 0 : zoom.start,
      zoom.end === undefined ? 100 : zoom.end
    );
    const values = range ? suggestedGridValues(range.low, range.high) : null;
    if (!values) {
      setStatus("当前K线区间无法计算建议值", true);
      return;
    }
    byId("gridBasePrice").value = values.base_price;
    byId("gridShare").value = values.grid_shares;
    byId("gridBaseShares").value = values.base_shares;
    byId("gridUpPct").value = values.up_pct;
    byId("gridDownPct").value = values.down_pct;
    setStatus("已填入建议参数，点击保存后生效");
  }

  async function loadSavedGridSettings(code) {
    try {
      state.gridSettings = await fetchJson(
        "/api/grid/settings?code=" + encodeURIComponent(code)
      );
    } catch (error) {
      state.gridSettings = null;
    }
  }

  async function openGridDialog() {
    byId("gridDialog").hidden = false;
    if (!state.code) return;
    try {
      const saved = await fetchJson(
        "/api/grid/settings?code=" + encodeURIComponent(state.code)
      );
      if (saved) {
        fillGridForm(saved);
        setStatus("已读取保存的网格策略");
        return;
      }
    } catch (error) {
      // 读取失败时使用默认值
    }
    fillGridForm({
      code: state.code,
      start: byId("startDate").value,
      base_shares: 1000,
      grid_shares: 100,
      up_pct: 1,
      down_pct: 1,
      fee: 5,
      base_price: "",
    });
    fillGridBasePrice(state.code, byId("startDate").value);
  }

  async function saveGridSettings(event) {
    event.preventDefault();
    const settings = {
      code: byId("gridCode").value.trim(),
      start: byId("gridStart").value,
      base_shares: byId("gridBaseShares").value,
      fee: byId("gridFee").value,
      base_price: byId("gridBasePrice").value,
      grid_shares: byId("gridShare").value,
      up_pct: byId("gridUpPct").value,
      down_pct: byId("gridDownPct").value,
    };
    try {
      const saved = await postJson("/api/grid/settings", settings);
      state.gridSettings = saved;
      state.gridResult = null;
      byId("gridDialog").hidden = true;
      byId("gridContent").textContent = "无模拟交易记录";
      setStatus("网格参数已保存");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function runGridSimulation(showStats) {
    if (!state.gridSettings) {
      setStatus("请先设置网格", true);
      return;
    }
    try {
      const result = await fetchJson(gridUrl(state.gridSettings));
      state.gridResult = result;
      if (showStats) renderGridStats(result);
      else await loadGridResult(state.gridSettings.code);
      setStatus("");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  function openAddDialog() {
    byId("addError").textContent = "";
    byId("addDialog").hidden = false;
  }

  async function submitAddSymbol(event) {
    event.preventDefault();
    const code = byId("addCode").value.trim();
    const start = byId("startDate").value.replace(/-/g, "");
    const end = byId("endDate").value.replace(/-/g, "");
    byId("addError").textContent = "";
    try {
      await fetchJson(addSymbolUrl(code, start, end));
      byId("addDialog").hidden = true;
      renderMenu(await fetchJson("/api/symbols"));
      const button = document.querySelector('.symbol[data-code="' + code + '"]');
      if (button) button.click();
      setStatus("已添加 " + code);
    } catch (error) {
      byId("addError").textContent = "输入的标的代码错误，请重新输入";
    }
  }

  async function confirmDeleteSymbol() {
    const target = state.deleteTarget;
    if (!target) return;
    try {
      await postJson("/api/symbols/delete", { code: target.code });
      byId("deleteDialog").hidden = true;
      if (state.code === target.code) {
        state.code = "";
        state.name = "";
        state.gridSettings = null;
        state.gridResult = null;
        byId("title").textContent = "请选择标的";
        byId("meta").textContent = "";
        byId("thead").innerHTML = "";
        byId("tbody").innerHTML = "";
        byId("gridContent").textContent = "无模拟交易记录";
        if (chart) chart.clear();
      }
      state.deleteTarget = null;
      renderMenu(await fetchJson("/api/symbols"));
      setStatus("已删除 " + target.code);
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  async function init() {
    const end = new Date();
    const start = new Date();
    start.setFullYear(start.getFullYear() - 1);
    byId("endDate").value = dateText(end);
    byId("startDate").value = dateText(start);

    byId("updateBtn").addEventListener("click", updateFromRange);
    const chartToggle = byId("chartToggle");
    chartToggle.addEventListener("click", function () {
      const chartPanel = byId("chart");
      const collapsed = !chartPanel.hidden;
      chartPanel.hidden = collapsed;
      chartToggle.classList.toggle("collapsed", collapsed);
      chartToggle.title = collapsed ? "展开K线" : "收起K线";
      chartToggle.setAttribute("aria-label", chartToggle.title);
      if (!collapsed && chart) chart.resize();
    });
    byId("addSymbolBtn").addEventListener("click", openAddDialog);
    byId("addCancel").addEventListener("click", function () {
      byId("addDialog").hidden = true;
    });
    byId("addForm").addEventListener("submit", submitAddSymbol);
    byId("deleteConfirm").addEventListener("click", confirmDeleteSymbol);
    byId("deleteCancel").addEventListener("click", function () {
      byId("deleteDialog").hidden = true;
      state.deleteTarget = null;
    });
    document.addEventListener("click", function (event) {
      if (!event.target.closest(".symbol-more") &&
          !event.target.closest(".symbol-menu")) {
        closeSymbolMenus();
      }
    });
    byId("gridSettingsBtn").addEventListener("click", openGridDialog);
    byId("gridSuggestBtn").addEventListener("click", applySuggestedGrid);
    byId("gridCancel").addEventListener("click", function () {
      byId("gridDialog").hidden = true;
    });
    byId("gridForm").addEventListener("submit", saveGridSettings);
    byId("gridSimulateBtn").addEventListener("click", function () {
      runGridSimulation(false);
    });
    byId("gridStatsBtn").addEventListener("click", function () {
      runGridSimulation(true);
    });
    byId("statsClose").addEventListener("click", function () {
      byId("statsDialog").hidden = true;
    });
    window.addEventListener("resize", function () {
      if (chart) chart.resize();
    });
    document.querySelectorAll(".period").forEach(function (button) {
      button.addEventListener("click", function () {
        loadPeriod(button.dataset.period);
      });
    });

    try {
      renderMenu(await fetchJson("/api/symbols"));
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})(typeof globalThis !== "undefined" ? globalThis : this);
