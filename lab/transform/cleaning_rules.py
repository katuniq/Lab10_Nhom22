"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline + 3 rule mới (Rule 7–9):

  Rule 7 — strip_bom_and_control_chars (transformation):
    Xóa BOM (\\ufeff) và control chars ẩn khỏi chunk_text trước khi xử lý.
    metric_impact: row 11 (BOM prefix) → sau strip text khớp row 1
    → bị bắt là duplicate → quarantine_records +1 khi inject.

  Rule 8 — future_effective_date (quarantine):
    Quarantine record có effective_date > ngày hôm nay (lỗi nhập liệu / dữ liệu giả).
    metric_impact: row 12 (date=2030-06-01) → quarantine_records +1; khi fix → giữ lại.

  Rule 9 — chunk_too_short (quarantine):
    Quarantine chunk_text < 20 ký tự sau khi strip (fragment, header rỗng, placeholder).
    metric_impact: row 13 ("Tạm thời.") → quarantine_records +1; khi fix → giữ lại.
"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Doc IDs hợp lệ — phải đồng bộ với contracts/data_contract.yaml.
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

# Ngưỡng độ dài tối thiểu của chunk (Rule 9).
CHUNK_MIN_LENGTH = 20

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_text(s: str) -> str:
    """Chuẩn hoá text để so sánh dedup: lowercase + collapse whitespace."""
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    """SHA256 hash ngắn để tạo chunk_id ổn định (idempotent upsert)."""
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


# ---------------------------------------------------------------------------
# Rule 7 — strip BOM + control chars (transformation, không quarantine)
# ---------------------------------------------------------------------------

def _strip_bom_and_control_chars(text: str) -> str:
    """
    Rule 7: Xóa UTF-8 BOM (\\ufeff) và ASCII control chars ẩn (0x00–0x1F trừ tab/newline).

    Lý do: BOM xuất hiện khi hệ nguồn export UTF-8-BOM thay vì UTF-8.
    Nếu không strip, cùng nội dung nhưng khác BOM → SHA256 khác → dedup bỏ sót,
    vector store nhận 2 embedding giống nhau (retrieval noise).

    metric_impact (row 11): BOM strip → text khớp row 1 → duplicate_chunk_text +1.
    """
    # Xóa BOM
    text = text.replace("\ufeff", "")
    # Xóa control chars ẩn (giữ lại \t=0x09 và \n=0x0A)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Chuẩn hoá khoảng trắng thừa (nhiều space → 1 space, strip đầu/cuối)
    text = re.sub(r" {2,}", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:  # utf-8-sig tự strip BOM file-level
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


# ---------------------------------------------------------------------------
# Main cleaning function
# ---------------------------------------------------------------------------

def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).

    Rules (baseline + mở rộng):
    1) Quarantine: doc_id không thuộc allowlist.
    2) Chuẩn hoá effective_date sang YYYY-MM-DD; quarantine nếu không parse được.
    3) Quarantine: hr_leave_policy có effective_date < 2026-01-01 (bản HR cũ).
    4) Quarantine: chunk_text rỗng.
    5) Dedup: loại trùng nội dung chunk_text (giữ bản đầu).
    6) Fix stale refund: '14 ngày làm việc' → '7 ngày làm việc'.
    --- Mới ---
    7) Strip BOM + control chars khỏi chunk_text (trước dedup).      [Rule 7]
    8) Quarantine: effective_date > ngày hôm nay (future date).      [Rule 8]
    9) Quarantine: chunk_text quá ngắn (< CHUNK_MIN_LENGTH ký tự).   [Rule 9]
    """
    today = date.today().isoformat()  # YYYY-MM-DD
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # --- Rule 1: doc_id allowlist ---
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # --- Rule 2: chuẩn hoá ngày ---
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": "invalid_effective_date_format",
                                "effective_date_raw": eff_raw})
            continue

        # --- Rule 8 (Mới): future effective_date ---
        # Dữ liệu có ngày hiệu lực trong tương lai = lỗi nhập liệu hoặc staging data.
        if eff_norm > today:
            quarantine.append({**raw, "reason": "future_effective_date",
                                "effective_date_normalized": eff_norm,
                                "today": today})
            continue

        # --- Rule 3: HR stale version ---
        if doc_id == "hr_leave_policy" and eff_norm < "2026-01-01":
            quarantine.append({**raw, "reason": "stale_hr_policy_effective_date",
                                "effective_date_normalized": eff_norm})
            continue

        # --- Rule 4: chunk_text rỗng ---
        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # --- Rule 7 (Mới): strip BOM + control chars ---
        text = _strip_bom_and_control_chars(text)

        # --- Rule 9 (Mới): chunk_text quá ngắn ---
        if len(text) < CHUNK_MIN_LENGTH:
            quarantine.append({**raw, "chunk_text_stripped": text,
                                "reason": "chunk_too_short",
                                "length": len(text),
                                "min_required": CHUNK_MIN_LENGTH})
            continue

        # --- Rule 5: dedup ---
        key = _norm_text(text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # --- Rule 6: fix stale refund window ---
        fixed_text = text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace("14 ngày làm việc", "7 ngày làm việc")
                fixed_text += " [cleaned: stale_refund_window]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n",
                        encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(
            "chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n",
            encoding="utf-8",
        )
        return
    # Thu thập tất cả keys từ tất cả rows (có thể khác nhau)
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)