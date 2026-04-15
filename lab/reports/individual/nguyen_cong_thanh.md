# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Công Thành  
**Vai trò:** Grading & Orchestration Owner  
**Ngày nộp:** 2026-04-15  
**Độ dài:** 540 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
- `grading_run.py` — Chạy grading test (3 câu: gq_d10_01, 02, 03), output JSONL
- `eval_retrieval.py` — Before/after retrieval evaluation (4 test question)
- `instructor_quick_check.py` — Verify artifact integrity ( manifest, grading_run.jsonl)
- `data/grading_questions.json` — Golden question set, grading criteria
- End-to-end orchestration: run pipeline → eval → grade → report

**Kết nối với thành viên khác:**
- Nhận collection từ Trần Quốc Khánh (Embed)
- Đọc quarantine reason từ Đỗ Đình Hoàn (Cleaning) để liên hệ before/after
- Validate manifest từ Nguyễn Xuân Tùng (Monitoring)
- Tích hợp input từ Nguyễn Việt Hùng (Ingestion) về run_id tracing

**Bằng chứ cứ:**
- `grading_run.jsonl`: 3/3 câu PASS (gq_d10_01, 02, 03 all MERIT)
- `before_after_eval.csv`: 4 golden questions, all pass (contains_expected=yes, hits_forbidden=no)
- Log: `instructor_quick_check.py` verify success

---

## 2. Một quyết định kỹ thuật

**Grading rubric design:** Mỗi câu có 3 tiêu chí: (1) `contains_expected` (top-k chứa keyword expected), (2) `hits_forbidden` (top-k không chứa stale policy), (3) `top1_doc_matches` (rank #1 là doc_id mong đợi). Câu pass khi **tất cả 3 tiêu chí = true**.

Lý do tách 3 tiêu chí: (1) check relevance, (2) check hallucination/stale, (3) check ranking quality. Không ghép thành 1 score vì khi fail, muốn biết cụ thể fail ở đâu (relevance vs. ranking vs. stale).

---

## 3. Một lỗi đã xử lý

**Triệu chứng:** Chạy `grading_run.py`, 3 câu đều output `top1_doc_matches=true` nhưng top-1 chunk content lạ (khác kỳ vọng).

**Phát hiện:** In top-5 chunks, thấy rank #1 là chunk từ doc_id đúng nhưng text từ lần inject trước (chứa "14 ngày làm việc" stale). Log embedding show: `embed_prune_removed=1` nhưng collection vẫn chứa vector cũ.

**Fix:** Trần Quốc Khánh refactor prune logic (so sánh set IDs trước/sau). Sau đó rerun grading, top-5 chunks được clean, top-1 = "7 ngày làm việc" đúng. Update `grading_run.jsonl` với `contains_expected=true, hits_forbidden=false, top1_doc_matches=true` ✓.

---

## 4. Bằng chứ cứ trước / sau

**before_after_eval.csv (run_id=2026-04-15T09-21Z):**
```
q_refund_window, ..., contains_expected=yes, hits_forbidden=no, top1_doc_expected=yes
q_p1_sla, ..., contains_expected=yes, hits_forbidden=no, top1_doc_expected=yes
q_lockout, ..., contains_expected=yes, hits_forbidden=no, top1_doc_expected=yes
q_leave_version, ..., contains_expected=yes, hits_forbidden=no, top1_doc_expected=yes
```

**grading_run.jsonl:**
```
gq_d10_01: contains_expected=true, hits_forbidden=false, top1_doc_matches=true
gq_d10_02: contains_expected=true, hits_forbidden=false, top1_doc_matches=true
gq_d10_03: contains_expected=true, hits_forbidden=false, top1_doc_matches=true
```

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: Implement **negative test cases** − thêm câu hỏi kiến test retrieval với intent không support (VD câu về lương, benefit ngoài scope) → verify system tránh hallucinate. Thêm score metric: precision@k, recall@k (so sánh returned chunks vs. oracle chunks). Dùng để track model improvement qua cicles.
