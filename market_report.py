import warnings
warnings.filterwarnings("ignore")
import requests
import pandas as pd
import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup

# 配置日志记录（可选）
logging.basicConfig(
    filename='market_report.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Binance API 配置（参考 btc_price.py）
BINANCE_BASE_URL = "https://data-api.binance.vision/api/v3"
BTC_SYMBOL = "BTCUSDT"

# OFR/FRED 系列代码映射（参考 repo_monitor.py）
SERIES_MAPPING = {
    "secured-overnight-financing-rate-sofr": "SOFR",
    "effective-federal-funds-rate": "EFFR",
    "sofr": "SOFR",
    "effr": "EFFR"
}

# 全球指数映射（Yahoo Finance 符号）
INDEX_SYMBOLS = {
    "韩国 KOSPI": "^KS11",
    "日本 日经225": "^N225",
    "台湾 加权指数": "^TWII",
    "恒生 恒生指数": "^HSI",
}

def fetch_interest_rate_data(series_code):
    """
    从多个数据源获取利率数据（SOFR 或 EFFR）
    1. 首先尝试OFR API
    2. 如果失败且有FRED映射，尝试从FRED获取
    参考 repo_monitor.py 中的 fetch_ofr_data 函数
    """
    # 首先尝试OFR
    url = f"https://www.financialresearch.gov/short-term-funding-monitor/api/series/timeseries/{series_code}.csv"
    try:
        df = pd.read_csv(url)
        # 查找日期列
        date_cols = [col for col in df.columns if 'date' in col.lower()]
        date_col = date_cols[0] if date_cols else df.columns[0]

        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(date_col).tail(5)  # 取最新5天

        # 查找值列（排除日期列）
        value_cols = [col for col in df.columns if col != date_col]
        value_col = value_cols[0] if value_cols else None

        if not value_col:
            logging.warning(f"从OFR获取 {series_code}: 未找到值列")
            return None

        # 重命名列为统一格式
        df = df[[date_col, value_col]].copy()
        df.columns = ['date', 'value']

        # 转换值列为数值类型
        df['value'] = pd.to_numeric(df['value'], errors='coerce')

        # 移除NaN值
        df = df.dropna(subset=['date', 'value'])

        if df.empty:
            logging.warning(f"从OFR获取 {series_code} 成功但数据为空")
            return None

        logging.info(f"从OFR获取 {series_code} 成功")
        return df
    except Exception as e:
        logging.warning(f"从OFR获取 {series_code} 失败: {e}")

        # 尝试从FRED获取（如果有映射）
        if series_code in SERIES_MAPPING and SERIES_MAPPING[series_code] is not None:
            fred_code = SERIES_MAPPING[series_code]
            logging.info(f"尝试从FRED获取 {fred_code} 作为 {series_code} 的替代")
            return get_fred_data(fred_code)

        return None

def get_fred_data(fred_code):
    """从FRED获取数据（替代OFR数据源）"""
    try:
        # 直接下载CSV
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_code}"
        df = pd.read_csv(url)

        # 查找日期列和值列
        date_cols = [col for col in df.columns if 'date' in col.lower()]
        date_col = date_cols[0] if date_cols else df.columns[0]

        # 查找值列
        value_cols = [col for col in df.columns if col.upper() == fred_code or 'value' in col.lower()]
        value_col = value_cols[0] if value_cols else df.columns[1]

        # 重命名列以统一格式
        df = df[[date_col, value_col]].copy()
        df.columns = ['date', 'value']

        # 转换日期列
        df['date'] = pd.to_datetime(df['date'])

        # 转换值列为数值类型，处理可能的格式问题
        df['value'] = pd.to_numeric(df['value'], errors='coerce')

        # 移除NaN值
        df = df.dropna(subset=['value'])

        # 按日期排序并取最近数据
        df = df.sort_values('date').tail(30)  # 取最近30天
        if df.empty:
            logging.warning(f"从FRED获取 {fred_code} 成功但数据为空")
            return None
        logging.info(f"从FRED获取 {fred_code} 成功")
        return df
    except Exception as e:
        logging.error(f"从FRED获取 {fred_code} 失败: {e}")
        return None

def get_us_10y_yield():
    """
    从 Trading Economics 获取美国10年国债收益率数据
    网站: https://zh.tradingeconomics.com/united-states/10-year-tips-yield
    从表格中提取 data-symbol="USGG10YR:IND" 行的“收益率”列数据
    """
    try:
        url = "https://zh.tradingeconomics.com/united-states/10-year-tips-yield"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        # 查找目标表格 - 尝试多种可能的class名称
        table = None
        table_classes = [
            'table table-hover sortable-theme-minimal table-striped table-heatmap',
            'table table-hover table-striped',
            'table table-hover',
            'table'
        ]

        for table_class in table_classes:
            table = soup.find('table', {'class': table_class})
            if table:
                break

        if not table:
            logging.warning("未找到目标表格")
            return None

        # 查找表头，确定"收益率"列的索引
        thead = table.find('thead')
        if not thead:
            logging.warning("表格没有表头")
            return None

        header_rows = thead.find_all('tr')
        if not header_rows:
            logging.warning("表格没有表头行")
            return None

        # 找到包含列名的行（通常是最后一行）
        header_row = header_rows[-1]
        headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]

        # 找到"收益率"列的索引
        yield_col_index = -1
        for i, header in enumerate(headers):
            if '收益率' in header:
                yield_col_index = i
                break

        # 如果没有找到"收益率"，尝试其他可能的列名
        if yield_col_index == -1:
            yield_aliases = ['收益率', 'Yield', 'YIELD', '收益', '利率', 'Interest Rate', 'Price', 'price', 'Last']
            for i, header in enumerate(headers):
                for alias in yield_aliases:
                    if alias in header:
                        yield_col_index = i
                        break
                if yield_col_index != -1:
                    break

        # 如果还是没找到，检查表头内容是否有乱码情况
        if yield_col_index == -1:
            # 检查表头中是否有非ASCII字符（可能是乱码的收益率）
            for i, header in enumerate(headers):
                if header and any(ord(char) > 127 for char in header):
                    yield_col_index = i
                    break

        # 如果仍然没找到，使用默认索引1（第二列，根据网页结构）
        if yield_col_index == -1:
            if len(headers) > 1:
                yield_col_index = 1
            else:
                logging.warning(f"未找到'收益率'列，可用列名: {headers}")
                return None

        # 查找数据行
        tbody = table.find('tbody')
        rows = None

        if tbody:
            rows = tbody.find_all('tr')
        else:
            rows = table.find_all('tr')
            # 跳过表头行（通常在thead中）
            if thead:
                header_trs = thead.find_all('tr')
                if header_trs:
                    rows = rows[len(header_trs):]

        if not rows:
            logging.warning("没有找到数据行")
            return None

        # 查找 data-symbol="USGG10YR:IND" 的行

        # 查找 data-symbol="USGG10YR:IND" 的行
        target_row = None
        for row in rows:
            if row.get('data-symbol') == 'USGG10YR:IND':
                target_row = row
                break

        # 如果找不到，尝试其他方式查找
        if not target_row:
            # 尝试查找包含 USGG10YR 文本的行
            for row in rows:
                row_text = row.get_text()
                if 'USGG10YR' in row_text or '10-Year' in row_text or '10年' in row_text:
                    target_row = row
                    logging.info(f"通过文本匹配找到目标行: {row_text[:50]}...")
                    break

        if not target_row:
            logging.warning("未找到 data-symbol='USGG10YR:IND' 的行")
            # 输出前几行的内容用于调试
            for i, row in enumerate(tbody.find_all('tr')[:5]):
                row_data = {}
                cells = row.find_all(['td', 'th'])
                for j, cell in enumerate(cells[:3]):  # 只取前3列
                    row_data[f'col{j}'] = cell.get_text(strip=True)[:30]
                logging.warning(f"行 {i+1}: {row_data}")
            return None

        # 提取该行的所有单元格
        cells = target_row.find_all(['td', 'th'])
        if len(cells) <= yield_col_index:
            logging.warning("行数据列数不足")
            return None

        # 方法1：通过列索引提取
        yield_cell = cells[yield_col_index]
        yield_value_text = yield_cell.get_text(strip=True)
        yield_value = None

        # 尝试从该单元格提取数值
        try:
            if yield_value_text:
                # 移除非数字字符（保留数字、小数点、负号）
                cleaned = re.sub(r'[^\d.-]', '', yield_value_text)
                if cleaned:
                    yield_value = float(cleaned)
                else:
                    # 如果清理后为空，尝试直接转换
                    yield_value = float(yield_value_text.replace('%', '').strip())
        except ValueError:
            logging.info(f"通过列索引提取收益率失败: {yield_value_text}")

        # 方法2：如果方法1失败，尝试查找id="p"的单元格
        if yield_value is None:
            p_cell = target_row.find('td', {'id': 'p'})
            if p_cell:
                p_text = p_cell.get_text(strip=True)
                try:
                    cleaned = re.sub(r'[^\d.-]', '', p_text)
                    if cleaned:
                        yield_value = float(cleaned)
                    else:
                        yield_value = float(p_text.replace('%', '').strip())
                    logging.info(f"通过id='p'找到收益率: {yield_value}")
                except ValueError:
                    logging.warning(f"无法解析id='p'单元格的值: {p_text}")

        if yield_value is None:
            logging.warning("无法提取收益率值")
            return None

        # 尝试获取日期
        date_value = None
        # 方法1：查找id="date"的单元格
        date_cell = target_row.find('td', {'id': 'date'})
        if date_cell:
            date_text = date_cell.get_text(strip=True)
            if date_text:
                date_value = date_text

        # 方法2：如果找不到id="date"，尝试从最后一列提取
        if not date_value and len(cells) > 0:
            # 通常日期在最后一列
            last_cell = cells[-1]
            last_text = last_cell.get_text(strip=True)
            # 检查是否是日期格式（包含-）
            if last_text and '-' in last_text:
                date_value = last_text

        result = {
            'yield': yield_value,
            'date': date_value or datetime.now().strftime('%Y-%m-%d')
        }

        logging.info(f"成功获取美国10年国债收益率: {yield_value}%")
        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"网络请求失败: {e}")
        return None
    except Exception as e:
        logging.error(f"获取美国10年国债收益率数据时发生错误: {e}")
        return None

def get_btc_stats():
    """
    获取 BTC/USDT 24小时统计数据
    参考 btc_price.py 中的 get_stats 函数
    """
    try:
        resp = requests.get(f"{BINANCE_BASE_URL}/ticker/24hr", params={"symbol": BTC_SYMBOL}, timeout=10)
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
    except Exception as e:
        logging.error(f"获取 BTC/USDT 数据失败: {e}")
        return None

def get_index_data(yahoo_symbol, label):
    """从 Yahoo Finance 获取全球指数最新行情"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=5d"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        result = data['chart']['result'][0]
        quotes = result['indicators']['quote'][0]
        timestamps = result['timestamp']

        closes = quotes['close']
        # 过滤掉 None 值
        valid_data = [(ts, close) for ts, close in zip(timestamps, closes) if close is not None]

        if len(valid_data) < 2:
            logging.warning(f"获取指数 {label} ({yahoo_symbol}) 数据不足")
            return None

        latest_ts, latest_close = valid_data[-1]
        _, prev_close = valid_data[-2]

        change = latest_close - prev_close
        change_pct = (change / prev_close) * 100
        latest_date = datetime.fromtimestamp(latest_ts).strftime('%Y-%m-%d')

        return {
            'label': label,
            'symbol': yahoo_symbol,
            'price': latest_close,
            'change': change,
            'change_pct': change_pct,
            'date': latest_date
        }
    except Exception as e:
        logging.error(f"获取指数 {label} ({yahoo_symbol}) 数据失败: {e}")
        return None

def generate_market_report():
    """生成市场快报"""
    print(f"开始生成市场快报... [{datetime.now()}]")

    # 1. 获取利率数据
    sofr_data = fetch_interest_rate_data("secured-overnight-financing-rate-sofr")
    effr_data = fetch_interest_rate_data("effective-federal-funds-rate")
    us_10y_yield = get_us_10y_yield()

    # 2. 获取 BTC/USDT 数据
    btc_stats = get_btc_stats()

    # 3. 获取全球指数数据
    index_data = {}
    for label, yahoo_symbol in INDEX_SYMBOLS.items():
        index_data[label] = get_index_data(yahoo_symbol, label)

    # 准备报告内容
    report_lines = []
    report_lines.append("=" * 50)
    report_lines.append("         市场快报")
    report_lines.append("=" * 50)

    # 添加时间戳
    report_lines.append(f"报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")

    # 利率数据部分
    report_lines.append("--- 利率市场 ---")

    if sofr_data is not None and not sofr_data.empty:
        latest_sofr = sofr_data.iloc[-1]
        sofr_date = latest_sofr['date'].strftime('%Y-%m-%d')
        sofr_value = float(latest_sofr['value'])
        report_lines.append(f"SOFR 利率 ({sofr_date}): {sofr_value:.4f}%")
    else:
        sofr_value = None
        report_lines.append("SOFR 利率: 数据不可用")

    if effr_data is not None and not effr_data.empty:
        latest_effr = effr_data.iloc[-1]
        effr_date = latest_effr['date'].strftime('%Y-%m-%d')
        effr_value = float(latest_effr['value'])
        report_lines.append(f"EFFR 利率 ({effr_date}): {effr_value:.4f}%")
    else:
        effr_value = None
        report_lines.append("EFFR 利率: 数据不可用")

    # 计算利差
    if sofr_value is not None and effr_value is not None:
        spread = sofr_value - effr_value
        report_lines.append(f"利差 (SOFR - EFFR): {spread:.4f}%")
        # 简单预警
        if spread > 0.10:
            report_lines.append("[预警] 利差 > 0.10%，融资基差异常，流动性可能收紧")
    else:
        report_lines.append("利差 (SOFR - EFFR): 数据不足无法计算")

    report_lines.append("")

    # 美国10年国债收益率部分
    report_lines.append("--- 国债市场 ---")

    if us_10y_yield is not None:
        us_10y_value = us_10y_yield['yield']
        us_10y_date = us_10y_yield['date']
        report_lines.append(f"美国10年国债收益率 ({us_10y_date}): {us_10y_value:.2f}%")
    else:
        us_10y_value = None
        report_lines.append("美国10年国债收益率: 数据不可用")

    report_lines.append("")

    # BTC/USDT 数据部分
    report_lines.append("--- 加密货币市场 ---")

    if btc_stats is not None:
        arrow = "▲" if btc_stats["change"] >= 0 else "▼"
        report_lines.append(f"BTC/USDT 当前价格: ${btc_stats['price']:,.2f}")
        report_lines.append(f"24小时涨跌幅: {arrow} {btc_stats['change_pct']:+.2f}% ({btc_stats['change']:+,.2f} USDT)")
    else:
        report_lines.append("BTC/USDT: 数据不可用")

    report_lines.append("")

    # 全球指数部分
    report_lines.append("--- 全球指数 ---")

    for label in INDEX_SYMBOLS.keys():
        data = index_data.get(label)
        if data is not None:
            arrow = "▲" if data['change'] >= 0 else "▼"
            report_lines.append(
                f"{data['label']} ({data['date']}): {data['price']:,.2f}  "
                f"{arrow} {data['change_pct']:+.2f}%"
            )
        else:
            report_lines.append(f"{label}: 数据不可用")

    report_lines.append("")
    report_lines.append("=" * 50)

    # 打印报告
    report = "\n".join(report_lines)
    print(report)

    # 记录日志
    index_log_parts = []
    for label, data in index_data.items():
        if data:
            index_log_parts.append(f"{label}={data['price']:,.2f}")
        else:
            index_log_parts.append(f"{label}=N/A")
    logging.info(f"市场快报生成成功: SOFR={sofr_value if sofr_value else 'N/A'}, "
                 f"EFFR={effr_value if effr_value else 'N/A'}, "
                 f"美国10年国债={us_10y_value if us_10y_value else 'N/A'}%, "
                 f"BTC价格={btc_stats['price'] if btc_stats else 'N/A'}, "
                 f"指数={{{', '.join(index_log_parts)}}}")

def main():
    """主函数"""
    try:
        generate_market_report()
    except Exception as e:
        logging.error(f"生成市场快报时发生错误: {e}")
        print(f"错误: {e}")
        return 1
    return 0

if __name__ == "__main__":
    main()
