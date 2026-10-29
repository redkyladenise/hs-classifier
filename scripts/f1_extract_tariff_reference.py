"""
Extract 8-digit tariff lines from official Tariff Commission AHTN 2022 PDFs
for Chapters 39, 73, 84, 85, and 87 using word-level column coordinates,
watermark size filtering, and bold-heading detection.

Outputs:
  - data/reference/ahtn_2022_scope_reference.parquet
  - data/reference/ahtn_2022_scope_reference.csv
  - reports/tables/f_sample_audit.csv
"""

from datetime import date
from pathlib import Path
import re
import pandas as pd
import pdfplumber

CHAPTER_CONFIG = {
    "39": {"file": "39.pdf", "start_page": 4, "end_page": 16},
    "73": {"file": "73.pdf", "start_page": 2, "end_page": 12},
    "84": {"file": "84.pdf", "start_page": 5, "end_page": 51},
    "85": {"file": "85.pdf", "start_page": 5, "end_page": 37},
    "87": {"file": "87.pdf", "start_page": 2, "end_page": 40},
}

RAW_DIR = Path("data/raw/tariff_book_2022")
OUT_DIR = Path("data/reference")
REPORT_DIR = Path("reports/tables")

OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Vertical bounds: skip top table headers (<118) and bottom page numbers (>765)
TOP_MIN = 108.0
BOTTOM_MAX = 765.0

# Horizontal column boundaries (in points)
X_HDG_MIN = 20.0
X_CODE_MIN = 52.0     # AHTN Code column starts around x0=54..66
X_DESC_MIN = 115.0    # Description column starts around x0=120..145
X_DESC_MAX = 360.0    # Duty rate columns start at x0>=368

CODE8_EXACT_RE = re.compile(r"^(\d{4}\.\d{2}\.\d{2})$")
SUB6_EXACT_RE = re.compile(r"^(\d{4}\.\d{2})$")
HDG4_EXACT_RE = re.compile(r"^(\d{2}\.\d{2})$")
HIERARCHY_DASH_RE = re.compile(r"^-\s*")

# Cleans up floating footnote blocks and inline duty review clauses
FOOTNOTE_CLEAN_RE = re.compile(
    r"(?:\s*(?:a\d+|\*)\s+(?:The MFN rate|Starting \d+|Subject to|Applicable to).*$|\s*:?\s*rate of duty shall be subject to periodic review.*$)",
    re.IGNORECASE,
)
FOOTNOTE_LINE_START_RE = re.compile(
    r"^(?:(?:a\d+|\*)\s+(?:The MFN rate|Starting \d+|Subject to|Applicable to)|rate of duty shall be subject to periodic review)",
    re.IGNORECASE,
)


def group_words_into_rows(words: list[dict], y_tolerance: float = 3.5) -> list[list[dict]]:
    """Group extracted words into horizontal rows based on their vertical 'top' coordinate."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows = []
    current_row = [sorted_words[0]]
    current_top = sorted_words[0]["top"]

    for w in sorted_words[1:]:
        if abs(w["top"] - current_top) <= y_tolerance:
            current_row.append(w)
        else:
            current_row.sort(key=lambda item: item["x0"])
            rows.append(current_row)
            current_row = [w]
            current_top = w["top"]

    if current_row:
        current_row.sort(key=lambda item: item["x0"])
        rows.append(current_row)

    return rows


def finalize_record(rec: dict, records: list[dict]):
    """Clean and append a completed 8-digit code record."""
    if not rec:
        return
    clean_desc = FOOTNOTE_CLEAN_RE.sub("", rec["description"]).strip()
    clean_desc = re.sub(r"\s+", " ", clean_desc)
    rec["description"] = clean_desc
    records.append(rec)


def extract_chapter(chapter: str, cfg: dict) -> list[dict]:
    pdf_path = RAW_DIR / cfg["file"]
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing PDF: {pdf_path}")

    records = []
    current_code = None
    retrieval_date = date.today().isoformat()

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx in range(cfg["start_page"] - 1, cfg["end_page"]):
            page = pdf.pages[page_idx]
            raw_words = page.extract_words(extra_attrs=["fontname", "size"])

            # Filter words to table body area, excluding watermarks (size > 13.5) and duty columns (x0 >= 360)
            valid_words = [
                w for w in raw_words
                if TOP_MIN <= w["top"] <= BOTTOM_MAX
                and X_HDG_MIN <= w["x0"] < X_DESC_MAX
                and 5.5 <= w.get("size", 10.0) <= 13.5
            ]

            rows = group_words_into_rows(valid_words)

            for row in rows:
                hdg_words = [w for w in row if X_HDG_MIN <= w["x0"] < X_CODE_MIN]
                code_words = [w for w in row if X_CODE_MIN <= w["x0"] < X_DESC_MIN]
                desc_words = [w for w in row if X_DESC_MIN <= w["x0"] < X_DESC_MAX]

                hdg_text = "".join(w["text"] for w in hdg_words).strip()
                code_text = "".join(w["text"] for w in code_words).strip()
                desc_text = " ".join(w["text"] for w in desc_words).strip()

                is_desc_bold = any(
                    "bold" in w.get("fontname", "").lower() for w in desc_words
                )

                if "(1)" in hdg_text or "(1)" in code_text or "(1)" in desc_text:
                    continue

                if FOOTNOTE_LINE_START_RE.match(desc_text) or FOOTNOTE_LINE_START_RE.match(code_text):
                    finalize_record(current_code, records)
                    current_code = None
                    continue

                # Case 1: Genuine 4-digit Heading in Column 1 (ONLY if there is no 8-digit code on this row)
                if HDG4_EXACT_RE.match(hdg_text) and not CODE8_EXACT_RE.match(code_text):
                    finalize_record(current_code, records)
                    current_code = None
                    continue


                # Case 2: New 6-digit Subheading in Column 2
                if SUB6_EXACT_RE.match(code_text):
                    finalize_record(current_code, records)
                    current_code = None
                    continue

                # Case 3: New 8-digit Tariff Code in Column 2
                m_code8 = CODE8_EXACT_RE.match(code_text)
                if m_code8:
                    finalize_record(current_code, records)
                    raw_code = m_code8.group(1)
                    current_code = {
                        "code8": raw_code.replace(".", ""),
                        "code_formatted": raw_code,
                        "chapter": chapter,
                        "description": desc_text,
                        "source_file": cfg["file"],
                        "retrieval_date": retrieval_date,
                    }
                    continue

                # Case 4: Standalone bold heading paragraph (ONLY if no code is currently active)
                if is_desc_bold and not HIERARCHY_DASH_RE.match(desc_text) and not current_code:
                    finalize_record(current_code, records)
                    current_code = None
                    continue

                # Case 5: Continuation line or uncoded subheading
                if current_code and desc_text:
                    if (
                        HIERARCHY_DASH_RE.match(desc_text)
                        or desc_text.endswith(":")
                        or desc_text.startswith("SUB-CHAPTER")
                        or desc_text.startswith("SECTION")
                    ):
                        finalize_record(current_code, records)
                        current_code = None
                    else:
                        current_code["description"] += " " + desc_text

        finalize_record(current_code, records)

    return records


def main():
    all_records = []
    print("Extracting AHTN 2022 codes using coordinate & font-aware word grouping...")

    for chapter, cfg in sorted(CHAPTER_CONFIG.items()):
        recs = extract_chapter(chapter, cfg)
        print(f"Chapter {chapter}: {len(recs)} codes extracted from {cfg['file']}")
        all_records.extend(recs)

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["code8"], keep="first").reset_index(drop=True)
    print(f"\nTotal distinct 8-digit codes extracted: {len(df)}")

    parquet_out = OUT_DIR / "ahtn_2022_scope_reference.parquet"
    csv_out = OUT_DIR / "ahtn_2022_scope_reference.csv"
    df.to_parquet(parquet_out, index=False)
    df.to_csv(csv_out, index=False, encoding="utf-8")
    print(f"Saved: {parquet_out}")
    print(f"Saved: {csv_out}")

    audit_samples = []
    for ch, grp in df.groupby("chapter"):
        n_sample = min(50, len(grp))
        sample = grp.sample(n=n_sample, random_state=42)
        audit_samples.append(sample)

    audit_df = pd.concat(audit_samples, ignore_index=True)
    audit_out = REPORT_DIR / "f_sample_audit.csv"
    audit_df.to_csv(audit_out, index=False, encoding="utf-8")
    print(f"Generated audit sample (250 codes): {audit_out}")


if __name__ == "__main__":
    main()