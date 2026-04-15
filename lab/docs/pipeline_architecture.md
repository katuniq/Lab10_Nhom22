# Kiến trúc pipeline — Lab Day 10

**Nhóm:** Group 22 — Data Pipeline & Observability  
**Cập nhật:** 2026-04-15

---

## 1. Sơ đồ luồng

```
raw CSV ──► Transform (cleaning_rules.py) ──► Quality (expectations.py) ──► Embed (ChromaDB upsert)
              │                                        │ FAIL halt                    │
              ▼                                        ▼                              ▼
         quarantine CSV                          Pipeline HALT                 day10_kb collection
                                                                                      │
                                     manifest JSON (run_id, freshness)                ▼
                                     freshness_check ◄──────────────────────── Serving (Day 08/09)
```

**Điểm đo freshness:** `latest_exported_at` trong raw CSV → ghi vào `manifest_{run_id}.json` → so với `FRESHNESS_SLA_HOURS=24`.  
**run_id ghi tại:** `artifacts/manifests/manifest_{run_id}.json`.  
**Quarantine:** `artifacts/quarantine/quarantine_{run_id}.csv`.

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner nhóm |
|------------|-------|--------|--------------|
| Ingest | `data/raw/policy_export_dirty.csv` | `List[Dict[str,str]]` | Ingestion owner |
| Transform | raw rows | cleaned rows + quarantine rows | Cleaning owner |
| Quality | cleaned rows | `List[ExpectationResult]`, `should_halt` | Quality owner |
| Embed | cleaned rows | ChromaDB upsert + prune stale IDs | Embed owner |
| Monitor | manifest JSON | freshness PASS/WARN/FAIL log | Monitoring owner |

---

## 3. Idempotency & rerun

`chunk_id = SHA256(doc_id|chunk_text|seq)[:16]` — ổn định theo nội dung.  
Pipeline dùng `upsert` (không `add`): rerun 2 lần không tạo duplicate vector.  
Sau mỗi upsert, pipeline prune các `chunk_id` trong collection không còn có trong batch hiện tại (`embed_prune_removed`).

---

## 4. Liên hệ Day 09

Pipeline Day 10 phục vụ **collection riêng** (`day10_kb`, model `all-MiniLM-L6-v2`) để giảm phụ thuộc OpenAI API key.  
Day 09 multi-agent dùng collection `day09_docs` với OpenAI `text-embedding-3-small`.  
Nếu muốn chia sẻ corpus, cần export `cleaned_sprint-clean.csv` → re-index vào Day 09 bằng `day09/lab/index.py`.

---

## 5. Rủi ro đã biết

- **Freshness FAIL thường xuyên:** raw CSV trong lab có `exported_at=2026-04-10`, SLA=24h → luôn FAIL sau 1 ngày. Production cần cron trigger mỗi 12h.
- **BOM từ nguồn Excel:** Rule 7 xử lý inline, nhưng nếu source xuất UTF-16 thì `load_raw_csv` (utf-8-sig) sẽ fail.
- **Chunk count > 10 theo E8:** nếu tài liệu dài bị chia nhiều chunk (>10) sẽ WARN — cần điều chỉnh chunking strategy.
