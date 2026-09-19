# -*- coding: utf-8 -*-
"""push_zsxq.py — 推送机构内参到知识星球《外资纪要社》

走 zsxq MCP (Model Context Protocol) endpoint,直接 HTTP POST JSON-RPC 2.0。
不再依赖 zsxq-cli 子进程或 OAuth token 持久化。

认证:api_key 通过 query 参数传递 (ZSXQ_MCP_KEY 环境变量)
端点:https://mcp.zsxq.com/topic/mcp

参考 MCP 标准协议:
  - initialize / tools/list / tools/call
  - 请求:{"jsonrpc":"2.0","id":N,"method":"tools/call","params":{"name":"create_topic","arguments":{...}}}
  - 响应:{"jsonrpc":"2.0","id":N,"result":{...}} 或 {"error":{...}}
"""
import os, sys, json, urllib.request, urllib.error, argparse, time
from pathlib import Path

MCP_BASE = 'https://mcp.zsxq.com/topic/mcp'
API_KEY = os.environ.get('ZSXQ_MCP_KEY', '')
GROUP_ID = os.environ.get('ZSXQ_GROUP_ID', '')


def mcp_call(method, params=None, timeout=30):
    """JSON-RPC 2.0 over HTTP。返回 (ok, payload)"""
    if not API_KEY:
        return False, 'ZSXQ_MCP_KEY env not set'
    url = f'{MCP_BASE}?api_key={API_KEY}'
    body = {
        'jsonrpc': '2.0',
        'id': int(time.time() * 1000) % 100000,
        'method': method,
        'params': params or {},
    }
    try:
        req = urllib.request.Request(url,
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8',
                     'Accept': 'application/json, text/event-stream'},
            method='POST')
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read().decode('utf-8', errors='replace')
        # MCP Streamable HTTP 响应可能是 JSON 或 SSE (event: message + data: ...)
        payload = None
        if raw.startswith('event:'):
            # 解析 SSE:取每段 data:
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
        try:
            err_body = e.read().decode('utf-8', errors='replace')[:300]
        except: err_body = ''
        return False, f'HTTP {e.code}: {err_body}'
    except Exception as e:
        return False, str(e)


def zsxq_create_topic(title, content):
    """通过 MCP tools/call 调用 create_topic 工具
    schema (来自 list-tools):
      required: group_id
      optional: title, content, type (talk|q&a), text_type (markdown|plain),
                creation_statement, image_ids, file_ids
    """
    text = f'【机构内参】{title}\n\n{content}'
    args = {
        'group_id': GROUP_ID,
        'title': title,
        'content': text,
        'type': 'talk',
        'text_type': 'markdown',
    }
    ok, payload = mcp_call('tools/call', {'name': 'create_topic', 'arguments': args})
    if ok:
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
            body = it.get('ai_summary') or it.get('body') or ''
            pub = it.get('pub_time', '')
            stocks = it.get('stocks', [])
            stock_str = ', '.join(stocks) if stocks else '未识别'
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
    if not API_KEY:
        print('ERR: ZSXQ_MCP_KEY env not set'); sys.exit(1)

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