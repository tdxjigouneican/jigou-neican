# -*- coding: utf-8 -*-
"""
jigou_fetcher.py — 通达信机构内参抓取 (Python 版, 永久版 v1.0)
================================================================
翻译自 jgnc_fetcher.js (Node.js, 9.16 升级前备份)
API: POST http://hot.icfqs.com:7615/TQLEX?Entry=CWServ.cfg_bk_jgnc

## 三个 Action:
- 001 → 板块分类树 (352 个板块, 4 层结构)
- 002 → 内参列表 (分页, 字段 T001-T012 + rec_id)
- 003 → 单条详情 (按 rec_id 列表批量)

## 字段映射:
- T001: 发布时间 (YYYYMMDDhhmm)
- T002: 标题
- T003: 预览正文
- T004: 完整正文 (****** = 付费锁定)
- T005/T007/T009: 关联股票代码
- T006/T008/T010: 关联股票名
- T011/T012: 板块字段
- rec_id: 唯一 ID (string)

## 存档:
- F:\机构内参\YYYY-MM-DD\HH-MM_<title>_<rec_id>.md
- F:\机构内参\.seen.json     (已抓 rec_id 列表, 去重)
- F:\机构内参\.outbox.json   (enqueue 历史, 倒序)
- F:\机构内参\.stock_index.json (个股映射)

## 用法:
  python jigou_fetcher.py today          # 抓最新一页
  python jigou_fetcher.py backfill YYYY-MM-DD YYYY-MM-DD   # 回填
  python jigou_fetcher.py cats           # 列板块分类
  python jigou_fetcher.py detail REC_ID  # 单条详情

## Cron 建议:
  08:00 / 12:30 各跑一次 (每天)

## Bug Fix (2026-09-17):
- 文件名 HH:MM → HH-MM (避免 Windows 非法字符)
- 支持 pub_time 无前导零 ("8:00" → "08-00")
- rec_id 统一存为 string (避免 JSON int 转换)
"""
import urllib.request, json, gzip, os, re, sys, time
from datetime import datetime

HOST = 'hot.icfqs.com'
PORT = 7615
BASE = f'http://{HOST}:{PORT}'
OUT_DIR = r'F:\机构内参'
OUT_FILE = os.path.join(OUT_DIR, '.outbox.json')
SEEN_FILE = os.path.join(OUT_DIR, '.seen.json')
STOCK_INDEX = os.path.join(OUT_DIR, '.stock_index.json')

HDRS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': BASE + '/site/tdx-pc-hqpage/page-jgnc.html',
    'Origin': BASE,
    'Content-Type': 'application/json; charset=UTF-8',
    'Accept-Encoding': 'gzip, deflate',
}

COLS = ['T001','T002','T003','T004','T005','T006','T007','T008','T009','T010','T011','T012','rec_id']


def post(path, body, timeout=15):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data, headers=HDRS, method='POST')
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read()
        if r.headers.get('Content-Encoding', '') == 'gzip':
            try: raw = gzip.decompress(raw)
            except: pass
        return json.loads(raw.decode('utf-8'))
    except urllib.error.HTTPError as e:
        try: body_b = e.read().decode('utf-8', errors='replace')[:300]
        except: body_b = ''
        return {'ErrorCode': e.code, 'ErrorInfo': body_b}
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
    """返回 HH-MM 安全文件名时间 (无冒号)。处理 '8:00' / '08:00' 两种格式"""
    if not pub: return '00-00'
    # pub_time 形如 "2026-09-17 15:50" 或 "2026-09-17 8:00"
    m = re.match(r'^\d{4}-\d{2}-\d{2}\s+(\d{1,2}):(\d{2})', pub)
    if m:
        return f"{int(m.group(1)):02d}-{m.group(2)}"
    # 也兼容 "202609171550" 原始格式
    m2 = re.match(r'^\d{4}\d{2}\d{2}(\d{2})(\d{2})', pub)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return '00-00'


def row_to_item(row):
    o = dict(zip(COLS, row))
    pub_time = ''
    t1 = str(o.get('T001', ''))
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
    stock_str = ', '.join(s['code'] + s['name'] for s in stocks) or '未识别'
    text = f"【机构内参】{title}\n时间：{pub_time}\n个股：{stock_str}\n\n{preview}"
    return {
        'rec_id': rec_id,
        'pub_time': pub_time,
        'title': title,
        'body': preview,
        'text': text,
        'stocks': [s['code'] for s in stocks],
        'stock_names': [s['name'] for s in stocks],
        'paid': not full,
        'enqueue_time': datetime.now().isoformat(timespec='seconds') + 'Z',
    }


def fetch_categories():
    r = post('/TQLEX?Entry=CWServ.cfg_bk_jgnc', {'Params': ['001', '', '', '', '', '', '']})
    if r.get('ErrorCode') != 0:
        return None, r
    rs = r['ResultSets'][0]
    return [dict(zip(rs['ColName'], row)) for row in rs['Content']], r


def fetch_list(itemValue='', bklx='', page=1, pageSize=30):
    r = post('/TQLEX?Entry=CWServ.cfg_bk_jgnc',
             {'Params': ['002', itemValue, bklx, '', '', str(page), str(pageSize)]})
    if r.get('ErrorCode') != 0:
        return [], 0, r
    rs = r['ResultSets'][0]
    items = [row_to_item(row) for row in rs['Content']]
    total_rs = r['ResultSets'][1] if len(r['ResultSets']) > 1 else None
    total = total_rs['Content'][0][0] if total_rs and total_rs.get('Content') else len(items)
    return items, int(total), r


def fetch_detail(rec_ids):
    if isinstance(rec_ids, (str, int)): rec_ids = [rec_ids]
    ids = ','.join(str(r) for r in rec_ids)
    r = post('/TQLEX?Entry=CWServ.cfg_bk_jgnc',
             {'Params': ['003', '', '', ids, '', '', '']})
    if r.get('ErrorCode') != 0:
        return [], r
    rs = r['ResultSets'][0]
    return [row_to_item(row) for row in rs['Content']], r


def load_seen():
    if os.path.exists(SEEN_FILE):
        try: return set(json.load(open(SEEN_FILE, encoding='utf-8')))
        except: return set()
    return set()


def save_seen(seen):
    seen_list = sorted(seen, key=lambda x: -int(x) if str(x).isdigit() else 0)
    json.dump(seen_list, open(SEEN_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def load_outbox():
    if os.path.exists(OUT_FILE):
        try: return json.load(open(OUT_FILE, encoding='utf-8'))
        except: return []
    return []


def save_outbox(items):
    existing = load_outbox()
    existing_ids = {str(it.get('rec_id')) for it in existing if it.get('rec_id')}
    new_items = [it for it in items if str(it.get('rec_id')) not in existing_ids]
    merged = existing + new_items
    merged.sort(key=lambda x: -int(x['rec_id']) if str(x.get('rec_id', '0')).isdigit() else 0)
    json.dump(merged[:500], open(OUT_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return len(new_items)


def write_md_files(items):
    by_date = {}
    for it in items:
        pub = it.get('pub_time', '')
        date = pub[:10] if len(pub) >= 10 else datetime.now().strftime('%Y-%m-%d')
        by_date.setdefault(date, []).append(it)
    n = 0
    for date, its in by_date.items():
        d = os.path.join(OUT_DIR, date)
        os.makedirs(d, exist_ok=True)
        for it in its:
            t = safe_time(it.get('pub_time', ''))
            safe_title = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', it.get('title',''))[:80]
            rec_id = it.get('rec_id', '')
            fn = f"{t}_{safe_title}_{rec_id}.md"
            p = os.path.join(d, fn)
            if not os.path.exists(p):
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(it.get('text', ''))
                n += 1
    return n


def cmd_today():
    """抓首页最新 50 条 (1 页)"""
    seen = load_seen()
    items, total, raw = fetch_list(page=1, pageSize=50)
    if not items:
        print(f"  ERR: {raw}"); return
    new_items = [it for it in items if it['rec_id'] not in seen]
    print(f"  total={total} got={len(items)} new={len(new_items)}")
    if new_items:
        n = write_md_files(new_items)
        for it in new_items: seen.add(it['rec_id'])
        save_seen(seen)
        delta = save_outbox(new_items)
        print(f"  WROTE: {n} md files | seen+={len(new_items)} | outbox+={delta}")


def cmd_backfill(start_date, end_date):
    """按日期范围回填: 翻页直到 pub_time 早于 start_date"""
    seen = load_seen()
    new_items = []
    page = 1
    max_pages = 400  # 10098 总数 / 50 每页 ≈ 202 页
    while page <= max_pages:
        items, _, _ = fetch_list(page=page, pageSize=50)
        if not items: break
        stop = False
        scanned_in_range = 0
        for it in items:
            pub = it.get('pub_time', '')[:10]
            if pub < start_date:
                print(f"  page {page}: Reached pub<{start_date} (got {pub}), stop")
                stop = True
                break
            if pub > end_date:
                continue
            scanned_in_range += 1
            if it['rec_id'] not in seen:
                seen.add(it['rec_id'])
                new_items.append(it)
        print(f"  page {page}: scanned={len(items)} in_range={scanned_in_range} new_so_far={len(new_items)}")
        if stop: break
        page += 1
    if new_items:
        n = write_md_files(new_items)
        save_seen(seen)
        delta = save_outbox(new_items)
        # 统计按日期分布
        by_date = {}
        for it in new_items:
            pub = it.get('pub_time', '')[:10]
            by_date[pub] = by_date.get(pub, 0) + 1
        print(f"  WROTE: {n} md files | seen+={len(new_items)} | outbox+={delta}")
        print(f"  By date:")
        for d in sorted(by_date.keys()):
            print(f"    {d}: {by_date[d]} items")


def cmd_cats():
    cats, raw = fetch_categories()
    if cats is None:
        print(f"  ERR: {raw}"); return
    print(f"  Categories: {len(cats)}")
    for c in cats[:10]:
        print(f"    {c}")


def cmd_detail(rec_id):
    items, raw = fetch_detail(rec_id)
    if not items:
        print(f"  ERR: {raw}"); return
    it = items[0]
    print(f"  rec_id: {it['rec_id']}")
    print(f"  title: {it['title']}")
    print(f"  pub_time: {it['pub_time']}")
    print(f"  stocks: {it['stocks']}")
    print(f"  body preview: {it['body'][:300]}")


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'today'
    print(f"[jigou_fetcher] mode={mode} {datetime.now().isoformat(timespec='seconds')}")
    if mode == 'today':
        cmd_today()
    elif mode == 'backfill':
        if len(sys.argv) < 4:
            print("Usage: jigou_fetcher.py backfill START_DATE END_DATE (YYYY-MM-DD)")
            sys.exit(1)
        cmd_backfill(sys.argv[2], sys.argv[3])
    elif mode == 'cats':
        cmd_cats()
    elif mode == 'detail':
        if len(sys.argv) < 3:
            print("Usage: jigou_fetcher.py detail REC_ID")
            sys.exit(1)
        cmd_detail(sys.argv[2])
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
    print(f"  Done.")
