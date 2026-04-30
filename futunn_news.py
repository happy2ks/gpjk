"""
抓取富途牛牛 7x24 小时实时快讯新闻
API: https://news.futunn.com/news-site-api/main/get-flash-list
"""
import requests
import sys
from datetime import datetime, timezone, timedelta

# 解决 Windows 终端中文乱码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_URL = "https://news.futunn.com/news-site-api/main/get-flash-list"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://news.futunn.com/main/live",
}


def fetch_news(page_size=30, seq_mark=""):
    """获取快讯列表"""
    params = {"pageSize": page_size}
    if seq_mark:
        params["seqMark"] = seq_mark

    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    resp.encoding = 'utf-8'
    data = resp.json()

    if data.get("code") != 0:
        print(f"API 返回错误: {data.get('message')}")
        return [], "", False

    inner = data["data"]["data"]
    return inner["news"], inner["seqMark"], inner["hasMore"]


# 北京时间时区
TZ_BEIJING = timezone(timedelta(hours=8))


def format_news(news):
    """格式化单条快讯"""
    ts = int(news.get("time", 0))
    t = datetime.fromtimestamp(ts, tz=TZ_BEIJING).strftime("%m-%d %H:%M") if ts else "未知时间"

    content = news['content']
    level = news.get("level", 0)
    tag = " [重要]" if level == 1 else ""
    return f"{t}{tag} {content}"


def main():
    page_size = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    seq_mark = ""
    total = 0
    lines = []

    for _ in range(pages):
        news_list, seq_mark, has_more = fetch_news(page_size, seq_mark)

        if not news_list:
            print("没有更多新闻了")
            break

        for n in news_list:
            lines.append(format_news(n))

        total += len(news_list)

        if not has_more:
            break

    now = datetime.now(TZ_BEIJING).strftime("%Y-%m-%d %H:%M")
    md = [
        f"# 富途牛牛快讯 ({now})",
        "",
        f"共 {total} 条",
        "",
    ]
    for line in lines:
        md.append(f"- {line}")
    md.append("")

    filename = f"快讯_{datetime.now(TZ_BEIJING).strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"已保存到 {filename}，共 {total} 条快讯")


if __name__ == "__main__":
    main()
