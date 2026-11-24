# stock_ai

基于东方财富公开行情接口，查询单只 A 股 / ETF 的当日行情与历史 K 线。仅依赖 Python 3.9+ 标准库。

## 启动服务

```bash
python3 -m stock_ai.server --host 127.0.0.1 --port 8000
```

## 网页看板

启动服务后访问 `http://127.0.0.1:8000/`：

- 左侧 10% 为菜单：`ETF` / `个股` 两级，标的来自 `data/etf`、`data/stock` 下的 JSON 文件。
- 右侧 90% 为详情：顶部横向排列开始日期、结束日期、更新、日线、周线、月线、年线。
- 工具栏下方是 ECharts K 线图（含成交量副图），高度由 `static/style.css` 的 `--chart-height` 控制，建议值 `450px`；图表按时间从左到右递增，表格仍为最新日期在最上。
- 图表默认显示最近 330 根，窗口上限也是 330 根；支持鼠标左右拖动和底部滑块平移查看更早数据。
- 主图叠加 30 日均线和 60 日均线（橙色 MA30、紫色 MA60），始终基于日线收盘价计算；周/月/年视图取该周期最后一个交易日对应的均线值。
- 主图高度占可用区域 75%，量能附图占 25%，两者间隔 24px；量能柱按当日涨跌着色（红涨绿跌）。
- 横轴日期标签放在主图底部，附图下方不再显示；只在虚线位置显示日期：日线 `YYYY-MM-DD`（每 20 个交易日）、周线 `YYYY-MM`（每 20 周）、月线 `YYYY-MM`（每 12 个月）、年线 `YYYY`（每年）。
- 鼠标悬浮框顶部始终显示对应记录的完整日期。
- 图表下方左侧为数据列表（60% 宽），右侧为网格策略面板（40% 宽，与列表等高）。

## 网格策略

- `设置网格`：输入网格标的（默认当前标的）、开始日期、底仓份数、税佣金（默认 5 元）、基准价（默认取开始日期开盘价）、网格份额、涨跌触发百分比。保存后写入对应缓存文件的顶层 `grid_settings`；再次打开或切换标的时会自动读取。
- `模拟网格`：从开始日期起按 开盘 → 最高 → 最低 → 收盘 顺序模拟；触发网格按触发价成交并更新基准价，持仓归零即结束。未模拟时显示“无模拟交易记录”。
- 交易记录列：交易日期、交易类型、成交价格、交易份额、最新持仓、持仓成本（该笔成交后的持仓平均成本）、持仓收益（该笔成交后按“现金 + 持仓市值 - 初始金额”计算的最终收益）。
- `模拟统计`：输出初始仓位/金额、最大持仓/金额、交易周期、税佣金合计、最终收益额、交易次数（合计/买入/卖出）、月平均交易次数等；若最新持仓大于 0，额外输出当前成本。

接口：`/api/grid/simulate?code=&start=&base_shares=&grid_shares=&up_pct=&down_pct=&fee=&base_price=`。
- 表格头取自缓存的 `kline_title`，内容取自 `kline_records`，支持上下滚动。
- `static/echarts.min.js` 为本地内置的 ECharts 5.5.1（Apache-2.0），无需外网。
- 点击标的会用缓存中的 `data.query_begin_time` / `data.query_end_time` 自动填充开始/结束日期；默认按日线倒序展示。
- 周/月/年线由本地日线聚合生成，同样倒序展示。
- `更新` 按日期范围强制调用 `get_history`（`refresh=1`，忽略缓存），并通过 `save_range=1` 把当前范围写回缓存；抓取后刷新表格，显示自动关闭的进度对话框。

新增接口：`/api/symbols`（菜单）、`/api/cache?code=`（原始缓存）、`/api/aggregate?code=&period=day|week|month|year`（聚合）。

## HTTP 接口

| 路径 | 参数 | 说明 |
| --- | --- | --- |
| `/api/quote` | `code`（必填） | 当日实时行情：最新、最高、最低、总手、金额等 |
| `/api/history` | `code`（必填），`start`、`end`（可选），`period`、`adjust`（可选） | 时间范围内的历史 K 线 |
| `/api/stock` | 同上 | 统一入口：无时间范围走实时行情，有则走历史 K 线 |
| `/health` | 无 | 健康检查 |

- `code`：6 位代码，如 `510300`、`600519`、`000001`。
- `start` / `end`：`YYYYMMDD` 或 `YYYY-MM-DD`；缺省分别为 `19900101` 和今天。
- `period`：`1/5/15/30/60` 分钟、`101` 日（默认）、`102` 周、`103` 月。
- `adjust`：`0` 不复权、`1` 前复权（默认）、`2` 后复权。

示例：

```bash
curl 'http://127.0.0.1:8000/api/quote?code=510300'
curl 'http://127.0.0.1:8000/api/history?code=510300&start=20251101&end=20251124'
curl 'http://127.0.0.1:8000/api/stock?code=510300&start=2025-11-01&end=2025-11-24'
```

`/api/quote` 返回示例：

```json
{
  "code": "510300",
  "name": "沪深300ETF华泰柏瑞",
  "latest": 4.038,
  "high": 4.084,
  "low": 4.032,
  "open": 4.05,
  "prev_close": 4.02,
  "change": 0.018,
  "pct_change": 0.045,
  "volume": 12765805,
  "amount": 5183304239.0,
  "timestamp": "2026-11-24T14:35:33+08:00",
  "source": "eastmoney"
}
```

其中 `volume` 单位为“手”，`amount` 单位为“元”，价格按东方财富返回的小数位数动态缩放。

## 本地缓存

缓存文件按代码类型存放：`data/etf/510300.json`、`data/stock/600519.json`。

- 调用接口时**优先读缓存**；缓存命中时 `source` 为 `cache`，不发起网络请求。
- 缓存不存在或请求范围在本地无数据时，才抓取东方财富，并把抓取结果**回写**到同一文件（原子写入，保留已有内容）。
- 默认日线、前复权数据统一累积在 `data.kline_records`：新增记录按 `date` 追加，同日期以新抓取值覆盖，整体按日期排序。历史查询按 `start`/`end` 过滤；当日行情取最后一条记录。
- 兼容已有的东财风格文件：`{"data": {"code": ..., "name": ..., "klines": [...]}}`（允许尾随逗号）；旧格式首次回写时会转换为 `kline_records`。
- 非默认周期/复权的数据仍存到 `history`，以 `period:adjust:start:end` 为键；当日实时行情存到 `quote` 键。
- 可通过环境变量 `STOCK_AI_DATA_DIR` 指定其它缓存目录。

如需强制刷新某段日线，删掉 `kline_records` 中对应日期的记录即可；刷新其它周期则删掉 `history` 中对应键。

## Python 直接调用

```python
from stock_ai import get_quote, get_history, get_stock_data

print(get_quote("510300"))
print(get_history("510300", "2026-11-01", "2026-11-23"))
print(get_stock_data("510300"))
```

## 测试

```bash
python3 -m unittest discover -s tests -t . -v
```
