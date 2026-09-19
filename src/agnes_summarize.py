# -*- coding: utf-8 -*-
"""agnes_summarize.py — 用 agnes AI 给每条机构内参做摘要/标签
- 调用 OpenAI-compat API (https://apihub.agnes-ai.com/v1/chat/completions)
- 输入: 已抓取的 .md 文件
- 输出: data/summarized.json (含 ai_summary, tags, importance)
"""
import os, sys, json, urllib.request, urllib.error, argparse
from pathlib import Path

AGNES_BASE = os.environ.get('AGNES_BASE_URL', 'https://apihub.agnes-ai.com/v1')
AGNES_KEY = os.environ.get('AGNES_API_KEY', '')
AGNES_MODEL = os.environ.get('AGNES_MODEL', 'agnes-2.5-flash')

PROMPT_TEMPLATE = '你是资深卖方研究员。请基于以下"机构内参"片段，给出 3 个字段的 JSON（仅输出 JSON，无 markdown）：\n\n1. ai_summary: 100-200 字摘要，保留核心数据/标的/结论，去除口水话\n2. tags: 3-5 个标签（行业/题材/事件/概念），从以下标签池挑：\n   - 科技/算力: AI算力/半导体/PCB/消费电子/光模块/CPO/数据中心/液冷/机器人/脑机接口/低空经济/卫星/量子科技\n   - 新能源: 光伏/储能/锂电池/钠电池/氢能/风电/核电/虚拟电厂\n   - 制造/材料: 新材料/化工/钢铁/有色/煤炭/石油/工程机械/造船\n   - 出行/运输: 汽车/智能驾驶/整车/零部件/轮胎/航运/航空/高铁/快递\n   - 消费: 食品/白酒/家电/纺服/美妆/零售/医美/宠物/免税/彩票\n   - 医药: 创新药/CXO/医疗器械/中药/疫苗/减肥药/合成生物\n   - 金融: 券商/保险/银行/信托/金融科技/支付\n   - 地产/基建: 房地产/建材/家电家居/装修/基建/水利/管网\n   - 政策/主题: 国改/并购重组/分红/回购/涨价/出海/出口/自主可控/信创/数据要素/华为链/苹果链/小米链\n   - 周期/事件: 业绩/超预期/利空/涨价/产能/停产/订单/中标\n3. importance: 1-5 星（5=最重磅；3=一般；1=水稿），基于时效+独家性+数据密度\n\n标题：{title}\n正文：\n{body}\n\nJSON：'

def agnes_chat(title, body, timeout=30):
    if not AGNES_KEY:
        return None, 'AGNES_API_KEY not set'
    prompt = PROMPT_TEMPLATE.format(title=title[:200], body=body[:3000])
    payload = {
        'model': AGNES_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
        'max_tokens': 800,
    }
    req = urllib.request.Request(
        f'{AGNES_BASE}/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {AGNES_KEY}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        obj = json.loads(r.read().decode('utf-8'))
        text = obj['choices'][0]['message']['content']
        # extract JSON from text (sometimes wrapped in ```)
        text = text.strip()
        if text.startswith('```'):
            text = '\n'.join(text.split('\n')[1:-1])
        return json.loads(text), None
    except urllib.error.HTTPError as e:
        return None, f'HTTP {e.code}: {e.read()[:200].decode("utf-8", errors="replace")}'
    except Exception as e:
        return None, str(e)

def process_md(md_path):
    text = Path(md_path).read_text(encoding='utf-8', errors='replace')
    lines = text.split('\n')
    title = lines[0].replace('【机构内参】', '').strip() if lines and lines[0].startswith('【机构内参】') else '无标题'
    body = '\n'.join(lines[1:]).strip()
    # find rec_id from filename
    rec_id = md_path.stem.rsplit('_', 1)[-1]
    summary, err = agnes_chat(title, body)
    if err:
        return {'rec_id': rec_id, 'title': title, 'body': body[:500], 'error': err}
    return {
        'rec_id': rec_id,
        'title': title,
        'body': body[:500],
        'ai_summary': summary.get('ai_summary', ''),
        'tags': summary.get('tags', []),
        'importance': summary.get('importance', 3),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='data')
    parser.add_argument('--output', '-o', default='data/summarized.json')
    parser.add_argument('--date', help='only process this date')
    parser.add_argument('--limit', type=int, default=10, help='max files per run')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    p = Path(args.input)
    if args.date:
        files = sorted((p / args.date).glob('*.md')) if (p / args.date).exists() else []
    else:
        files = []
        for d in sorted([x for x in p.iterdir() if x.is_dir()], reverse=True):
            files = sorted(d.glob('*.md'))
            if files: break

    files = files[:args.limit]
    if not files:
        print('no md files found'); return

    if args.dry_run:
        print(f'[DRY-RUN] would summarize {len(files)} files')
        for f in files[:3]:
            print(f'  - {f.name}')
        return

    out = []
    for f in files:
        print(f'  {f.name}', flush=True)
        result = process_md(f)
        out.append(result)
        if 'error' in result:
            print(f'    ERR: {result["error"][:100]}')
        else:
            print(f'    OK: importance={result.get("importance")} tags={result.get("tags")}')

    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nWROTE {len(out)} items to {args.output}')

if __name__ == '__main__':
    main()
