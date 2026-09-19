# -*- coding: utf-8 -*-
"""Flask read-only API for jigou-neican"""
from flask import Flask, jsonify, send_from_directory
import os, json
from datetime import datetime, timedelta

app = Flask(__name__)

DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), '..', 'data'))

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

@app.route('/api/today')
def today():
    date = datetime.now().strftime('%Y-%m-%d')
    return _list_day(date)

@app.route('/api/day/<date>')
def day(date):
    return _list_day(date)

@app.route('/api/recent')
def recent():
    out = []
    if not os.path.exists(DATA_DIR):
        return jsonify({'items': []})
    days = sorted([d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))], reverse=True)
    for d in days[:7]:
        items = _list_day(d).get_json().get('items', [])
        out.append({'date': d, 'items': items})
    return jsonify({'days': out})

def _list_day(date):
    day_dir = os.path.join(DATA_DIR, date)
    if not os.path.exists(day_dir):
        return jsonify({'date': date, 'items': [], 'error': 'no data'})
    items = []
    for fn in sorted(os.listdir(day_dir)):
        if fn.endswith('.md'):
            fp = os.path.join(day_dir, fn)
            try:
                content = open(fp, encoding='utf-8').read()
                rec_id = fn.rsplit('_', 1)[-1].replace('.md', '')
                items.append({
                    'file': fn,
                    'rec_id': rec_id,
                    'preview': content[:500],
                })
            except Exception as e:
                items.append({'file': fn, 'error': str(e)})
    return jsonify({'date': date, 'count': len(items), 'items': items})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
