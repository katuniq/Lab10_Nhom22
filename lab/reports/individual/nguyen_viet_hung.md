# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Việt Hùng  
**Vai trò:** Ingestion / Cleaning / Embed / Monitoring — toàn bộ pipeline  
**Ngày nộp:** 2026-04-15  
**Độ dài:** ~550 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**

- `transform/cleaning_rules.py` — toàn bộ logic cleaning, thêm Rule 7–9
- `quality/expectations.py` — thêm E7, E8
- `data/raw/policy_export_dirty.csv` — thêm 3 row inject (11–13) cho metric_impact
- `etl_pipeline.py` — pipeline orchestration (đọc, clean, validate, embed, manifest, freshness)
- `eval_retrieval.py`, `grading_run.py` — evaluation layer
- `data/grading_questions.json` — golden question set
- `.env` — config ChromaDB, embedding model, freshness SLA
- `docs/`, `contracts/`, `reports/` — tài liệu

**Kết nối với thành viên khác:** Trong lab cá nhân, tôi phụ trách toàn bộ end-to-end. Nếu làm nhóm thực tế, Cleaning owner cần sync với Embed owner về schema `chunk_id` (SHA256 stable ID), và Monitoring owner cần manifest JSON format từ pipeline.

**Bằng chứng:** Toàn bộ code được viết/chỉnh sửa trong session này, kiểm tra qua pipeline run log: `run_id=sprint-clean`, `cleaned_records=6`, `quarantine_records=7`, 8 expectations pass.

---

## 2. Một quyết định kỹ thuật

**Halt vs warn cho E7 (no_future_effective_date):**

Tôi chọn **halt** cho E7 vì future-dated chunks mô tả chính sách chưa được phê duyệt chính thức. Nếu để vào vector store, agent có thể trả lời người dùng theo policy "kế hoạch 2030" (ví dụ row 12: "SLA P1 phản hồi 10 phút"), gây nhầm lẫn nghiệp vụ.

E8 (chunk_count_per_doc_reasonable) tôi chọn **warn** vì: over-chunking là signal noise nhưng không nhất thiết làm retrieval sai hoàn toàn — vẫn cần giám sát chứ không nên block pipeline khi tài liệu hợp lệ nhưng dài.

Nguyên tắc: halt khi dữ liệu sai → agent có thể trả lời sai; warn khi dữ liệu có thể suboptimal nhưng không chắc gây harm.

---

## 3. Một lỗi hoặc anomaly đã xử lý

**Triệu chứng:** Trong lần chạy đầu tiên, pipeline crash tại bước embed với `ModuleNotFoundError: No module named 'sentence_transformers'`.

**Metric/check phát hiện:** Traceback rõ ràng tại `etl_pipeline.py` bước embed — ChromaDB's `SentenceTransformerEmbeddingFunction` cần package `sentence-transformers` cài riêng.

**Fix:** `pip install sentence-transformers`. Sau đó pipeline chạy thành công với `embed_upsert count=6`. Bổ sung vào README: `pip install chromadb sentence-transformers python-dotenv`.

Một anomaly khác: Rule 7 (BOM strip) phải được đặt **sau** Rule 4 (empty text check) nhưng **trước** Rule 9 (min length). Nếu strip BOM trước Rule 4 thì row rỗng chỉ có BOM (`"\ufeff"`) sẽ trở thành empty string → bị bắt đúng bởi Rule 4. Thứ tự rule quan trọng.

---

## 4. Bằng chứng trước / sau

**run_id inject-bad** (`artifacts/eval/after_inject_bad.csv`):
```
gq_d10_01,...,hits_forbidden=yes,contains_expected=yes,top1_doc_expected=yes
```

**run_id sprint-clean** (`artifacts/eval/after_clean.csv`):
```
gq_d10_01,...,hits_forbidden=no,contains_expected=yes,top1_doc_expected=yes
```

`hits_forbidden` chuyển từ `yes` → `no`: chunk "14 ngày làm việc" đã bị loại hoàn toàn khỏi collection sau clean run (`embed_prune_removed=1` trong log sprint-clean).

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: implement **alert webhook** khi `freshness_check=FAIL` hoặc expectation halt fail — gọi Slack incoming webhook với payload tóm tắt manifest (run_id, age_hours, failed_expectations). Hiện tại pipeline chỉ log ra stdout, cần push thành observable signal để on-call nhận ngay mà không cần xem log thủ công.
