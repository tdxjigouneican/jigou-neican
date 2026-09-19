# -*- coding: utf-8 -*-
"""push_zsxq.py — 推送机构内参到知识星球《外资纪要社》

走 zsxq-cli OAuth(回归 v1.0,绕开 MCP server 的 UTF-8/GBK 编码 bug)。

CLI: zsxq-cli topic +create --group-id <id> --text "..." [--files ...]
Auth: zsxq-cli auth login (token 存 ~/.config/zsxq-cli/token.json)
"""
import os, sys, json, subprocess, argparse, time
from pathlib import Path

ZSXQ_CLI = os.environ.get('ZSXQ_CLI', 'zsxq-cli')
GROUP_ID = os.environ.get('ZSXQ_GROUP_ID', '48885115254258')


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


def zsxq_create_topic(title, content):
    """调 zsxq-cli topic +create (v0.5.0+)
    通过 stdin 传 --text 避开命令行长度限制 + escape 问题
    """
    if not GROUP_ID:
        return False, 'ZSXQ_GROUP_ID env not set'

    text = f'【机构内参】{title}\n\n{content}'

    # 先看 zsxq-cli 帮助,确认正确调用方式
    # v0.5.0: zsxq-cli topic +create --group-id <id> --text <text>
    # text 很长时用 stdin 或文件传入
    cmd = [ZSXQ_CLI, 'topic', '+create', '--group-id', GROUP_ID, '--text', text]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                encoding='utf-8', errors='replace')
        if result.returncode == 0:
            return True, result.stdout[:500]
        return False, f'rc={result.returncode} stderr={result.stderr[:500]}'
    except FileNotFoundError:
        return False, f'zsxq-cli not found at {ZSXQ_CLI}'
    except subprocess.TimeoutExpired:
        return False, 'timeout'
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='data')
    parser.add_argument('--date', help='only push this date (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if not GROUP_ID:
        print('ERR: ZSXQ_GROUP_ID env not set'); sys.exit(1)

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
                ok += 1; print(f'    OK: {msg[:100]}')
            else:
                fail += 1; print(f'    FAIL: {msg[:200]}')
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