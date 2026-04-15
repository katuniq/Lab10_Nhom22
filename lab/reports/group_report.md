# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Group 1  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Nguyễn Việt Hùng | Ingestion / Raw Owner | nguyenviethungsoicthust@gmail.com |
| Đỗ Đình Hoàn | Cleaning & Quality Owner | dodinhhoan@example.com |
| Trần Quốc Khánh | Embed & Idempotency Owner | trankhanh@example.com |
| Nguyễn Xuân Tùng | Monitoring / Freshness Owner | nguyentung@example.com |
| Nguyễn Công Thành | Grading & Orchestration Owner | nguyenthanh@example.com |

**Ngày nộp:** 2026-04-15  
**Repo:** c:\Users\ADMIN\Downloads\day10  
**Độ dài báo cáo nhóm:** ~1,200 từ (5 phần)
**Fiilestructure:** group_report.md + 5 individual reports (450–650 từ mỗi người)

---

## 1. Pipeline tổng quan

Nguồn raw là file CSV tĩnh `data/raw/policy_export_dirty.csv` (13 records) mô phỏng export từ hệ thống CRM/Policy, chứa các lỗi thực tế: BOM encoding, ngày sai format, dữ liệu cũ, chunk quá ngắn, và future-dated staging data.

Chuỗi lệnh end-to-end:

```bash
# Cài đặt
pip install chromadb sentence-transformers python-dotenv

# Pipeline chuẩn
python etl_pipeline.py run --run-id sprint-clean

# Pipeline inject lỗi (demo before/after)
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate

# Eval retrieval
python eval_retrieval.py --questions data/grading_questions.json --out artifacts/eval/after_clean.csv

# Freshness check
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint-clean.json

# Grading
python grading_run.py --out artifacts/eval/grading_run.jsonl
```

**run_id** được truyền qua CLI flag (`--run-id`), ghi vào `artifacts/manifests/manifest_{run_id}.json` cùng toàn bộ metrics: `raw_records`, `cleaned_records`, `quarantine_records`, `embed_upsert_count`, `freshness_check`.

---

## 2. Cleaning & expectation

Baseline đã có 6 rule (allowlist, date normalization, HR stale, empty text, dedup, refund fix). Nhóm bổ sung **3 rule mới** và **2 expectation mới**:

### 2a. Bảng metric_impact

| Rule / Expectation mới | Trước (không có rule) | Sau / khi inject | Chứng cứ |
|------------------------|----------------------|-----------------|----------|
| **Rule 7** — strip_bom_and_control_chars | Row 11 BOM tạo embedding trùng nhưng chunk_id khác → vector noise | Sau strip → dedup bắt, `quarantine_records +1` | `quarantine_sprint-clean.csv` row 11: reason=`duplicate_chunk_text` |
| **Rule 8** — future_effective_date | Row 12 (2030-06-01) embed vào collection → agent trả lời theo policy chưa phê duyệt | `quarantine_records +1`, row 12 không vào collection | `quarantine_sprint-clean.csv` row 12: reason=`future_effective_date` |
| **Rule 9** — chunk_too_short | Row 13 "Tạm thời." (9 chars) embed gây retrieval noise | `quarantine_records +1` | `quarantine_sprint-clean.csv` row 13: reason=`chunk_too_short`, length=9 |
| **E7** — no_future_effective_date (halt) | Future chunk bypass cleaning sẽ vào collection | E7 FAIL nếu dùng `--skip-validate` và cleaning bị tắt | Log inject-bad: `expectation[no_future_effective_date]` FAIL khi inject row 12 trực tiếp |
| **E8** — chunk_count_per_doc_reasonable (warn) | 15 bản sao cùng doc_id bypass dedup → retrieval noise | WARN nếu bất kỳ doc có >10 chunk | `doc_counts={'policy_refund_v4': 2, 'sla_p1_2026': 1, ...}` — tất cả trong ngưỡng |

**Rule chính (baseline + mở rộng):**
- Rule 1: allowlist doc_id (halt nếu unknown)
- Rule 2: chuẩn hoá effective_date sang ISO, quarantine nếu sai format
- Rule 3: HR stale version (effective_date < 2026-01-01) → quarantine
- Rule 4: chunk_text rỗng → quarantine
- Rule 5: dedup theo content hash → quarantine
- Rule 6: fix "14 ngày làm việc" → "7 ngày làm việc" cho policy_refund_v4
- **Rule 7**: strip BOM + control chars (transformation, trước dedup)
- **Rule 8**: future effective_date > today → quarantine
- **Rule 9**: chunk_text < 20 chars sau strip → quarantine

**Ví dụ expectation fail:** Chạy inject-bad, E3 (`refund_no_stale_14d_window`) FAIL halt với `violations=1`. Pipeline không dừng vì `--skip-validate`, nhưng log rõ ràng: `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`.

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject:** Chạy `--no-refund-fix --skip-validate` → chunk "14 ngày làm việc" không bị fix, vượt qua expectation halt → vào vector store.

**Kết quả định lượng** (`artifacts/eval/after_inject_bad.csv` vs `artifacts/eval/after_clean.csv`):

| Question | Scenario | hits_forbidden | contains_expected | top1_doc_expected |
|----------|----------|----------------|-------------------|-------------------|
| gq_d10_01 (refund window) | inject-bad | **yes** | yes | yes |
| gq_d10_01 (refund window) | after-clean | **no** | yes | yes |
| gq_d10_02 (SLA P1) | cả hai | no | yes | yes |
| gq_d10_03 (HR leave) | cả hai | no | yes | yes |

`hits_forbidden` chuyển từ `yes` → `no` sau clean run chứng minh pipeline loại bỏ hoàn toàn stale chunk ra khỏi retrieval. `embed_prune_removed=1` trong log sprint-clean xác nhận chunk inject-bad đã bị prune.

---

## 4. Freshness & monitoring

SLA 24h vì policy knowledge base phục vụ agent CSKH theo thời gian thực — policy thay đổi trong ngày (flash sale, incident) phải được reflect trong vòng 24h.

Kết quả:
```
freshness_check=FAIL — age_hours=115.6, sla_hours=24.0, reason=freshness_sla_exceeded
```

FAIL là **expected** trong lab (raw CSV tĩnh, `exported_at=2026-04-10`). Manifest ghi nhận rõ ràng giúp monitoring phát hiện nếu production pipeline bị treo mà không trigger export.

---

## 5. Liên hệ Day 09

Pipeline Day 10 dùng collection riêng `day10_kb` với embedding model `all-MiniLM-L6-v2` (offline, không cần API key), tách biệt hoàn toàn với `day09_docs` dùng OpenAI `text-embedding-3-small`.

Lý do tách: (1) khác embedding model → không thể query chéo collection, (2) Day 10 tập trung vào data quality thay vì multi-agent routing. Nếu muốn unified corpus, cần export `cleaned_sprint-clean.csv` và re-index qua `day09/lab/index.py`.

---

## 6. Rủi ro còn lại & việc chưa làm

- Alert tự động Slack khi freshness/expectation fail chưa implement.
- Chưa có unit test cho từng cleaning rule — E2E test qua pipeline run.
- `CHUNK_MIN_LENGTH=20` hardcoded — nên đưa vào `.env` để dễ điều chỉnh theo loại tài liệu.
- Grading: 3/3 câu hỏi đều pass (`contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true`).
