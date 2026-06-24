"""Test JSON repair on actual failed output"""
import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

with open('data/extractions/v1_events/side/孤星.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
raw = d.get('_raw', '')

# strip think
text = re.sub(r'<think>[\s\S]*?</think>', '', raw).strip()

# extract ```json block
m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
if not m:
    print('No JSON block found')
    sys.exit(1)

json_str = m.group(1)
print(f'JSON string length: {len(json_str)}')

# Try to find all problematic quotes
# Pattern: Chinese-char + " + Chinese-char (opening quote)
repaired = re.sub(r'(?<=[一-鿿])“', '「', json_str)  # "
repaired = re.sub(r'(?<=[一-鿿])”', '」', repaired)  # "
# Also handle regular ASCII quotes between Chinese chars
repaired = re.sub(r'(?<=[一-鿿])\x22(?=[一-鿿「])', '「', repaired)
repaired = re.sub(r'(?<=[一-鿿」])\x22(?=[一-鿿，。！、\n\r])', '」', repaired)

try:
    parsed = json.loads(repaired)
    print(f'OK! events={len(parsed.get("events",[]))}')
except json.JSONDecodeError as e:
    print(f'Failed at char {e.pos}: {e}')
    ctx = repaired[max(0, e.pos-50):e.pos+50]
    print(f'Context: {ctx}')

    # Try more aggressive repair: find ALL unescaped quotes within string values
    # Strategy: find all instances of 中文字符+"+中文字符 pattern
    for i, ch in enumerate(repaired):
        if ch == '"' and i > 0 and i < len(repaired) - 1:
            prev = repaired[i-1]
            next_ch = repaired[i+1]
            if '一' <= prev <= '鿿' and '一' <= next_ch <= '鿿':
                print(f'Unescaped quote at pos {i}: ...{repaired[i-5:i+5]}...')
