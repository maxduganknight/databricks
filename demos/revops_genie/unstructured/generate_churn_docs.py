"""
RevOps — churn / QBR document generator.

Writes 16 HTML QBR/cancellation memos (4 Mid-Market accounts × 4 months,
Mar–Jun 2026), converts them to PDF, and uploads to the UC Volume
raw_churn_docs/pdf/. Each doc breaks the account's ARR change into three
reason lines: Renewed/Retained (flat), Competitive Displacement (escalating,
names the same AI-native rival), Missing-Feature Downgrade (escalating).

Downstream: unstructured/extract_churn_docs.sql runs ai_parse_document +
ai_extract → fact_churn_reason.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

CATALOG = os.environ.get("DEMO_CATALOG", "solution_builder")
SCHEMA = os.environ.get("DEMO_SCHEMA", "demo_revops_intelligence")
SKILL_PDF = ".claude/skills/databricks-unstructured-pdf-generation/scripts/pdf_generator.py"

COMPETITOR = "ProcureIQ"
FEATURE = "Real-Time Budget Approvals"

# 4 Mid-Market accounts (i%10 in 2..5 → Mid-Market in dim_account).
ACCOUNTS = ["ACCT0032", "ACCT0033", "ACCT0034", "ACCT0035"]
RENEWED = {"ACCT0032": 135_000, "ACCT0033": 126_000, "ACCT0034": 108_000, "ACCT0035": 80_000}

MONTHS = ["0326", "0426", "0526", "0626"]
MONTH_LABEL = {"0326": "March 2026", "0426": "April 2026", "0526": "May 2026", "0626": "June 2026"}
DOC_DATE = {"0326": "2026-03-15", "0426": "2026-04-15", "0526": "2026-05-15", "0626": "2026-06-15"}

# competitive_loss / feature_gap by (month → per-account list, order matches ACCOUNTS).
COMP = {"0326": [2550, 2380, 2040, 1530], "0426": [7800, 7280, 6240, 4680],
        "0526": [12000, 11200, 9600, 7200], "0626": [15900, 14840, 12720, 9540]}
FEAT = {"0326": [1350, 1260, 1080, 810], "0426": [4200, 3920, 3360, 2520],
        "0526": [6300, 5880, 5040, 3780], "0626": [8400, 7840, 6720, 5040]}

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body {{ font-family: Helvetica, Arial, sans-serif; margin: 48px; color: #1F2530; line-height: 1.5; }}
h1 {{ color: #094074; font-size: 22px; }} h2 {{ color: #3C6997; font-size: 15px; margin-top: 26px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 10px; }}
th, td {{ border: 1px solid #ccc; padding: 8px 10px; text-align: left; font-size: 13px; }}
th {{ background: #F0F4FA; }} .num {{ text-align: right; }} .meta {{ color: #667; font-size: 12px; }}
</style></head><body>
<h1>Quarterly Business Review &amp; Renewal Memo</h1>
<p class="meta"><b>Account:</b> {account_name} &nbsp;|&nbsp; <b>Account ID:</b> {account_id}
&nbsp;|&nbsp; <b>Segment:</b> Mid-Market &nbsp;|&nbsp; <b>Prepared:</b> {doc_date}</p>

<h2>1. Renewal outcome</h2>
<p>Of the account's book of ARR, <b>${renewed:,}</b> was <b>Renewed / Retained</b> at
this cycle. The remainder moved to contraction or loss for the reasons documented below.
This memo is prepared for the Office of Revenue Operations for the {month_label} cycle.</p>

<h2>2. Competitive displacement</h2>
<p>The customer cited <b>{competitor}</b>, an AI-native procurement platform, as the
primary reason for reducing spend — {competitor} undercut the company on price for the
comparable module set. ARR lost to competitive displacement this cycle:
<b>${comp:,}</b>. This competitor was <b>not present</b> in prior renewal cycles and
first appeared in the March 2026 reviews.</p>

<h2>3. Missing-feature downgrade</h2>
<p>The customer downgraded modules due to a missing capability: <b>{feature}</b>.
Buyers require real-time budget checks at the point of approval, which the current
package does not provide. ARR lost to this feature gap this cycle: <b>${feat:,}</b>.
The feature was requested and is absent from the current roadmap.</p>

<h2>4. ARR reason summary</h2>
<table>
<tr><th>Reason category</th><th>Competitor named</th><th class="num">ARR ($)</th></tr>
<tr><td>Renewed / Retained</td><td>&mdash;</td><td class="num">{renewed:,}</td></tr>
<tr><td>Competitive Displacement</td><td>{competitor}</td><td class="num">{comp:,}</td></tr>
<tr><td>Missing-Feature Downgrade</td><td>&mdash;</td><td class="num">{feat:,}</td></tr>
</table>
<p class="meta">Feature requested: {feature}. Competitor: {competitor}. Cycle: {month_label}.</p>
</body></html>"""


def main() -> None:
    html_dir = Path("unstructured/raw_data/html")
    pdf_dir = Path("unstructured/raw_data/pdf")
    html_dir.mkdir(parents=True, exist_ok=True)
    for mo in MONTHS:
        for ai, acct in enumerate(ACCOUNTS):
            html = HTML.format(
                account_name=f"Account {int(acct[4:]):03d} ({['NA','EMEA','APAC'][int(acct[4:]) % 3]})",
                account_id=acct, doc_date=DOC_DATE[mo], month_label=MONTH_LABEL[mo],
                renewed=RENEWED[acct], competitor=COMPETITOR, feature=FEATURE,
                comp=COMP[mo][ai], feat=FEAT[mo][ai],
            )
            (html_dir / f"qbr_{acct}_{mo}.html").write_text(html)
    print(f"Wrote {len(MONTHS) * len(ACCOUNTS)} HTML files → {html_dir}")

    subprocess.run(["python3", SKILL_PDF, "convert", "-i", str(html_dir), "-o", str(pdf_dir), "--force"], check=True)

    vol = f"dbfs:/Volumes/{CATALOG}/{SCHEMA}/raw_churn_docs/pdf"
    subprocess.run(["databricks", "fs", "cp", "-r", "--overwrite", str(pdf_dir), vol], check=True)
    print(f"Uploaded PDFs → {vol}")


if __name__ == "__main__":
    main()
