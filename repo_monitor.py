import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import logging
from datetime import datetime

# 配置日志记录
logging.basicConfig(
    filename='repo_flow.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 映射：OFR系列代码 -> FRED代码
SERIES_MAPPING = {
    "dvp-service-transaction-volume": None,  # 暂无FRED对应
    "secured-overnight-financing-rate-sofr": "SOFR",
    "effective-federal-funds-rate": "EFFR",
    "sofr": "SOFR",
    "effr": "EFFR"
}

def fetch_ofr_data(series_code):
    """
    从多个数据源获取金融数据
    1. 首先尝试OFR API
    2. 如果失败且有FRED映射，尝试从FRED获取
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

def main():
    print(f"开始执行 2026 债务高墙监控任务... [{datetime.now()}]")
    
    # 1. 获取 DVP 成交量 (对冲基金的子弹)
    dvp_vol = fetch_ofr_data("dvp-service-transaction-volume")
    
    # 2. 获取 SOFR-EFFR 利差 (直接获取计算好的利差数据更稳)
    # 也可以分别获取 sofr 和 effr 再计算
    sofr_data = fetch_ofr_data("secured-overnight-financing-rate-sofr")
    effr_data = fetch_ofr_data("effective-federal-funds-rate")

    if sofr_data is not None and not sofr_data.empty:
        latest_sofr = sofr_data.iloc[-1]
        latest_effr = effr_data.iloc[-1] if effr_data is not None and not effr_data.empty else None

        spread = latest_sofr['value'] - latest_effr['value'] if latest_effr is not None else "N/A"

        # 确定报告日期（优先使用DVP日期，否则使用SOFR日期）
        report_date = None
        if dvp_vol is not None and not dvp_vol.empty:
            latest_vol = dvp_vol.iloc[-1]
            report_date = latest_vol['date']
        else:
            report_date = latest_sofr['date']

        # 打印报告
        # 格式化数值显示
        sofr_value = float(latest_sofr['value'])
        effr_value = float(latest_effr['value']) if latest_effr is not None else None
        spread_value = float(spread) if isinstance(spread, (int, float)) else None

        # 确定DVP显示值
        dvp_display = "N/A"
        if dvp_vol is not None and not dvp_vol.empty:
            latest_vol = dvp_vol.iloc[-1]
            dvp_display = f"${latest_vol['value']:.2f} Billion"

        # 构建报告字符串
        report_lines = []
        report_lines.append("--- 每日回购市场快报 ---")
        report_lines.append(f"日期: {report_date.strftime('%Y-%m-%d')}")
        report_lines.append(f"DVP 总成交量: {dvp_display}")
        report_lines.append(f"SOFR 利率: {sofr_value:.2f}%")

        # 处理EFFR显示
        if effr_value is not None:
            report_lines.append(f"EFFR 利率: {effr_value:.2f}%")
        else:
            report_lines.append("EFFR 利率: N/A")

        # 处理利差显示
        if spread_value is not None:
            report_lines.append(f"利差 (SOFR-EFFR): {spread_value:.4f}%")
        else:
            report_lines.append("利差 (SOFR-EFFR): N/A")

        report_lines.append("------------------------")
        report = "\n        ".join(report_lines)

        print(f"        {report}")

        # 记录日志使用格式化值
        effr_display = f"{effr_value:.2f}%" if effr_value is not None else "N/A"
        spread_display = f"{spread_value:.4f}%" if spread_value is not None else "N/A"
        logging.info(f"SUCCESS: DVP={dvp_display}, SOFR={sofr_value:.2f}%, EFFR={effr_display}, Spread={spread_display}")

        # 预警：2026年Q2-Q4 债务压力期间，利差 > 0.1% 需要高度警惕
        if spread_value is not None and spread_value > 0.10:
            warning_msg = "[警告] ALERT: 融资基差异常！流动性可能正在收紧。"
            print(warning_msg)
            logging.warning(warning_msg)
    else:
        print("[错误] 数据抓取不完整，请检查网络或 API 状态。")

if __name__ == "__main__":
    main()