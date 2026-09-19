# jigou-neican (机构内参)

通达信机构内参每日抓取 → 知识星球《外资纪要社》 + IMA 知识库"外资纪要社/机构内参"文件夹。

## 架构 (B 方案)

```
通达信 hot.icfqs.com:7615/TQLEX
    ↓ 每日 20:00 cron
GitHub Actions (tdxjigouneican/jigou-neican)
    ↓
    ├→ jigou_fetcher.py: 抓取最新内参 → JSON
    ├→ agnes_summarize.py: agnes AI 摘要/标签/个股识别
    ├→ push_zsxq.py: → 知识星球《外资纪要社》(zsxq-cli topic +create)
    └→ push_ima.py: → IMA 知识库 (openapi/wiki/v1/add_knowledge)
    ↓
Render Web Service (Flask 只读 API) → Cloudflare Worker 反代 → jeeseek.top 子域
```

## 关键 ID

| 项 | 值 |
|---|---|
| 知识星球 | 《外资纪要社》 |
| IMA knowledge_base_id | `eD_gxNj7vxloDEYzjG9_9LEdABb_WBeI5Tqjs41lm_I=` |
| IMA folder_id (机构内参) | `folder_7506378096640223` |
| 通达信 API | `POST http://hot.icfqs.com:7615/TQLEX?Entry=CWServ.cfg_bk_jgnc` |
| 抓取脚本 | `src/jigou_fetcher.py` (原 `C:\Users\hua\.openclaw\workspace\jigou_fetcher.py`) |

## 本地开发

```bash
pip install -r requirements.txt
python src/jigou_fetcher.py today          # 抓最新一页
python src/jigou_fetcher.py backfill 2026-09-15 2026-09-16   # 回填
```

## 部署

1. Render Web Service（自动从 GitHub 部署）
2. Cloudflare Worker 反代 → `jgnc.jeeseek.top`
3. GitHub Actions cron `0 20 * * * Asia/Shanghai`
