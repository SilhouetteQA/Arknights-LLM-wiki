"""
提取所有 IS 主题的藏品描述
每个藏品输出: {编号, 名称, 描述文本}
"""
import urllib.request, re, json
from pathlib import Path

BASE = "https://prts.wiki"
OUTPUT = Path("data/is_raw")

# 每个主题的收藏品页面
COLLECTIBLES = {
    "刻俄柏的灰蕈迷境": {
        "base": "%E5%88%BB%E4%BF%84%E6%9F%8F%E7%9A%84%E7%81%B0%E8%95%88%E8%BF%B7%E5%A2%83",
        "page": "收藏品图鉴",
    },
    "傀影与猩红孤钻": {
        "base": "%E5%82%80%E5%BD%B1%E4%B8%8E%E7%8C%A9%E7%BA%A2%E5%AD%A4%E9%92%BB",
        "page": "长生者宝盒",
    },
    "水月与深蓝之树": {
        "base": "%E6%B0%B4%E6%9C%88%E4%B8%8E%E6%B7%B1%E8%93%9D%E4%B9%8B%E6%A0%91",
        "page": "生物制品陈设",
    },
    "探索者的银凇止境": {
        "base": "%E6%8E%A2%E7%B4%A2%E8%80%85%E7%9A%84%E9%93%B6%E5%87%87%E6%AD%A2%E5%A2%83",
        "page": "仪式用品索引",
    },
    "萨卡兹的无终奇语": {
        "base": "%E8%90%A8%E5%8D%A1%E5%85%B9%E7%9A%84%E6%97%A0%E7%BB%88%E5%A5%87%E8%AF%AD",
        "page": "想象实体图鉴",
    },
    "岁的界园志异": {
        "base": "%E5%B2%81%E7%9A%84%E7%95%8C%E5%9B%AD%E5%BF%97%E5%BC%82",
        "page": "见字图册",
        "number_format": "Cxxx",  # 用 C001 格式而非 No.1
    },
}


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'AK-Wiki/1.0'})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode('utf-8')


def extract_collectibles(html):
    """从收藏品页面提取所有藏品 {no, name, full_text}"""
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        html, re.DOTALL
    )

    items = []
    for table in tables:
        rows = re.findall(r'<tr>(.*?)</tr>', table, re.DOTALL)
        if len(rows) < 2:
            continue

        # Row 0: No.X | 名称
        cells0 = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', rows[0], re.DOTALL)
        if len(cells0) < 2:
            continue

        no_text = re.sub(r'<[^>]+>', '', cells0[0]).strip()
        name = re.sub(r'<[^>]+>', '', cells0[1]).strip()

        # 必须是 "No.数字" 格式
        if not re.match(r'No\.\s*\d+', no_text):
            continue

        # Row 2: 价格 | 效果+描述
        if len(rows) > 2:
            cells2 = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', rows[2], re.DOTALL)
            if len(cells2) >= 2:
                full_text = re.sub(r'<[^>]+>', '', cells2[1]).strip()
                full_text = re.sub(r'\s+', ' ', full_text)
            else:
                full_text = ''
        else:
            full_text = ''

        if name and full_text:
            items.append({
                'no': no_text.strip(),
                'name': name,
                'full_text': full_text,
            })

    return items


def main():
    for theme_name, cfg in COLLECTIBLES.items():
        print(f"\n{'='*50}")
        print(f"  {theme_name}")

        try:
            url = f"{BASE}/w/{cfg['base']}/{urllib.request.quote(cfg['page'])}"
            print(f"  {url}")
            html = fetch(url)
            items = extract_collectibles(html)
            print(f"  -> {len(items)} 件藏品")

            # 保存到主题目录
            theme_dir = OUTPUT / theme_name
            theme_dir.mkdir(parents=True, exist_ok=True)

            with open(theme_dir / 'collectibles.json', 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)

            # 纯文本
            with open(theme_dir / 'collectibles.txt', 'w', encoding='utf-8') as f:
                f.write(f"{theme_name} — 藏品描述 ({len(items)}件)\n")
                f.write(f"{'='*50}\n\n")
                for item in items:
                    f.write(f"[{item['no']}] {item['name']}\n")
                    f.write(f"  {item['full_text']}\n\n")

        except Exception as e:
            print(f"  [FAIL] {e}")

    print("\nDone.")


if __name__ == '__main__':
    main()
