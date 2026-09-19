# -*- coding: utf-8 -*-
"""push_zsxq.py — 推送机构内参到知识星球《外资纪要社》

走 zsxq MCP HTTP(用 OAuth Bearer token,不走 zsxq-cli binary,跨平台)。
经验: 用 OAuth Bearer token 调 MCP create_topic 中文正常;
       用普通 MCP api_key 调会触发 zsxq 服务端 GBK 编码 bug,中文乱码。
"""
import os, sys, json, urllib.request, urllib.error, argparse, time
from pathlib import Path

MCP_BASE = 'https://mcp.zsxq.com/topic/mcp'
BEARER_TOKEN = os.environ.get('ZSXQ_OAUTH_TOKEN', '')
API_KEY = os.environ.get('ZSXQ_MCP_KEY', '')
GROUP_ID = os.environ.get('ZSXQ_GROUP_ID', '48885115254258')


def mcp_call(method, params=None, timeout=30):
    """JSON-RPC 2.0 over HTTP。Bearer token 优先, api_key fallback。
    Accept 必须含 application/json, text/event-stream (MCP Streamable HTTP 要求)
    """
    url = f'{MCP_BASE}?api_key={API_KEY}' if API_KEY else MCP_BASE
    body = {
        'jsonrpc': '2.0',
        'id': int(time.time() * 1000) % 100000,
        'method': method,
        'params': params or {},
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
    }
    if BEARER_TOKEN:
        headers['Authorization'] = f'Bearer {BEARER_TOKEN}'
    try:
        req = urllib.request.Request(url,
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers=headers, method='POST')
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read().decode('utf-8', errors='replace')
        payload = None
        if raw.startswith('event:'):
            for line in raw.splitlines():
                if line.startswith('data:'):
                    try:
                        payload = json.loads(line[5:].strip())
                        break
                    except: continue
        if payload is None:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return True, raw[:200]
        if 'error' in payload:
            return False, f"RPC error: {payload['error']}"
        return True, payload.get('result', payload)
    except urllib.error.HTTPError as e:
        try: err_body = e.read().decode('utf-8', errors='replace')[:300]
        except: err_body = ''
        return False, f'HTTP {e.code}: {err_body}'
    except Exception as e:
        return False, str(e)


def zsxq_create_topic(title, content):
    text = f'【机构内参】{title}\n\n{content}'
    args = {
        'group_id': GROUP_ID,
        'title': title,
        'content': text,
        'type': 'talk',
        'text_type': 'markdown',
        'creation_statement': 'aigc',
    }
    ok, payload = mcp_call('tools/call', {'name': 'create_topic', 'arguments': args})
    if ok:
        # 解析 inner JSON 字符串(MCP 包了一层)
        if isinstance(payload, dict) and 'content' in payload:
            for c in payload.get('content', []):
                if c.get('type') == 'text':
                    try:
                        inner = json.loads(c['text'])
                        if inner.get('success'):
                            tid = inner.get('topic', {}).get('topic_id', '?')
                            return True, f'topic_id={tid}'
                        else:
                            return False, f'API error: {inner.get("error", inner)}'
                    except: pass
        return True, str(payload)[:300]
    return False, str(payload)[:500]


def find_files(data_dir, date=None):
    """支持目录或 summarized.json 入口"""
    p = Path(data_dir)
    if not p.exists(): return []
    if p.is_file() and p.suffix == '.json':
        items = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        out = []
        for it in items:
            rec_id = it.get('rec_id', '')
            title = it.get('title', '无标题')
            # 优先原文(T003 preview),其次 AI 摘要
            body = it.get('body') or it.get('full') or it.get('ai_summary') or ''
            pub = it.get('pub_time', '')
            # 优先 stock_names (中文名+代码),其次 stocks (代码)
            stock_names = it.get('stock_names', [])
            stocks = it.get('stocks', [])
            if stock_names and stocks:
                stock_str = ', '.join(f"{c}{n}" for c, n in zip(stocks, stock_names))
            elif stock_names:
                stock_str = ', '.join(stock_names)
            elif stocks:
                stock_str = ', '.join(stocks)
            else:
                stock_str = '未识别'
            text = f"【机构内参】{title}\n时间：{pub}\n个股：{stock_str}\n\n{body}"
            tmp = p.parent / f'.zsxq_push_{rec_id}.md'
            tmp.write_text(text, encoding='utf-8')
            out.append(tmp)
        return out
    if date:
        day_dir = p / date
        return sorted(day_dir.glob('*.md')) if day_dir.exists() else []
    days = sorted([d for d in p.iterdir() if d.is_dir()], reverse=True)
    if not days: return []
    return sorted(days[0].glob('*.md'))


def read_md(md_path):
    text = Path(md_path).read_text(encoding='utf-8', errors='replace')
    lines = text.split('\n')
    title = ''
    body = text
    if lines and lines[0].startswith('【机构内参】'):
        title = lines[0].replace('【机构内参】', '').strip()
        body = '\n'.join(lines[1:]).strip()
    return title, body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='data')
    parser.add_argument('--date', help='only push this date (YYYY-MM-DD)')
    parser.add_argument('--list-tools', action='store_true', help='list MCP tools and exit (debug)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.list_tools:
        ok, payload = mcp_call('tools/list', {})
        print(json.dumps(payload, ensure_ascii=False, indent=2) if ok else f'ERR: {payload}')
        return

    if not GROUP_ID:
        print('ERR: ZSXQ_GROUP_ID env not set'); sys.exit(1)
    if not BEARER_TOKEN and not API_KEY:
        print('ERR: need ZSXQ_OAUTH_TOKEN (preferred) or ZSXQ_MCP_KEY'); sys.exit(1)

    files = find_files(args.input, args.date)
    if not files:
        print(f'no md files found in {args.input}/{args.date or "latest"}'); return

    files = files[:30]

    if args.dry_run:
        print(f'[DRY-RUN] would push {len(files)} topics:')
        for f in files[:5]:
            t, _ = read_md(f)
            print(f'  - {t[:60]}...')
        return

    ok, fail = 0, 0
    tmp_to_cleanup = []
    try:
        for f in files:
            title, body = read_md(f)
            print(f'  push: {title[:60]}...', flush=True)
            success, msg = zsxq_create_topic(title, body)
            if success:
                ok += 1; print(f'    OK: {msg[:150]}')
            else:
                fail += 1; print(f'    FAIL: {msg[:300]}')
            time.sleep(2)
            if f.name.startswith('.zsxq_push_'):
                tmp_to_cleanup.append(f)
    finally:
        for f in tmp_to_cleanup:
            try: f.unlink()
            except: pass

    print(f'\nDONE: ok={ok} fail={fail}')


if __name__ == '__main__':
    main()