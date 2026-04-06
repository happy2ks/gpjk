#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Trading Economics 网站抓取美国利率数据
网址：https://zh.tradingeconomics.com/united-states/secured-overnight-financing-rate

目标数据：
1. 银行贷款利率
2. 有效联邦基金利率
3. 美联储利率（Fed）
4. 担保隔夜融资利率

提取"近期数据"列的值
"""

import requests
from bs4 import BeautifulSoup
import sys

def fetch_page(url):
    """获取网页内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

def extract_rates_from_soup(soup):
    """从BeautifulSoup对象中提取目标利率数据"""
    target_names = [
        "银行贷款利率",
        "有效联邦基金利率",
        "美联储利率（Fed）",
        "担保隔夜融资利率"
    ]

    results = {}

    # 查找所有表格
    tables = soup.find_all('table')

    for table_idx, table in enumerate(tables):
        # 获取表格的所有行
        rows = table.find_all('tr')
        if len(rows) <= 1:
            continue

        # 提取表头
        headers = []
        thead = table.find('thead')
        if thead:
            header_rows = thead.find_all('tr')
            for row in header_rows:
                ths = row.find_all(['th', 'td'])
                headers = [th.get_text(strip=True) for th in ths]
        else:
            # 使用第一行作为表头
            first_row = rows[0]
            ths = first_row.find_all(['th', 'td'])
            headers = [th.get_text(strip=True) for th in ths]
            rows = rows[1:]  # 跳过表头行

        # 查找"近期数据"列的索引
        recent_data_col = -1
        for i, header in enumerate(headers):
            if "近期数据" in header:
                recent_data_col = i
                break

        if recent_data_col == -1:
            # 如果没有找到，假设第二列是近期数据
            if len(headers) >= 2:
                recent_data_col = 1
            else:
                recent_data_col = 0

        # 遍历每一行
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = [cell.get_text(strip=True) for cell in cells]

            if not row_data:
                continue

            row_name = row_data[0] if row_data else ""

            # 检查是否为目标行
            for target in target_names:
                if target in row_name:
                    # 提取近期数据
                    if recent_data_col < len(row_data):
                        recent_value = row_data[recent_data_col]
                        results[target] = recent_value
                    break

        # 如果已经找到所有目标，提前退出
        if len(results) == len(target_names):
            break

    return results

def print_results(results):
    """打印结果"""
    target_names = [
        "银行贷款利率",
        "有效联邦基金利率",
        "美联储利率（Fed）",
        "担保隔夜融资利率"
    ]

    print("\n" + "="*50)
    print("利率数据抓取结果")
    print("="*50)

    all_found = True
    for target in target_names:
        if target in results:
            print(f"{target}: {results[target]}")
        else:
            print(f"{target}: 未找到")
            all_found = False

    print("="*50)

    if all_found:
        print("成功获取所有目标数据！")
    else:
        print("警告：部分数据未找到")

def save_to_file(results, filename="interest_rates.txt"):
    """将结果保存到文件"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("利率数据抓取结果\n")
            f.write("="*50 + "\n")
            for name, value in results.items():
                f.write(f"{name}: {value}\n")
            f.write("="*50 + "\n")
        print(f"\n结果已保存到文件: {filename}")
    except IOError as e:
        print(f"保存文件失败: {e}")

def main():
    url = "https://zh.tradingeconomics.com/united-states/secured-overnight-financing-rate"

    print("正在从 Trading Economics 抓取利率数据...")
    print(f"URL: {url}")

    # 获取网页内容
    html = fetch_page(url)
    if not html:
        print("无法获取网页内容，请检查网络连接或URL")
        sys.exit(1)

    # 创建BeautifulSoup对象
    soup = BeautifulSoup(html, 'html.parser')

    # 提取数据
    results = extract_rates_from_soup(soup)

    # 打印结果
    print_results(results)

    # 保存到文件
    save_to_file(results)

    return results

if __name__ == "__main__":
    main()