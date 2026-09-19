# -*- coding: utf-8 -*-
r"""jigou_fetcher.py - TDX institutional briefing fetcher (GitHub Actions version)
Based on local version at workspace/jigou_fetcher.py
"""
import urllib.request, urllib.parse, json, gzip, os, re, sys, time, argparse
from datetime import datetime, timedelta

TDX_BASE = os.environ.get('TDX_API_BASE', 'http://hot.icfqs.com:7615')
ENTRY = 'CWServ.cfg_bk_jgnc'
COLS = ['T001','T002','T003','T004','T005','T006','T007','T008','T009','T010','T011','T012','rec_id']

def post(path, body, timeout=15):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(f'{TDX_BASE}{path}', data=data, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': f'{TDX_BASE}/site/tdx-pc-hqpage/page-jgnc.html',
        'Origin': TDX_BASE,
        'Content-Type': 'application/json; charset=UTF-8',
        'Accept-Encoding': 'gzip, deflate',
    }, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
        if r.headers.get('Content-Encoding', '') == 'gzip':
            try: raw = gzip.decompress(raw)
            except: pass
        return json.loads(raw.decode('utf-8'))
    except Exception as e:
        return {'ErrorCode': -1, 'ErrorInfo': str(e)}

def strip_html(html):
    if not html: return ''
    s = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    s = re.sub(r'</p>', '\n\n', s, flags=re.IGNORECASE)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    return re.sub(r'[ \t]+', ' ', s).strip()

def safe_time(pub):
    if not pub: return '00-00'
    m = re.match(r'^\d{4}-\d{2}-\d{2}\s+(\d{1,2}):(\d{2})', pub)
    if m: return f"{int(m.group(1)):02d}-{m.group(2)}"
    m2 = re.match(r'^\d{4}\d{2}\d{2}(\d{2})(\d{2})', pub)
    if m2: return f"{m2.group(1)}-{m2.group(2)}"
    return '00-00'

def row_to_item(row):
    o = dict(zip(COLS, row))
    t1 = str(o.get('T001', ''))
    pub_time = ''
    if re.match(r'^\d{12}$', t1):
        pub_time = f"{t1[:4]}-{t1[4:6]}-{t1[6:8]} {t1[8:10]}:{t1[10:12]}"
    else:
        pub_time = t1
    stocks = []
    for ck, nk in [('T005', 'T006'), ('T007', 'T008'), ('T009', 'T010')]:
        if o.get(ck) and o[ck] != '******':
            stocks.append({'code': o[ck], 'name': o[nk] or ''})
    preview = strip_html(o.get('T003') or '')
    full = strip_html(o.get('T004') or '') if o.get('T004') and o['T004'] != '******' else ''
    title = o.get('T002') or ''
    rec_id = str(o.get('rec_id', ''))
    return {
        'rec_id': rec_id,
        'pub_time': pub_time,
        'title': title,
        'body': preview,
        'full': full,
        'stocks': [s['code'] for s in stocks],
        'stock_names': [s['name'] for s in stocks],
        'paid': not full,
    }

def fetch_list(page=1, page_size=50):
    r = post(f'/TQLEX?Entry={ENTRY}', {'Params':['002','','','','',str(page),str(page_size)]})
    if r.get('ErrorCode') != 0: return [], 0
    rs = r['ResultSets'][0]
    items = [row_to_item(row) for row in rs['Content']]
    total_rs = r['ResultSets'][1] if len(r['ResultSets']) > 1 else None
    total = total_rs['Content'][0][0] if total_rs and total_rs.get('Content') else len(items)
    return items, int(total)

def save_md(items, output_dir):
    by_date = {}
    for it in items:
        pub = it.get('pub_time', '')
        date = pub[:10] if len(pub) >= 10 else datetime.now().strftime('%Y-%m-%d')
        by_date.setdefault(date, []).append(it)
    n = 0
    for date, its in by_date.items():
        d = os.path.join(output_dir, date)
        os.makedirs(d, exist_ok=True)
        for it in its:
            t = safe_time(it.get('pub_time', ''))
            safe_title = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', it.get('title', ''))[:80]
            rec_id = it.get('rec_id', '')
            fn = f"{t}_{safe_title}_{rec_id}.md"
            fp = os.path.join(d, fn)
            if not os.path.exists(fp):
                stock_str = ', '.join(it['stocks']) or '未识别'
                text = f"""【机构内参】{it['title']}
时间：{it['pub_time']}
个股：{stock_str}

{it['body']}
"""
                if it.get('full'):
                    text += f"\n\n=== 完整正文 ===\n{it['full']}\n"
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write(text)
                n += 1
    return n

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['today','backfill'], default='today')
    parser.add_argument('--output', '-o', default='data')
    parser.add_argument('--start', default=None, help='backfill start YYYY-MM-DD')
    parser.add_argument('--end', default=None, help='backfill end YYYY-MM-DD')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    if args.mode == 'today':
        items, total = fetch_list(page=1, page_size=50)
        if not items:
            print('ERR: no items'); sys.exit(1)
        n = save_md(items, args.output)
        print(f'OK today: total={total} got={len(items)} wrote={n} md files')
    elif args.mode == 'backfill':
        if not args.start or not args.end:
            print('ERR: --start and --end required'); sys.exit(1)
        new_items = []
        page = 1
        while page < 500:
            items, total = fetch_list(page=page, page_size=50)
            if not items: break
            stop = False
            for it in items:
                pub = it.get('pub_time', '')[:10]
                if pub < args.start: stop = True; break
                if pub > args.end: continue
                new_items.append(it)
            print(f'  page {page}: scanned={len(items)} total={total} new={len(new_items)}')
            if stop: break
            page += 1
        n = save_md(new_items, args.output)
        print(f'OK backfill: wrote {n} md files')

if __name__ == '__main__':
    main()
