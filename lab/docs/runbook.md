# Runbook — Lab Day 10

---

## Symptom

Agent/user nhận câu trả lời sai — ví dụ: "hoàn tiền trong 14 ngày làm việc" thay vì 7 ngày, hoặc "10 ngày phép năm" thay vì 12 ngày.

---

## Detection

| Metric | Nguồn | Ngưỡng báo động |
|--------|-------|-----------------|
| `hits_forbidden=yes` | `artifacts/eval/*.csv` | Bất kỳ dòng nào |
| `expectation[refund_no_stale_14d_window] FAIL` | Pipeline log | Ngay lập tức halt |
| `freshness_check=FAIL` | Manifest JSON | `age_hours > sla_hours` |
| `embed_prune_removed > 0` sau inject | Pipeline log | Cần kiểm tra nội dung prune |

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/manifest_{run_id}.json` | Xem `cleaned_records`, `quarantine_records`, `skipped_validate` |
| 2 | Mở `artifacts/quarantine/quarantine_{run_id}.csv` | Tìm reason=`duplicate_chunk_text`, `future_effective_date`, `chunk_too_short` |
| 3 | Chạy `python eval_retrieval.py --questions data/grading_questions.json --out artifacts/eval/debug.csv` | Xem `hits_forbidden`, `contains_expected`, `top1_doc_expected` |
| 4 | Kiểm tra log `artifacts/logs/` | Tìm `FAIL (halt)` hoặc `WARN` |

---

## Mitigation

1. **Stale refund window:** Rerun pipeline bình thường (không `--no-refund-fix`, không `--skip-validate`):
   ```bash
   python etl_pipeline.py run --run-id sprint-clean
   ```
2. **Future-dated chunk bypass expectations:** KHÔNG thể bypass — E7 là halt. Fix ngày trong raw CSV rồi rerun.
3. **Data freshness FAIL:** Trigger export mới từ source system, cập nhật `exported_at`, rerun pipeline.
4. **Rollback tạm thời:** Khôi phục manifest + re-embed từ `cleaned_sprint-clean.csv` trước khi inject.

---

## Prevention

- Thêm schedule trigger pipeline mỗi 12h để duy trì freshness SLA.
- Bổ sung expectation E9: kiểm tra `exported_at` không quá cũ (>48h).
- Alert tự động: nếu `freshness_check=FAIL` → post Slack `#data-quality-alerts`.
- Review quarantine CSV trong CI để phát hiện sớm anomaly từ source system.
