# Quality report — Lab Day 10 (nhóm 22)

**run_id:** sprint-clean  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Inject-bad run | Sprint-clean run | Ghi chú |
|--------|---------------|-----------------|---------|
| raw_records | 13 | 13 | Cùng raw CSV |
| cleaned_records | 6 | 6 | Inject-bad: refund chunk sai vẫn pass (--skip-validate) |
| quarantine_records | 7 | 7 | Xem breakdown bên dưới |
| Expectation halt fail? | YES (`refund_no_stale_14d_window`) | NO (tất cả PASS) | inject-bad dùng --skip-validate |
| embed_prune_removed | 0 | 1 | Clean run prune chunk inject-bad ra khỏi collection |

**Quarantine breakdown (sprint-clean):**

| reason | count |
|--------|-------|
| duplicate_chunk_text | 2 (row 2 = dup row 1; row 11 = BOM-stripped dup row 1) |
| stale_hr_policy_effective_date | 1 (row 7, HR 2025) |
| missing_chunk_text | 1 (row 5, refund empty text) |
| unknown_doc_id | 1 (row 9, legacy_catalog_xyz_zzz) |
| future_effective_date | 1 (row 12, 2030-06-01) |
| chunk_too_short | 1 (row 13, "Tạm thời." = 9 chars) |

---

## 2. Before / after retrieval

File: `artifacts/eval/after_inject_bad.csv` vs `artifacts/eval/after_clean.csv`

**gq_d10_01 — Refund window (câu hỏi then chốt):**

| Scenario | top1_doc_id | contains_expected | hits_forbidden | top1_doc_expected |
|----------|-------------|-------------------|----------------|-------------------|
| inject-bad | policy_refund_v4 | yes | **yes** | yes |
| after-clean | policy_refund_v4 | yes | **no** | yes |

`hits_forbidden=yes` sau inject: "14 ngày làm việc" xuất hiện trong top-k do chunk sai không bị fix.  
Sau clean: Rule 6 fix "14 ngày" → "7 ngày", E3 expectation pass, `hits_forbidden=no`.

**gq_d10_02, gq_d10_03:** cả hai scenario đều pass (`contains_expected=yes`, `hits_forbidden=no`).

---

## 3. Freshness & monitor

Kết quả `freshness_check=FAIL` cho cả hai run:
```json
{"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 115.6, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

SLA 24h được chọn vì knowledge base chứa policy nghiệp vụ — cần cập nhật trong ngày để agent không trả lời theo chính sách cũ. FAIL ở đây là **expected** trong môi trường lab (data tĩnh); production cần trigger export mỗi 12h.

---

## 4. Corruption inject (Sprint 3)

Ba loại corruption được inject vào `policy_export_dirty.csv`:

| Row | Loại corruption | Rule phát hiện | Kết quả |
|-----|----------------|----------------|---------|
| 11 | BOM prefix `\ufeff` | Rule 7 strip → Rule 5 dedup | quarantine: duplicate_chunk_text |
| 12 | Future date 2030-06-01 | Rule 8 + E7 | quarantine: future_effective_date; E7 FAIL nếu bypass cleaning |
| 13 | Chunk quá ngắn "Tạm thời." | Rule 9 | quarantine: chunk_too_short |

Ngoài ra, row 3 (14 ngày làm việc) vào inject-bad run: E3 FAIL (halt) phát hiện; `--skip-validate` cho phép tiếp tục nhưng vector store nhận chunk sai → `hits_forbidden=yes` trong eval.

---

## 5. Hạn chế & việc chưa làm

- Freshness FAIL luôn trong lab vì raw CSV không được export lại — không phải lỗi pipeline.
- Chưa implement alert tự động lên Slack khi freshness/expectation fail.
- E8 chưa kiểm tra `under_limit` (chunk < 1 thực tế không xảy ra với allowlist hiện tại).
- Chưa có test unit cho từng cleaning rule riêng lẻ.
