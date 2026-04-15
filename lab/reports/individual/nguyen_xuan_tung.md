# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Xuân Tùng  
**Vai trò:** Monitoring / Freshness Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** 520 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `monitoring/freshness_check.py` — Logic kiểm tra freshness SLA, tính age_hours
- `contracts/data_contract.yaml` — Định nghĩa SLA (24 giờ), ownership, alert contact
- `docs/runbook.md` — Post-incident playbook khi freshness fail
- Phần monitoring logic trong `etl_pipeline.py` (freshness check step)
- `artifacts/manifests/` — Đọc manifest để tính freshness metric

**Kết nối với thành viên khác:**
- Đọc manifest output từ Trần Quốc Khánh (Embed): timestamp `latest_exported_at`
- Nhận metric_impact từ Đỗ Đình Hoàn (Cleaning) để trigger alert
- Ghi SLA definition từ data_contract.yaml
- Tương tác Nguyễn Công Thành (Grading) nếu pipeline fail do freshness

**Bằng chứ cứ:**
- `freshness_check=FAIL` trong log
- `age_hours=115.6, sla_hours=24.0, reason=freshness_sla_exceeded` trong manifest
- `monitoring/freshness_check.py` output

---

## 2. Một quyết định kỹ thuật

**SLA 24 giờ là hợp lý vì:** Dataset là policy knowledge base cho agent CSKH — policy thay đổi trong ngày (flash sale, rule mới, bugfix regulation compliance) cần được cập nhật nhanh. Nếu SLA > 24h, agent trả lời theo policy cũ trong 2+ ngày → customer complaint.

**Về calc freshness:** Dùng `latest_exported_at` (timestamp tối tưới của bất kỳ chunk nào trong dataset), không phải run timestamp. Vì: pipeline có thể fail → run thất bại nhưng dataset cũ vẫn được serve. Monitoring phải detect "dữ liệu trong production quá cũ", không phải "lần chạy gần nhất bao lâu".

---

## 3. Một lỗi đã xử lý

**Triệu chứng:** Lần đầu chạy freshness_check, script fail: `KeyError: 'exported_at'` — không tìm được key trong CSV.

**Phát hiện:** Inspect manifest → chunk metadata có `exported_at` nhưng Python code dùng wrong key name (`export_at` thay vì `exported_at`). Kiểm schema: Đỗ Đình Hoàn định nghĩa column `exported_at` trong quarantine/cleaned CSV, nhưng freshness script dùng typo.

**Fix:** Sửa key từ `export_at` → `exported_at`. Sau đó: `age_hours=115.6` được tính đúng, so sánh `115.6 > 24.0` → FAIL status. Bổ sung unit test để check key presence trong CSV header.

---

## 4. Bằng chứng trước / sau

**Script output (run_id=2026-04-15T09-21Z):**
```
manifest_path: artifacts/manifests/manifest_2026-04-15T09-21Z.json
latest_exported_at: 2026-04-10T08:00:00
today: 2026-04-15
age_hours: 115.6
sla_hours: 24.0
status: FAIL
reason: freshness_sla_exceeded
```

**Vs. healthy state (hypothetical):**
```
latest_exported_at: 2026-04-15T07:30:00 (hôm nay)
age_hours: 1.5
status: PASS
```

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: Integrate Slack/PagerDuty webhook − khi freshness FAIL hoặc expectation halt fail, trigger alert tới on-call team. Webhook payload: `{"run_id", "status", "failed_checks": [...], "age_hours", "recommendation"}`. Tránh ngồi chờ log manual, mà proactive notify team. Cần configure `ALERT_WEBHOOK_URL` trong `.env`.
