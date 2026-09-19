# -*- coding: utf-8 -*-
"""push_ima.py — 推送机构内参到 IMA 知识库《外资纪要社/机构内参》文件夹
- IMA API: POST https://ima.qq.com/openapi/wiki/v1/{endpoint}
- Auth headers: ima-openapi-clientid, ima-openapi-apikey, ima-openapi-ctx
- 完整流程: check_repeated → create_media → COS upload → add_knowledge
"""
import os, sys, json, hashlib, hmac, urllib.request, urllib.error, urllib.parse, argparse
from pathlib import Path

IMA_BASE = 'https://ima.qq.com'
KB_ID = os.environ.get('IMA_KB_ID', 'eD_gxNj7vxloDEYzjG9_9LEdABb_WBeI5Tqjs41lm_I=')
FOLDER_ID = os.environ.get('IMA_FOLDER_ID', 'folder_7506378096640223')
CLIENT_ID = os.environ.get('IMA_CLIENT_ID', '')
API_KEY = os.environ.get('IMA_API_KEY', '')
MEDIA_TYPE_MAP = {'pdf':1,'doc':3,'docx':3,'ppt':4,'pptx':4,'xls':5,'xlsx':5,
                  'md':7,'markdown':7,'txt':14,'jpg':13,'jpeg':13,'png':13}

H_AUTH = {
    'ima-openapi-clientid': CLIENT_ID,
    'ima-openapi-apikey': API_KEY,
    'ima-openapi-ctx': 'skill_version=1.1.8',
    'Content-Type': 'application/json; charset=utf-8',
}

def call(path, body):
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f'{IMA_BASE}/{path}', data=data, headers=H_AUTH, method='POST')
    try:
        u = urllib.request.urlopen(req, timeout=20)
        raw = u.read()
        try: return u.status, json.loads(raw.decode('utf-8'))
        except: return u.status, raw[:500].decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        try: return e.code, e.read().decode('utf-8', errors='replace')[:1000]
        except: return -1, ''
    except Exception as e: return -1, str(e)

def cos_put(secret_id, secret_key, token, bucket, region, cos_key, file_bytes,
            start_time, expired_time, content_type='application/octet-stream'):
    hostname = f'{bucket}.cos.{region}.myqcloud.com'
    pathname = f'/{cos_key}'
    key_time = f'{start_time};{expired_time}'
    sign_headers = {'content-length': str(len(file_bytes)), 'host': hostname}
    sign_key = hmac.new(secret_key.encode('utf-8'), key_time.encode('utf-8'), hashlib.sha1).hexdigest()
    header_keys = sorted(sign_headers.keys())
    http_headers = '&'.join(f'{k.lower()}={urllib.parse.quote(sign_headers[k], safe="")}' for k in header_keys)
    http_string = f'put\n{pathname}\n\n{http_headers}\n'
    string_to_sign = f'sha1\n{key_time}\n{hashlib.sha1(http_string.encode("utf-8")).hexdigest()}\n'
    signature = hmac.new(sign_key.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha1).hexdigest()
    header_list = ';'.join(k.lower() for k in header_keys)
    auth = (f'q-sign-algorithm=sha1&q-ak={secret_id}&q-sign-time={key_time}'
            f'&q-key-time={key_time}&q-header-list={header_list}&q-url-param-list=&q-signature={signature}')
    req = urllib.request.Request(
        f'https://{hostname}{pathname}', data=file_bytes, method='PUT',
        headers={'Content-Type': content_type, 'Content-Length': str(len(file_bytes)),
                 'Authorization': auth, 'x-cos-security-token': token},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.status, resp.read()[:500].decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        try: return e.code, e.read()[:500].decode('utf-8', errors='replace')
        except: return -1, ''
    except Exception as e: return -1, str(e)

def upload_one(filepath):
    """上传一个文件到 IMA。返回 (success: bool, msg: str, media_id: str)"""
    p = Path(filepath)
    if not p.exists():
        return False, f'file not found: {filepath}', ''
    file_name = p.name
    file_size = p.stat().st_size
    file_ext = p.suffix.lstrip('.') or 'md'
    media_type = MEDIA_TYPE_MAP.get(file_ext.lower(), 7)
    content_type = f'text/{file_ext}' if file_ext.lower() in ('md','markdown') else f'application/{file_ext}'

    # Step 3: check
    s, r = call('openapi/wiki/v1/check_repeated_names', {
        'params': [{'name': file_name, 'media_type': media_type}],
        'knowledge_base_id': KB_ID, 'folder_id': FOLDER_ID,
    })
    if isinstance(r, dict) and r.get('code') == 0:
        results = r.get('data', {}).get('results', [])
        if results and results[0].get('is_repeated'):
            return False, f'already exists: {file_name}', ''

    # Step 4: create_media
    s2, r2 = call('openapi/wiki/v1/create_media', {
        'file_name': file_name, 'file_size': file_size, 'content_type': content_type,
        'knowledge_base_id': KB_ID, 'file_ext': file_ext,
    })
    if not (isinstance(r2, dict) and r2.get('code') == 0):
        return False, f'create_media failed: {r2}', ''
    d = r2['data']
    media_id = d['media_id']
    cos = d['cos_credential']

    # Step 5: COS upload
    with open(filepath, 'rb') as f:
        file_bytes = f.read()
    sc, sb = cos_put(
        secret_id=cos['secret_id'], secret_key=cos['secret_key'],
        token=cos['token'],
        bucket=cos['bucket_name'], region=cos['region'],
        cos_key=cos['cos_key'], file_bytes=file_bytes,
        start_time=cos['start_time'], expired_time=cos['expired_time'],
        content_type=content_type,
    )
    if not (200 <= sc < 300):
        return False, f'COS upload failed: {sc} {sb}', ''

    # Step 6: add_knowledge
    s3, r3 = call('openapi/wiki/v1/add_knowledge', {
        'media_type': media_type, 'media_id': media_id,
        'title': file_name,  # GATE 2: title = file_name
        'knowledge_base_id': KB_ID, 'folder_id': FOLDER_ID,
        'file_info': {
            'cos_key': cos['cos_key'], 'file_size': file_size, 'file_name': file_name,
        },
    })
    if isinstance(r3, dict) and r3.get('code') == 0:
        return True, f'uploaded: {file_name}', media_id
    return False, f'add_knowledge failed: {r3}', ''

def collect_md_paths(data_dir, date=None):
    """支持目录或 summarized.json 入口。返回 [(day_label, md_path), ...]"""
    p = Path(data_dir)
    if not p.exists():
        return []
    # summarized.json 入口:把每个 item 物化成临时 .md
    if p.is_file() and p.suffix == '.json':
        items = json.loads(p.read_text(encoding='utf-8', errors='replace'))
        out = []
        tmp_paths = []
        for it in items:
            rec_id = it.get('rec_id', '')
            title = it.get('title', '无标题')
            body = it.get('ai_summary') or it.get('body') or ''
            pub = it.get('pub_time', '')
            stocks = it.get('stocks', [])
            stock_str = ', '.join(stocks) if stocks else '未识别'
            text = f"【机构内参】{title}\n时间：{pub}\n个股：{stock_str}\n\n{body}"
            day = pub[:10] if len(pub) >= 10 else 'unknown'
            tmp = p.parent / f'.ima_push_{rec_id}.md'
            tmp.write_text(text, encoding='utf-8')
            tmp_paths.append(tmp)
            out.append((day, tmp))
        # 把清理用的 tmp 列表挂到 out 末尾(用单元素元组哨兵)
        out.append(('__CLEANUP__', tmp_paths))
        return out

    if date:
        days = [date]
    else:
        days = sorted([d.name for d in p.iterdir() if d.is_dir()], reverse=True)
        if days: days = [days[0]]

    out = []
    for d in days:
        day_dir = p / d
        if not day_dir.exists(): continue
        for f in sorted(day_dir.iterdir()):
            if f.suffix.lower() == '.md':
                out.append((d, f))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', '-i', default='data', help='data dir (YYYY-MM-DD/*.md) or summarized.json')
    parser.add_argument('--date', help='only upload this date (YYYY-MM-DD), default = latest')
    args = parser.parse_args()

    if not CLIENT_ID or not API_KEY:
        print('ERR: IMA_CLIENT_ID / IMA_API_KEY env not set'); sys.exit(1)

    data_dir = Path(args.input)
    if not data_dir.exists():
        print(f'ERR: data dir not found: {data_dir}'); sys.exit(1)

    pairs = collect_md_paths(data_dir, args.date)
    tmp_to_cleanup = []
    try:
        total_ok, total_fail = 0, 0
        for entry in pairs:
            if entry[0] == '__CLEANUP__':
                tmp_to_cleanup = entry[1]
                continue
            d, f = entry
            print(f'  [{d}] {f.name}', flush=True)
            ok, msg, _ = upload_one(str(f))
            print(f'    -> {"OK" if ok else "FAIL"}: {msg}', flush=True)
            if ok: total_ok += 1
            else: total_fail += 1
        print(f'\nDONE: ok={total_ok} fail={total_fail}')
    finally:
        for f in tmp_to_cleanup:
            try: f.unlink()
            except: pass

if __name__ == '__main__':
    main()
