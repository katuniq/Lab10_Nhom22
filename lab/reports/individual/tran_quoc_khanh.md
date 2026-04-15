# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trần Quốc Khánh  
**Vai trò:** Embed & Idempotency Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** 540 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `etl_pipeline.py` — Embeding layer (ChromaDB upsert, idempotent key strategy, prune logic)
- `chroma_db/` — Vector database lưu trữ, collection management (`day10_kb`)
- `.env` — Config embedding model (`all-MiniLM-L6-v2`), ChromaDB path
- Phần idempotency documentation (`docs/pipeline_architecture.md`)

**Kết nối với thành viên khác:**
- Nhận 6 cleaned records từ Đỗ Đình Hoàn (Cleaning)
- Ghi manifest + metadata cho Nguyễn Xuân Tùng (Monitoring)
- Cung cấp collection statistics cho Nguyễn Công Thành (Grading evaluation)
- Ghi run_id vào collection metadata để tracking lineage

**Bằng chứ cứ:**
- `embed_upsert count=6` trong log pipeline
- `chroma_db/` directory với 6 indexed documents
- `artifacts/manifests/manifest_2026-04-15T09-21Z.json` ghi `embed_upsert_count=6`

---

## 2. Một quyết định kỹ thuật

**Idempotency Strategy:** Dùng stable **chunk_id** (SHA256 hash của normalized content) làm ChromaDB doc ID, thay vì sequential ID hoặc timestamp. Khi rerun pipeline với same cleaned CSV:
- Chunk cũ nhất (id=X) nếu unchanged → upsert với cùng ID, metadata update (exported_at, run_id)
- Chunk mất (quarantine trong lần mới) → **prune** (xóa từ collection)
- Chunk mới → insert vào collection

Benefit: `etl_pipeline.py run` chạy lại→ collection luôn sync với latest cleaned data. Không tích tụ vector cũ → retrieval không nhầm lẫn.

---

## 3. Một lỗi đã xử lý

**Triệu chứng:** Chạy pipeline lần 2 (modify 1 cleaning rule, rerun), collection vẫn chứa 7 vectors từ lần 1. Khi query refund question, trả lại cả "7 ngày" (lần 2) và "14 ngày" (cũ từ lần 1) → retrieval rank confusion.

**Phát hiện:** Kiểm log embedding → `embed_upsert count=6` nhưng `chroma_db` vẫn có dòng "14 ngày". ChromaDB upsert mặc định không xóa vectors không có trong cleaned set.

**Fix:** Implement prune logic: sau upsert 6 vectors, so sánh IDs trong collection với IDs trong cleaned CSV → remove không match. Log: `embed_prune_removed=1` (xóa chunk "14 ngày" stale từ lần 1). Collection sau đó clean, query refund chỉ trả "7 ngày" ✓.

---

## 4. Bằng chứng trước / sau

**Sau fix idempotency (run_id=2026-04-15T09-21Z):**
```
Collection before prune: 7 vectors
Collection after prune: 6 vectors
embed_upsert_count=6, embed_prune_removed=1
```

**Query refund_window before prune:**
```
hits_forbidden=yes (top-5 chứa cả "7 ngày" + "14 ngày")
```

**Query refund_window after prune:**
```
hits_forbidden=no (top-5 chỉ "7 ngày")
contains_expected=yes ✓
```

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: Implement **embedding version tracking** − store model version + embedding date trong ChromaDB collection metadata. Khi model update (upgrade `all-MiniLM` → `all-MiniLM-L12`), tự động detect version mismatch + suggest re-embed toàn collection (vì embedding từ 2 model không so sánh được). Hiện tại format manual, auto-detect sẽ tránh silent failure khi model thay đổi.
