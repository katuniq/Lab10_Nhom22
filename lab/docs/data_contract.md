# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `data/docs/policy_refund_v4.txt` (`policy_refund_v4`) | Batch Ingest (đọc file) | Nội dung cũ (chứa hoàn tiền 14 ngày thay vì 7 ngày) gây `halt` | SLA Publish > 24h, Alert qua `#data-quality-alerts` |
| `data/docs/sla_p1_2026.txt` (`sla_p1_2026`) | Batch Ingest (đọc file) | Trùng lặp dữ liệu (`warn`), parse lỗi | SLA Publish > 24h, Alert qua `#data-quality-alerts` |
| `data/docs/it_helpdesk_faq.txt` (`it_helpdesk_faq`) | Batch Ingest (đọc file) | Trùng lặp dữ liệu (`warn`), parse lỗi | SLA Publish > 24h, Alert qua `#data-quality-alerts` |
| `data/docs/hr_leave_policy.txt` (`hr_leave_policy`) | Batch Ingest (đọc file) | Vi phạm thiết lập phiên bản (`min_effective_date < 2026-01-01`) | SLA Publish > 24h, Alert qua `#data-quality-alerts` |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | ID ổn định sau clean (thường hash hoặc doc_id + seq) |
| doc_id | string | Có | Khóa logic tài liệu nguồn (vd `policy_refund_v4`). Phải nằm trong `allowed_doc_ids` |
| chunk_text | string | Có | Dữ liệu văn bản. Bị giới hạn ràng buộc `min_length = 8` |
| effective_date | date | Có | Ngày hiệu lực của dữ liệu (VD: cần thoả yêu cầu `policy_versioning`) |
| exported_at | datetime | Có | Giờ ghi nhận export xuất để tính SLA (`freshness` theo `publish`) |

---

## 3. Quy tắc quarantine vs drop

> Record bị flag đi đâu? Ai approve merge lại?

- **Quy tắc xử lý:**
  - Lỗi vi phạm `severity: halt` (vd: `no_stale_refund_window` chứa chính sách 14 ngày): Data batch bị **drop** (từ chối xử lý đưa vào target) hoặc hệ thống sẽ **quarantine** (cách ly records hỏng vào thư mục/bảng Dead Letter Queue) để tránh đầu độc Knowledge Base.
  - Lỗi vi phạm `severity: warn` (vd: `no_duplicate_chunk_text`): Records được cảnh báo (log warning) nhưng vẫn được đưa qua pipeline theo mặc định.
- **SLA & Cảnh báo:** Đo độ tươi (freshness) tại bước `publish`. Nếu lệch chuẩn `sla_hours: 24`, sẽ bắn cảnh báo.
- **Approve merge lại:** Metadata config định nghĩa `owner_team: "platform-data"`. Đội `platform-data` sẽ nhận alert qua kênh `#data-quality-alerts`, tiến hành phân tách xác thực và approve việc ingest lại (merge).

---

## 4. Phiên bản & canonical

> Source of truth cho policy refund: file nào / version nào?

- Dataset quản lý: `kb_chunk_export` - version: `1.0`
- **Source of truth (Canonical Source) cho policy refund:**
  - Đường dẫn file: `data/docs/policy_refund_v4.txt`
  - Canonical identifier (doc_id): `policy_refund_v4`
  - Version: Chính sách `v4` (thể hiện thời hạn trả hàng là 7 ngày).
- **Lưu ý policy versioning khác:** Đối với `hr_leave_policy`, version tham chiếu có `hr_leave_min_effective_date` là `2026-01-01`.
