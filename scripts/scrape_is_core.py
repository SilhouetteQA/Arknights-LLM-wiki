"""
集成战略核心页面精确抓取
每个 IS 主题 3-5 个核心页面: 事件一览、藏品、结局记录、月度小队、额外资料
"""
import urllib.request, re, json, time, os
from pathlib import Path

OUTPUT = Path("data/is_raw")
BASE = "https://prts.wiki"

# 每个主题的核心页面 — 精确列表
THEMES = {
    "傀影与猩红孤钻": {
        "base": "%E5%82%80%E5%BD%B1%E4%B8%8E%E7%8C%A9%E7%BA%A2%E5%AD%A4%E9%92%BB",
        "pages": {
            "事件一览": "事件一览",
            "猩红珍藏": "猩红珍藏",
            "长生者宝盒": "长生者宝盒",
            "月度小队": "月度小队",
        }
    },
    "水月与深蓝之树": {
        "base": "%E6%B0%B4%E6%9C%88%E4%B8%8E%E6%B7%B1%E8%93%9D%E4%B9%8B%E6%A0%91",
        "pages": {
            "事件一览": "事件一览",
            "生物制品陈设": "生物制品陈设",
            "深蓝记录仪": "深蓝记录仪",
            "追忆映射": "追忆映射",
        }
    },
    "探索者的银凇止境": {
        "base": "%E6%8E%A2%E7%B4%A2%E8%80%85%E7%9A%84%E9%93%B6%E5%87%87%E6%AD%A2%E5%A2%83",
        "pages": {
            "事件一览": "事件一览",
            "仪式用品索检": "仪式用品索检",
            "冬夜展览馆": "冬夜展览馆",
            "密文板研究": "密文板研究",
            "探索者档案": "探索者档案",
        }
    },
    "萨卡兹的无终奇语": {
        "base": "%E8%90%A8%E5%8D%A1%E5%85%B9%E7%9A%84%E6%97%A0%E7%BB%88%E5%A5%87%E8%AF%AD",
        "pages": {
            "事件一览": "事件一览",
            "逸散思维辑录": "逸散思维辑录",
            "巫仪档案库": "巫仪档案库",
            "想象实体图录": "想象实体图录",
        }
    },
    "岁的界园志异": {
        "base": "%E5%B2%81%E7%9A%84%E7%95%8C%E5%9B%AD%E5%BF%97%E5%BC%82",
        "pages": {
            "事件一览": "事件一览",
            "藏钱木盒": "藏钱木盒",
            "珍玩集会": "珍玩集会",
            "见字图册": "见字图册",
        }
    },
    "刻俄柏的灰蕈迷境": {
        "base": "%E5%88%BB%E4%BF%84%E6%9F%8F%E7%9A%84%E7%81%B0%E8%95%88%E8%BF%B7%E5%A2%83",
        "pages": {
            "事件一览": "事件一览",
            "收藏品图鉴": "收藏品图鉴",
        }
    },
}

RELEVANT_SECTIONS = [
    '事件', '结局', 'Ending', 'ENDING',
    '月度', '追忆', '万象', '小队', '档案',
    '收藏', '珍藏', '宝盒', '生物制品', '物品', '图鉴', '陈设', '钱木',
    '记录仪', '记录', '碑林', '回响', '启示', '呼唤',
    '背景', '额外', '故事', '引言', '审判庭', '印刷机', '播放机',
    '认知', '排异', '符号',
]


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'AK-Wiki/1.0'})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read().decode('utf-8')


def clean_html(html):
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</?(?:p|div|li|tr|h[1-6]|td|th)[^>]*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)

    skip = ['PRTS', 'Cookie', '命名空间', '查看', '搜索', '导航', '工具', '个人',
            '热门', '帮助', '关于', '隐私', '免责', 'function', 'var ', 'class=',
            'client-', 'jQuery', 'RLCONF', 'wg', 'mediaWiki',
            'document.', 'window.', 'console.', 'setTimeout',
            '干员一览', '配音一览', '分支一览', '模组一览', '家具一览',
            '时装回廊', '采购中心', '卡池一览', '活动一览', '公招计算',
            '画师一览', '配乐一览', '页面值', '编辑者', '扩展', 'Widget']
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if len(line) < 2:
            continue
        if any(s in line for s in skip):
            continue
        lines.append(line)
    return '\n'.join(lines)


def is_relevant_section(title):
    for kw in RELEVANT_SECTIONS:
        if kw in title:
            return True
    return False


def scrape_theme(name, cfg):
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")

    result = {'name': name, 'pages': {}}
    base = cfg['base']

    for page_name, page_path in cfg['pages'].items():
        url = f'{BASE}/w/{base}/{urllib.request.quote(page_path)}'
        try:
            print(f"  {page_name}: {url}")
            html = fetch(url)

            # 提取章节
            sections = []
            for m in re.finditer(
                r'<span class="mw-headline"[^>]*id="([^"]*)"[^>]*>(.*?)</span>',
                html
            ):
                sid = m.group(1)
                title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                sections.append({'id': sid, 'title': title, 'pos': m.start()})

            # 提取相关章节的文本
            page_content = {}
            total_chars = 0
            for i, sec in enumerate(sections):
                if not is_relevant_section(sec['title']):
                    continue
                start = sec['pos']
                end = sections[i + 1]['pos'] if i + 1 < len(sections) else len(html)
                text = clean_html(html[start:end])
                if len(text.strip()) > 10:
                    page_content[sec['title']] = text
                    total_chars += len(text)

            # 如果没有匹配到章节，走全文
            if not page_content:
                full = clean_html(html)
                if full.strip():
                    page_content['_全文'] = full[:50000]
                    total_chars = len(full)

            result['pages'][page_name] = {
                'url': url,
                'sections': list(page_content.keys()),
                'content': page_content,
                'chars': total_chars,
            }
            print(f"    -> {len(page_content)} sections, {total_chars} chars")
            time.sleep(0.5)

        except Exception as e:
            print(f"    [404/ERR] {e}")
            result['pages'][page_name] = {'url': url, 'error': str(e)}

    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    index = {'themes': {}, 'total_chars': 0}

    for name, cfg in THEMES.items():
        try:
            data = scrape_theme(name, cfg)
            theme_dir = OUTPUT / name
            theme_dir.mkdir(parents=True, exist_ok=True)

            # JSON
            with open(theme_dir / 'data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 纯文本
            with open(theme_dir / 'text.txt', 'w', encoding='utf-8') as f:
                f.write(f"{'='*50}\n{name}\n{'='*50}\n\n")
                for pn, pd in data['pages'].items():
                    f.write(f"\n### {pn} ###\n")
                    if 'error' in pd:
                        f.write(f"ERROR: {pd['error']}\n")
                        continue
                    for st, sc in pd['content'].items():
                        f.write(f"\n--- {st} ---\n")
                        f.write(sc[:3000])
                        if len(sc) > 3000:
                            f.write(f"\n[...截断, 共{len(sc)}字符]\n")
                        f.write('\n')

            chars = sum(p.get('chars', 0) for p in data['pages'].values())
            index['themes'][name] = {
                'pages': len(data['pages']),
                'success': sum(1 for p in data['pages'].values() if 'error' not in p),
                'chars': chars,
            }
            index['total_chars'] += chars
            print(f"  saved: {theme_dir}")

        except Exception as e:
            print(f"  [FAIL] {name}: {e}")

    with open(OUTPUT / 'index.json', 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(index['themes'])} themes, {index['total_chars']:,} chars total")
    for name, info in index['themes'].items():
        print(f"  {name}: {info['success']}/{info['pages']} pages, {info['chars']:,} chars")


if __name__ == '__main__':
    main()
