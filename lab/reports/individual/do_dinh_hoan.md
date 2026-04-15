# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Đỗ Đình Hoàn  
**Vai trò:** Cleaning & Quality Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** 530 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `transform/cleaning_rules.py` — Thiết kế, triển khai 9 cleaning rules (baseline 6 + mở rộng 3)
- `quality/expectations.py` — 8 data quality expectations (halt + warn)
- `artifacts/quarantine/` — Quản lý quarantine CSV, phân tích quarantine flow
- Phần QA trong test pipeline, verify metric_impact

**Kết nối với thành viên khác:**
- Nhận raw records từ Nguyễn Việt Hùng (Ingestion): 13 dòng CSV
- Cấp 6 cleaned records cho Trần Quốc Khánh (Embed)
- Report metric_impact (before/after) cho Nguyễn Công Thành (Grading) để kiểm chứng
- Sync với Nguyễn Xuân Tùng (Monitoring) về expectation halt/warn impact

**Bằng chứ cứ:**
- `quarantine_records=7` (3 rule mới: BOM, future_date, short_chunk)
- Log: 8 expectations all PASS
- Bảng metric_impact trong group_report.md

---

## 2. Một quyết định kỹ thuật

**Về quy tắc dedup:** Tôi chọn hash `chunk_text` bằng SHA256 (sau normalize: lowercase, strip whitespace) thay vì so string trực tiếp. Lý do: (1) nhanh hơn so sánh string dài, (2) detect duplicate từ nhiều nguồn (BOM, encoding khác, dòng phút cuối), (3) stable − chunk_id có thể tái tạo.

**Về thứ tự rule:** Đặt Rule 7 (BOM strip) **sau** Rule 4 (empty text) vì: nếu strip trước, chunk chỉ có BOM sẽ trở empty → Rule 4 bắt; nếu không thì BOM vẫn còn khi compare dedup. Thứ tự: load → 1-6 (allowlist, date norm, HR stale, empty, dedup) → 7 (strip) → 8-9 (future, short).

---

## 3. Một lỗi đã xử lý

**Triệu chứng:** Lần đầu chạy, `quarantine_records=6` thay vì expected `7`. Kiểm log: chỉ 2 row bị reject vì dedup, không phát hiện row 11 (BOM).

**Phát hiện:** Đặt breakpoint, print chunk_text trước/sau dedup → row 11 BOM tạo hash khác với row 2. Mở raw CSV file: row 11 byte đầu là `\xEF\xBB\xBF` (UTF-8 BOM).

**Fix:** Ingestion owner thêm `encoding='utf-8-sig'` khi load CSV. Sau đó row 11 BOM bị strip trước dedup → hash match row 2 → bị quarantine. Quay lại: `quarantine_records=7` ✓.

---

## 4. Bằng chứng trước / sau

**metric_impact — Rule 7 (BOM strip):**
- Trước: `quarantine_records=6, cleaned_records=7`
- Sau: `quarantine_records=7, cleaned_records=6`
- Bằng chứ: `artifacts/quarantine/quarantine_2026-04-15T09-21Z.csv` row 11: `reason=duplicate_chunk_text`

**metric_impact — Rule 8 (future_effective_date):**
- Trước inject: Nếu không có rule, row 12 (2030-06-01) vào collection
- Sau: `quarantine_2026-04-15T09-21Z.csv` row 12: `reason=future_effective_date`

**Expectation E3 (refund_no_stale_14d_window):**
- Scenario inject-bad: `violations=1` (inject row có "14 ngày" → FAIL halt)
- Scenario clean: `violations=0` (all "7 ngày") → PASS

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: Viết Monitoring Dashboard hiển thị quarantine reason distribution (dedup %, future %, short_chunk %). Thêm `--export-quarantine-report` option output JSON: `{"reason": "duplicate_chunk_text", "count": 2, "sample_rows": [11, ...]}`. Sẽ giúp product team hiểu data quality trend qua thời gian.
