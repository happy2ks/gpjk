"""
市场快报生成器。

从多个数据源获取金融数据（利率、国债、加密货币、全球指数），
生成格式化的市场快报文本。

数据源：
    - OFR / FRED: SOFR、EFFR 利率
    - Trading Economics: 美国10年国债收益率
    - Binance API: BTC/USDT 行情
    - Yahoo Finance: 全球指数（KOSPI、日经225、台湾加权、恒生）
"""

import functools
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="market_report.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BINANCE_BASE_URL = "https://data-api.binance.vision/api/v3"
BTC_SYMBOL = "BTCUSDT"

# Yahoo Finance 全球指数映射
INDEX_SYMBOLS = {
    "韩国 KOSPI": "^KS11",
    "日本 日经225": "^N225",
    "台湾 加权指数": "^TWII",
    "恒生 恒生指数": "^HSI",
}

# 网络请求通用配置
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # 秒


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def retry_on_network_error(func):
    """网络请求重试装饰器，在请求异常时自动重试（最多 MAX_RETRIES 次）。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt <= MAX_RETRIES:
                    logging.warning(f"{func.__name__} 第{attempt}次失败，{RETRY_DELAY}s后重试: {e}")
                    time.sleep(RETRY_DELAY)
        logging.error(f"{func.__name__} 重试{MAX_RETRIES + 1}次后仍然失败: {last_error}")
        return None

    return wrapper


# ---------------------------------------------------------------------------
# 利率数据（OFR / FRED）
# ---------------------------------------------------------------------------
SERIES_MAPPING = {
    "secured-overnight-financing-rate-sofr": "SOFR",
    "effective-federal-funds-rate": "EFFR",
    "sofr": "SOFR",
    "effr": "EFFR",
}


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame | None:
    """将 OFR 返回的 DataFrame 标准化为 ['date', 'value'] 两列格式。"""
    date_cols = [col for col in df.columns if "date" in col.lower()]
    date_col = date_cols[0] if date_cols else df.columns[0]

    value_cols = [col for col in df.columns if col != date_col]
    value_col = value_cols[0] if value_cols else None
    if not value_col:
        logging.warning("标准化 DataFrame 失败：未找到值列")
        return None

    df = df[[date_col, value_col]].copy()
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "value"])
    return df if not df.empty else None


def _get_fred_data(fred_code: str) -> pd.DataFrame | None:
    """从 FRED 获取利率数据（OFR 的降级方案）。"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_code}"
    try:
        df = pd.read_csv(url)
        date_cols = [col for col in df.columns if "date" in col.lower()]
        date_col = date_cols[0] if date_cols else df.columns[0]
        value_cols = [col for col in df.columns if col.upper() == fred_code or "value" in col.lower()]
        value_col = value_cols[0] if value_cols else df.columns[1]

        df = df[[date_col, value_col]].copy()
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
        df = df.sort_values("date").tail(30)

        if df.empty:
            logging.warning(f"从 FRED 获取 {fred_code} 成功但数据为空")
            return None
        logging.info(f"从 FRED 获取 {fred_code} 成功")
        return df
    except Exception as e:
        logging.error(f"从 FRED 获取 {fred_code} 失败: {e}")
        return None


def fetch_ofr_data(series_code: str) -> pd.DataFrame | None:
    """从 OFR API 获取利率数据，失败时自动 fallback 到 FRED。"""
    url = f"https://www.financialresearch.gov/short-term-funding-monitor/api/series/timeseries/{series_code}.csv"
    try:
        df = pd.read_csv(url)
        df = _normalize_dataframe(df)
        if df is not None:
            df = df.sort_values("date").tail(5)
            logging.info(f"从 OFR 获取 {series_code} 成功")
            return df
        else:
            logging.warning(f"从 OFR 获取 {series_code} 成功但标准化后数据为空")
    except Exception as e:
        logging.warning(f"从 OFR 获取 {series_code} 失败: {e}")

    if series_code in SERIES_MAPPING and SERIES_MAPPING[series_code] is not None:
        fred_code = SERIES_MAPPING[series_code]
        logging.info(f"尝试从 FRED 获取 {fred_code} 作为 {series_code} 的替代")
        return _get_fred_data(fred_code)
    return None


# ---------------------------------------------------------------------------
# 美国10年国债收益率（Trading Economics）
# ---------------------------------------------------------------------------
def _fetch_te_page(url: str) -> str | None:
    """从 Trading Economics 获取页面 HTML。"""
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def _find_data_table(soup: BeautifulSoup):
    """在 BeautifulSoup 解析结果中查找目标数据表格。"""
    table_classes = [
        "table table-hover sortable-theme-minimal table-striped table-heatmap",
        "table table-hover table-striped",
        "table table-hover",
        "table",
    ]
    for cls in table_classes:
        table = soup.find("table", class_=cls)
        if table:
            return table
    return None


def _find_column_index(headers: list[str], target_aliases: list[str]) -> int:
    """在表头列表中查找目标列的索引。"""
    for i, header in enumerate(headers):
        for alias in target_aliases:
            if alias in header:
                return i
    # 回退：查找包含非 ASCII 字符的列（可能是乱码）
    for i, header in enumerate(headers):
        if header and any(ord(c) > 127 for c in header):
            return i
    return -1


def _find_target_row(rows, symbol: str = "USGG10YR:IND"):
    """在表格行中查找包含目标 data-symbol 的行。"""
    for row in rows:
        if row.get("data-symbol") == symbol:
            return row
    # 回退：文本匹配
    for row in rows:
        row_text = row.get_text()
        if "USGG10YR" in row_text or "10-Year" in row_text or "10年" in row_text:
            logging.info(f"通过文本匹配找到目标行: {row_text[:50]}...")
            return row
    return None


def _extract_cell_value(cells, col_index: int) -> float | None:
    """从行单元格中提取数值。"""
    if len(cells) <= col_index:
        return None

    cell = cells[col_index]
    text = cell.get_text(strip=True)
    if not text:
        return None

    # 方法1：移除非法字符后转换
    cleaned = re.sub(r"[^\d.-]", "", text)
    if cleaned:
        try:
            return float(cleaned)
        except ValueError:
            pass

    # 方法2：去除 % 符号后转换
    try:
        return float(text.replace("%", "").strip())
    except ValueError:
        return None


def _extract_date(cells) -> str:
    """从行单元格中提取日期字符串。"""
    # 查找 id="date" 的单元格
    for cell in cells:
        if cell.get("id") == "date":
            text = cell.get_text(strip=True)
            if text:
                return text

    # 回退：最后一列为日期
    if cells:
        last_text = cells[-1].get_text(strip=True)
        if last_text and "-" in last_text:
            return last_text

    return datetime.now().strftime("%Y-%m-%d")


@retry_on_network_error
def get_us_10y_yield() -> dict | None:
    """
    从 Trading Economics 获取美国10年国债收益率。

    Returns:
        {'yield': float, 'date': str} 或 None
    """
    url = "https://zh.tradingeconomics.com/united-states/10-year-tips-yield"
    html = _fetch_te_page(url)
    soup = BeautifulSoup(html, "html.parser")

    # 查找表格
    table = _find_data_table(soup)
    if not table:
        logging.warning("未找到目标表格")
        return None

    # 解析表头，定位"收益率"列
    thead = table.find("thead")
    if not thead:
        logging.warning("表格没有表头")
        return None

    header_rows = thead.find_all("tr")
    if not header_rows:
        logging.warning("表格没有表头行")
        return None

    headers = [th.get_text(strip=True) for th in header_rows[-1].find_all(["th", "td"])]
    yield_col = _find_column_index(
        headers,
        ["收益率", "Yield", "YIELD", "收益", "利率", "Interest Rate", "Price", "price", "Last"],
    )
    if yield_col == -1:
        yield_col = 1 if len(headers) > 1 else -1
    if yield_col == -1:
        logging.warning(f"未找到收益率列，可用列名: {headers}")
        return None

    # 查找数据行
    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")
    if tbody and thead:
        # 跳过表头行
        header_count = len(header_rows)
        rows = rows[header_count:] if len(rows) > header_count else rows
    if not rows:
        logging.warning("没有找到数据行")
        return None

    # 定位目标行
    target_row = _find_target_row(rows)
    if not target_row:
        logging.warning("未找到 data-symbol='USGG10YR:IND' 的行")
        # 调试输出前几行
        for i, row in enumerate(rows[:5]):
            cells = row.find_all(["td", "th"])
            row_data = {f"col{j}": c.get_text(strip=True)[:30] for j, c in enumerate(cells[:3])}
            logging.warning(f"行 {i + 1}: {row_data}")
        return None

    # 提取数据
    cells = target_row.find_all(["td", "th"])
    yield_value = _extract_cell_value(cells, yield_col)

    # 回退：尝试 id="p" 单元格
    if yield_value is None:
        p_cell = target_row.find("td", id="p")
        if p_cell:
            yield_value = _extract_cell_value([p_cell], 0)
            if yield_value is not None:
                logging.info(f"通过 id='p' 找到收益率: {yield_value}")

    if yield_value is None:
        logging.warning("无法提取收益率值")
        return None

    date_value = _extract_date(cells)
    logging.info(f"成功获取美国10年国债收益率: {yield_value}%")
    return {"yield": yield_value, "date": date_value}


# ---------------------------------------------------------------------------
# BTC/USDT（Binance）
# ---------------------------------------------------------------------------
@retry_on_network_error
def get_btc_stats() -> dict | None:
    """
    获取 BTC/USDT 24小时统计数据。

    Returns:
        {'price', 'change', 'change_pct', 'high', 'low', 'volume', 'quote_vol'} 或 None
    """
    resp = requests.get(
        f"{BINANCE_BASE_URL}/ticker/24hr",
        params={"symbol": BTC_SYMBOL},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "price": float(data["lastPrice"]),
        "change": float(data["priceChange"]),
        "change_pct": float(data["priceChangePercent"]),
        "high": float(data["highPrice"]),
        "low": float(data["lowPrice"]),
        "volume": float(data["volume"]),
        "quote_vol": float(data["quoteVolume"]),
    }


# ---------------------------------------------------------------------------
# 全球指数（Yahoo Finance）
# ---------------------------------------------------------------------------
@retry_on_network_error
def get_index_data(yahoo_symbol: str, label: str) -> dict | None:
    """
    从 Yahoo Finance 获取全球指数最新行情。

    Returns:
        {'label', 'symbol', 'price', 'change', 'change_pct', 'date'} 或 None
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=5d"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    result = data["chart"]["result"][0]
    quotes = result["indicators"]["quote"][0]
    timestamps = result["timestamp"]

    closes = quotes["close"]
    valid_data = [(ts, close) for ts, close in zip(timestamps, closes) if close is not None]

    if len(valid_data) < 2:
        logging.warning(f"获取指数 {label} ({yahoo_symbol}) 数据不足")
        return None

    latest_ts, latest_close = valid_data[-1]
    _, prev_close = valid_data[-2]

    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100
    latest_date = datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d")

    return {
        "label": label,
        "symbol": yahoo_symbol,
        "price": latest_close,
        "change": change,
        "change_pct": change_pct,
        "date": latest_date,
    }


# ---------------------------------------------------------------------------
# 数据获取编排
# ---------------------------------------------------------------------------
def _fetch_all_data() -> dict:
    """
    并发获取所有数据源。

    Returns:
        {
            'sofr_data': DataFrame|None,
            'effr_data': DataFrame|None,
            'us_10y_yield': dict|None,
            'btc_stats': dict|None,
            'index_data': {label: dict|None, ...},
        }
    """
    results = {}

    # 将指数获取拆分为独立任务以最大化并发
    index_tasks = {
        label: (get_index_data, yahoo_symbol, label)
        for label, yahoo_symbol in INDEX_SYMBOLS.items()
    }

    # 构建任务列表：利率、国债、BTC、指数
    tasks = {
        "sofr_data": (fetch_ofr_data, "secured-overnight-financing-rate-sofr"),
        "effr_data": (fetch_ofr_data, "effective-federal-funds-rate"),
        "us_10y_yield": (get_us_10y_yield,),
        "btc_stats": (get_btc_stats,),
    }
    for label, task_info in index_tasks.items():
        tasks[f"index_{label}"] = task_info

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {}
        for task_key, task_info in tasks.items():
            func, *args = task_info
            future = executor.submit(func, *args)
            future_map[future] = task_key

        for future in as_completed(future_map):
            task_key = future_map[future]
            try:
                results[task_key] = future.result()
            except Exception as e:
                logging.error(f"并发任务 {task_key} 异常: {e}")
                results[task_key] = None

    # 将指数结果整理回嵌套字典
    index_data = {}
    for label in INDEX_SYMBOLS:
        index_data[label] = results.pop(f"index_{label}", None)

    results["index_data"] = index_data
    return results


# ---------------------------------------------------------------------------
# 报告格式化
# ---------------------------------------------------------------------------
def _format_report(data: dict) -> str:
    """
    根据数据字典生成格式化的市场快报文本。

    Args:
        data: _fetch_all_data() 返回的字典

    Returns:
        格式化后的报告字符串
    """
    sofr_data: pd.DataFrame | None = data["sofr_data"]
    effr_data: pd.DataFrame | None = data["effr_data"]
    us_10y_yield: dict | None = data["us_10y_yield"]
    btc_stats: dict | None = data["btc_stats"]
    index_data: dict = data["index_data"]

    lines = []
    lines.append("=" * 50)
    lines.append("         市场快报")
    lines.append("=" * 50)
    lines.append(f"报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # --- 利率市场 ---
    lines.append("--- 利率市场 ---")

    sofr_value = None
    effr_value = None

    if sofr_data is not None and not sofr_data.empty:
        latest_sofr = sofr_data.iloc[-1]
        sofr_date = latest_sofr["date"].strftime("%Y-%m-%d")
        sofr_value = float(latest_sofr["value"])
        lines.append(f"SOFR 利率 ({sofr_date}): {sofr_value:.4f}%")
    else:
        lines.append("SOFR 利率: 数据不可用")

    if effr_data is not None and not effr_data.empty:
        latest_effr = effr_data.iloc[-1]
        effr_date = latest_effr["date"].strftime("%Y-%m-%d")
        effr_value = float(latest_effr["value"])
        lines.append(f"EFFR 利率 ({effr_date}): {effr_value:.4f}%")
    else:
        lines.append("EFFR 利率: 数据不可用")

    if sofr_value is not None and effr_value is not None:
        spread = sofr_value - effr_value
        lines.append(f"利差 (SOFR - EFFR): {spread:.4f}%")
        if spread > 0.10:
            lines.append("[预警] 利差 > 0.10%，融资基差异常，流动性可能收紧")
    else:
        lines.append("利差 (SOFR - EFFR): 数据不足无法计算")

    lines.append("")

    # --- 国债市场 ---
    lines.append("--- 国债市场 ---")

    us_10y_value = None
    if us_10y_yield is not None:
        us_10y_value = us_10y_yield["yield"]
        us_10y_date = us_10y_yield["date"]
        lines.append(f"美国10年国债收益率 ({us_10y_date}): {us_10y_value:.2f}%")
    else:
        lines.append("美国10年国债收益率: 数据不可用")

    lines.append("")

    # --- 加密货币市场 ---
    lines.append("--- 加密货币市场 ---")

    if btc_stats is not None:
        arrow = "▲" if btc_stats["change"] >= 0 else "▼"
        lines.append(f"BTC/USDT 当前价格: ${btc_stats['price']:,.2f}")
        lines.append(
            f"24小时涨跌幅: {arrow} {btc_stats['change_pct']:+.2f}% "
            f"({btc_stats['change']:+,.2f} USDT)"
        )
    else:
        lines.append("BTC/USDT: 数据不可用")

    lines.append("")

    # --- 全球指数 ---
    lines.append("--- 全球指数 ---")

    for label in INDEX_SYMBOLS:
        idx = index_data.get(label)
        if idx is not None:
            arrow = "▲" if idx["change"] >= 0 else "▼"
            lines.append(
                f"{idx['label']} ({idx['date']}): {idx['price']:,.2f}  "
                f"{arrow} {idx['change_pct']:+.2f}%"
            )
        else:
            lines.append(f"{label}: 数据不可用")

    lines.append("")
    lines.append("=" * 50)

    return "\n".join(lines)


def _log_report(data: dict) -> None:
    """记录市场快报生成日志。"""
    btc_stats = data.get("btc_stats")
    us_10y_yield = data.get("us_10y_yield")
    index_data: dict = data.get("index_data", {})

    sofr_data: pd.DataFrame | None = data.get("sofr_data")
    effr_data: pd.DataFrame | None = data.get("effr_data")

    sofr_str = f"{float(sofr_data.iloc[-1]['value']):.4f}" if sofr_data is not None and not sofr_data.empty else "N/A"
    effr_str = f"{float(effr_data.iloc[-1]['value']):.4f}" if effr_data is not None and not effr_data.empty else "N/A"
    us10y_str = f"{us_10y_yield['yield']:.2f}" if us_10y_yield else "N/A"
    btc_str = f"${btc_stats['price']:,.2f}" if btc_stats else "N/A"

    index_parts = [
        f"{label}={idx['price']:,.2f}" if idx else f"{label}=N/A"
        for label, idx in index_data.items()
    ]

    logging.info(
        f"市场快报生成成功: SOFR={sofr_str}, "
        f"EFFR={effr_str}, "
        f"美国10年国债={us10y_str}%, "
        f"BTC价格={btc_str}, "
        f"指数={{{', '.join(index_parts)}}}"
    )


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def generate_market_report() -> None:
    """生成并打印市场快报。"""
    print(f"开始生成市场快报... [{datetime.now()}]")

    data = _fetch_all_data()
    report = _format_report(data)
    print(report)

    _log_report(data)


def main() -> int:
    try:
        generate_market_report()
    except Exception as e:
        logging.error(f"生成市场快报时发生错误: {e}")
        print(f"错误: {e}")
        return 1
    return 0


if __name__ == "__main__":
    main()
