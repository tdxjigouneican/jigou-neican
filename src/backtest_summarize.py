# -*- coding: utf-8 -*-
"""backtest_summarize.py — AI 摘要质量回测

用途:对历史 .md 文件跑 agnes_summarize,把输出汇总统计:
- importance 分布(1-5)
- tag 命中率(每个 tag 出现次数)
- 摘要长度分布(平均/中位/最长/最短)
- ai_summary 与 body 长度比(检查"灌水")
- 错误率(网络失败 / JSON 解析失败)

输出:stdout 报告 + data/backtest_YYYYMMDD.json
"""
import os, sys, json, argparse, statistics
from pathlib import Path
from collections import Counter

# 直接复用 agnes_summarize
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agnes_summarize import process_md

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='data')
    parser.add_argument('--limit', type=int, default=20, help='max files to backtest')
    parser.add_argument('--output', '-o', default=None)
    args = parser.parse_args()

    p = Path(args.input)
    files = []
    for d in sorted([x for x in p.iterdir() if x.is_dir()], reverse=True):
        files.extend(sorted(d.glob('*.md')))
    files = files[:args.limit]
    if not files:
        print('no md files found'); return

    print(f'[backtest] processing {len(files)} files...')
    results = []
    for f in files:
        r = process_md(f)
        results.append(r)

    # 统计
    ok = [r for r in results if 'error' not in r]
    fail = [r for r in results if 'error' in r]

    imp_dist = Counter(r.get('importance', 0) for r in ok)
    tag_counter = Counter()
    sum_lens, body_lens = [], []
    for r in ok:
        for t in r.get('tags', []):
            tag_counter[t] += 1
        s = r.get('ai_summary', '')
        b = r.get('body', '')
        sum_lens.append(len(s))
        body_lens.append(len(b))

    print('\n=== Backtest Report ===')
    print(f'Total: {len(results)} | OK: {len(ok)} | FAIL: {len(fail)}')
    if fail:
        print(f'Error rate: {len(fail)/len(results)*100:.1f}%')
        for r in fail[:3]:
            print(f"  - {r.get('title','')[:40]}: {r.get('error','')[:80]}")
    print(f'\nImportance distribution:')
    for i in range(1, 6):
        n = imp_dist.get(i, 0)
        pct = n / len(ok) * 100 if ok else 0
        bar = '█' * int(pct / 5)
        print(f'  {i}★: {n:4d} ({pct:5.1f}%) {bar}')
    print(f'\nTop 20 tags:')
    for t, c in tag_counter.most_common(20):
        print(f'  {t}: {c}')
    if sum_lens:
        print(f'\nSummary length: avg={statistics.mean(sum_lens):.0f} '
              f'median={statistics.median(sum_lens):.0f} '
              f'min={min(sum_lens)} max={max(sum_lens)}')
        ratios = [s/b for s,b in zip(sum_lens, body_lens) if b > 0]
        if ratios:
            print(f'Summary/Body ratio: avg={statistics.mean(ratios):.2f} '
                  f'(>1.0 警惕"灌水",<0.3 警惕"信息丢失")')

    if args.output:
        Path(args.output).write_text(
            json.dumps({
                'total': len(results), 'ok': len(ok), 'fail': len(fail),
                'importance_dist': dict(imp_dist),
                'tag_counter': dict(tag_counter),
                'summary_len': sum_lens,
                'body_len': body_lens,
                'results': results,
            }, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        print(f'\nWrote: {args.output}')

if __name__ == '__main__':
    main()