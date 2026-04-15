"""
Expectation suite — kiểm tra cleaned rows trước khi embed.

Baseline (E1–E6) + 2 expectation mới (E7–E8):

  E7 — no_future_effective_date (halt):
    Không có record nào có effective_date > ngày hôm nay.
    Nếu Rule 8 cleaning chạy đúng thì E7 luôn pass; đây là lớp bảo vệ thứ 2
    phòng khi cleaning bị bypass (--skip-validate không áp dụng cho cleaning rules).
    metric_impact: khi inject row 12 (date=2030-06-01) với --skip-validate → E7 FAIL.

  E8 — chunk_count_per_doc_reasonable (warn):
    Mỗi doc_id trong cleaned phải có 1–10 chunks.
    Quá ít → tài liệu quan trọng bị under-represented.
    Quá nhiều → có thể inject loop hoặc chunking sai → retrieval noise.
    metric_impact: nếu inject 15 bản sao cùng doc_id (bypass dedup), E8 WARN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str   # "warn" | "halt"
    detail: str


def run_expectations(
    cleaned_rows: List[Dict[str, Any]],
) -> Tuple[List[ExpectationResult], bool]:
    """
    Chạy toàn bộ expectation suite.
    Trả về (results, should_halt).
    should_halt = True nếu có ít nhất 1 expectation halt bị fail.
    """
    results: List[ExpectationResult] = []

    # ------------------------------------------------------------------
    # E1: Ít nhất 1 dòng sau clean
    # ------------------------------------------------------------------
    ok = len(cleaned_rows) >= 1
    results.append(ExpectationResult(
        "min_one_row", ok, "halt",
        f"cleaned_rows={len(cleaned_rows)}",
    ))

    # ------------------------------------------------------------------
    # E2: Không doc_id rỗng
    # ------------------------------------------------------------------
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    results.append(ExpectationResult(
        "no_empty_doc_id", len(bad_doc) == 0, "halt",
        f"empty_doc_id_count={len(bad_doc)}",
    ))

    # ------------------------------------------------------------------
    # E3: Policy refund không chứa cửa sổ sai "14 ngày làm việc"
    # ------------------------------------------------------------------
    bad_refund = [
        r for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    results.append(ExpectationResult(
        "refund_no_stale_14d_window", len(bad_refund) == 0, "halt",
        f"violations={len(bad_refund)}",
    ))

    # ------------------------------------------------------------------
    # E4: chunk_text đủ dài tối thiểu 8 ký tự (warn — cảnh báo nhẹ)
    # ------------------------------------------------------------------
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    results.append(ExpectationResult(
        "chunk_min_length_8", len(short) == 0, "warn",
        f"short_chunks={len(short)}",
    ))

    # ------------------------------------------------------------------
    # E5: effective_date đúng định dạng ISO YYYY-MM-DD
    # ------------------------------------------------------------------
    iso_bad = [
        r for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$",
                        (r.get("effective_date") or "").strip())
    ]
    results.append(ExpectationResult(
        "effective_date_iso_yyyy_mm_dd", len(iso_bad) == 0, "halt",
        f"non_iso_rows={len(iso_bad)}",
    ))

    # ------------------------------------------------------------------
    # E6: Không còn marker "10 ngày phép năm" trên HR doc sau clean
    # ------------------------------------------------------------------
    bad_hr = [
        r for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    results.append(ExpectationResult(
        "hr_leave_no_stale_10d_annual", len(bad_hr) == 0, "halt",
        f"violations={len(bad_hr)}",
    ))

    # ------------------------------------------------------------------
    # E7 (Mới): Không có record với effective_date trong tương lai
    #
    # Tại sao halt: future-dated chunks chưa có hiệu lực, embed vào vector store
    # có thể làm agent trả lời theo chính sách chưa được phê duyệt.
    # Rule 8 trong cleaning đã lọc; E7 là lớp bảo vệ thứ 2 (defense-in-depth).
    # metric_impact: inject row 12 (2030-06-01) + --skip-validate → E7 FAIL.
    # ------------------------------------------------------------------
    today = date.today().isoformat()
    future_rows = [
        r for r in cleaned_rows
        if (r.get("effective_date") or "") > today
    ]
    results.append(ExpectationResult(
        "no_future_effective_date", len(future_rows) == 0, "halt",
        f"future_dated_rows={len(future_rows)} today={today}",
    ))

    # ------------------------------------------------------------------
    # E8 (Mới): Số chunk mỗi doc_id nằm trong khoảng hợp lý [1, 10]
    #
    # Tại sao warn (không halt): chạy CI nhẹ hơn, nhưng kéo warning vào log
    # để monitoring phát hiện injection loop hoặc over-chunking.
    # metric_impact: inject 12 bản sao cùng doc_id (bypass dedup) → E8 WARN.
    # ------------------------------------------------------------------
    from collections import Counter
    doc_counts = Counter(r.get("doc_id", "") for r in cleaned_rows)
    over_limit = {doc: cnt for doc, cnt in doc_counts.items() if cnt > 10}
    under_limit = {doc: cnt for doc, cnt in doc_counts.items() if cnt < 1}
    ok8 = len(over_limit) == 0 and len(under_limit) == 0
    detail8 = f"doc_counts={dict(doc_counts)}"
    if over_limit:
        detail8 += f" over_limit={over_limit}"
    results.append(ExpectationResult(
        "chunk_count_per_doc_reasonable", ok8, "warn", detail8,
    ))

    should_halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, should_halt