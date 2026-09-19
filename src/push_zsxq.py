# -*- coding: utf-8 -*-
"""push_zsxq.py — 推送机构内参到知识星球《外资纪要社》
用 zsxq-cli (官方 v0.5.0+) 的 `topic +create` 命令
"""
import os, sys, json, subprocess, argparse, time
from pathlib import Path

ZSXQ_CLI = os.environ.get('ZSXQ_CLI', 'zsxq-cli')
GROUP_ID = os.environ.get('ZSXQ_GROUP_ID', '')  # 《外资纪要社》的 group_id

def find_files(data_dir, date=None):
    """支持两种输入:
    - data_dir 是目录 → 找 YYYY-MM-DD/*.md
    - data_dir 是 summarized.json → 解析 rec_id/title/body,产出合成"伪文件"流
    """
    p = Path(data_dir)
    if not p.exists(): return []
    # summarized.json 入口
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
            # 临时文件,让 read_md 复用现有解析逻辑
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
    # 抽取标题（第一行）
    lines = text.split('\n')
    title = ''
    body = text
    if lines and lines[0].startswith('【机构内参】'):
        title = lines[0].replace('【机构内参】', '').strip()
        body = '\n'.join(lines[1:]).strip()
    return title, body

def zsxq_create_topic(title, content):
    """调 zsxq-cli topic +create"""
    if not GROUP_ID:
        return False, 'ZSXQ_GROUP_ID env not set'

    # 构造 zsxq-cli 调用
    # zsxq-cli topic +create --group-id <id> --text "..." [--files ...]
    # ⚠️ zsxq-cli 的 --text 参数对长文本需要 escape
    cmd = [
        ZSXQ_CLI, 'topic', '+create',
        '--group-id', GROUP_ID,
        '--text', f'【机构内参】{title}\n\n{content}',
    ]
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

    files = find_files(args.input, args.date)
    if not files:
        print(f'no md files found in {args.input}/{args.date or "latest"}')
        return

    # 限制每天最多发 30 条（避免刷屏）
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
            time.sleep(2)  # 避免刷屏
            if f.name.startswith('.zsxq_push_'):
                tmp_to_cleanup.append(f)
    finally:
        for f in tmp_to_cleanup:
            try: f.unlink()
            except: pass

    print(f'\nDONE: ok={ok} fail={fail}')

if __name__ == '__main__':
    main()
