import pandas as pd
import requests
from datetime import datetime, timedelta

# 尝试导入pandas_datareader，如果失败则使用备用方案
try:
    import pandas_datareader.data as web
    PANDAS_DATAREADER_AVAILABLE = True
except Exception as e:
    print(f"pandas_datareader导入失败: {e}")
    print("将使用备用数据获取方法...")
    web = None
    PANDAS_DATAREADER_AVAILABLE = False

def get_fed_data():
    """获取 SOFR 和 EFFR (来自 FRED)"""
    end = datetime.now()
    start = end - timedelta(days=30)  # 获取最近一个月趋势

    print("正在从 FRED 获取利率数据...")
    # SOFR: 担保隔夜融资利率
    # EFFR: 有效联邦基金利率

    if PANDAS_DATAREADER_AVAILABLE:
        df = web.DataReader(['SOFR', 'EFFR'], 'fred', start, end)
    else:
        # 备用方法：使用fredapi
        try:
            from fredapi import Fred
            # 需要FRED API密钥，这里使用公共API（可能有限制）
            fred = Fred()
            sofr = fred.get_series('SOFR', start, end)
            effr = fred.get_series('EFFR', start, end)
            df = pd.DataFrame({'SOFR': sofr, 'EFFR': effr})
        except Exception as e:
            print(f"fredapi获取失败: {e}")
            # 备用方法：直接下载CSV
            print("尝试直接下载CSV...")
            sofr_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR"
            effr_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=EFFR"

            # 读取CSV，自动检测列名
            sofr_df = pd.read_csv(sofr_url)
            effr_df = pd.read_csv(effr_url)

            # 查找日期列和值列
            date_col = [col for col in sofr_df.columns if 'date' in col.lower()][0]
            sofr_value_col = [col for col in sofr_df.columns if col.upper() == 'SOFR' or 'value' in col.lower()][0]
            effr_value_col = [col for col in effr_df.columns if col.upper() == 'EFFR' or 'value' in col.lower()][0]

            # 转换日期列
            sofr_df[date_col] = pd.to_datetime(sofr_df[date_col])
            effr_df[date_col] = pd.to_datetime(effr_df[date_col])

            sofr_df.set_index(date_col, inplace=True)
            effr_df.set_index(date_col, inplace=True)

            # 合并数据
            df = pd.DataFrame({'SOFR': sofr_df[sofr_value_col], 'EFFR': effr_df[effr_value_col]})
            # 过滤日期范围
            df = df[(df.index >= start) & (df.index <= end)]

    df['Spread (SOFR-EFFR)'] = df['SOFR'] - df['EFFR']
    return df

def get_ofr_dvp_volume():
    """获取 OFR DVP Repo 成交量数据"""
    print("正在从 OFR 获取 DVP Volume 数据...")
    # 尝试多个可能的OFR API URL
    url_candidates = [
        "https://www.financialresearch.gov/short-term-funding-monitor/api/series/timeseries/dvp-service-transaction-volume.csv",
        "https://www.financialresearch.gov/short-term-funding-monitor/api/v1/series/timeseries/dvp-service-transaction-volume.csv",
        "https://www.financialresearch.gov/short-term-funding-monitor/api/series/dvp-service-transaction-volume.csv",
        "https://www.financialresearch.gov/short-term-funding-monitor/api/timeseries/dvp-service-transaction-volume.csv"
    ]

    for url in url_candidates:
        try:
            print(f"尝试URL: {url}")
            # 使用requests获取，以便更好的错误处理
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # 读取CSV数据
            df_volume = pd.read_csv(pd.io.common.StringIO(response.text))

            # 查找日期列
            date_cols = [col for col in df_volume.columns if 'date' in col.lower()]
            if not date_cols:
                date_col = df_volume.columns[0]  # 默认第一列
            else:
                date_col = date_cols[0]

            df_volume[date_col] = pd.to_datetime(df_volume[date_col])
            df_volume.set_index(date_col, inplace=True)
            # 获取最新的一条记录
            print(f"成功从 {url} 获取数据")
            return df_volume.tail(10)  # 返回最近10天数据

        except Exception as e:
            print(f"URL {url} 失败: {e}")
            continue

    return "OFR 数据获取失败: 所有URL尝试均失败"

def main():
    # 1. 执行获取
    rates_df = get_fed_data()
    volume_df = get_ofr_dvp_volume()

    # 2. 打印结果
    print("\n" + "="*50)
    print("--- 每日美债回购市场监控报告 ---")
    print(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

    print("\n[1] 利率成本监控 (单位: %)")
    print(rates_df.tail(5)) # 打印最近5个交易日

    print("\n[2] DVP 成交量监控 (对冲基金融资额度)")
    print(volume_df)

    # 3. 简单的预警逻辑
    latest_spread = rates_df['Spread (SOFR-EFFR)'].iloc[-1]
    if latest_spread > 0.10: # 如果利差超过 10 个基点
        print("\n[警告] 预警：SOFR-EFFR 利差异常扩大，回购市场流动性趋紧！")
    else:
        print("\n[正常] 目前融资成本利差处于正常区间。")

if __name__ == "__main__":
    main()