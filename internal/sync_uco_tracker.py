#!/usr/bin/env python3
"""Sync Salesforce UCOs to the MDK UCO Tracker Google Sheet.

Pulls every UseCase__c attached to an account where I'm a (Primary) Solution
Architect via AccountTeamMember, and writes them as rows. MDK POV columns
that I've filled in are preserved across runs, matched by UCO Id (with a
fallback match on Account Name + UCO Name for legacy rows).

Usage:
    python3 scripts/sync_uco_tracker.py

Requires:
    - sf CLI authenticated (`sf org login web`)
    - Google auth set up (`/google-auth` or `python3 ... google_auth.py login`)
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

import requests

# === CONFIG ===
SHEET_ID = "1pRZr_CfayQj_RVuaEf9oRnGFZpDui95TpCif3j4FwD8"
SHEET_TAB = "Active UCOs"
USER_EMAIL = "max.duganknight@databricks.com"
SF_INSTANCE_URL = "https://databricks.my.salesforce.com"
QUOTA_PROJECT = "gcp-dev-field-eng-aiapiquota"
GOOGLE_AUTH_PY = (
    Path.home()
    / ".vibe/marketplace/plugins/fe-google-tools/skills/google-auth/resources/google_auth.py"
)

# Column order matches the existing sheet, plus a trailing UCO Id helper column.
HEADERS = [
    "Account Name",          # A — SF
    "AE",                    # B — SF (Account Owner first name)
    "UCO Name",              # C — SF
    "Stage",                 # D — SF
    "Products",              # E — SF
    "Target Live",           # F — SF
    "$DBU/Month",            # G — SF (MonthlyTotalDollarDBUs__c)
    "MDK POV",               # H — MDK (preserved)
    "MDK POV Notes",         # I — MDK (preserved)
    "MDK Recommended Stage", # J — MDK (preserved)
    "UCO Id",                # K — SF (stable match key)
]
NUM_COLS = len(HEADERS)
LAST_COL_LETTER = chr(ord("A") + NUM_COLS - 1)  # 'K'
# (col_idx, key) — `key` is the dict key in the preserved-MDK mapping below.
MDK_COLS = ((7, "pov"), (8, "pov_notes"), (9, "recommended_stage"))
UCO_ID_COL = 10


# === Salesforce ===

def ensure_sf_auth() -> None:
    """Check sf CLI session; if expired/missing, kick off the SSO web login."""
    check = subprocess.run(
        ["sf", "org", "display", "--target-org", USER_EMAIL, "--json"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        try:
            payload = json.loads(check.stdout)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("status") == 0:
            return  # session is valid

    print("Salesforce session is expired or missing — launching SSO login...")
    login = subprocess.run(
        ["sf", "org", "login", "web", "--instance-url", SF_INSTANCE_URL]
    )
    if login.returncode != 0:
        sys.exit("sf org login web failed. Re-run the script after authenticating.")


def sf_query(soql: str) -> list[dict]:
    """Run a SOQL query via the sf CLI and return the records."""
    result = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"sf query failed:\n{result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout)
    if payload.get("status") != 0:
        sys.exit(f"sf returned non-zero status: {payload}")
    return payload["result"]["records"]


def get_user_id() -> str:
    rows = sf_query(
        f"SELECT Id FROM User WHERE Username = '{USER_EMAIL}' AND IsActive = true"
    )
    if not rows:
        sys.exit(f"No active SF user found for {USER_EMAIL}")
    return rows[0]["Id"]


def get_sa_account_ids(user_id: str) -> list[str]:
    rows = sf_query(
        "SELECT AccountId FROM AccountTeamMember "
        f"WHERE UserId = '{user_id}' "
        "AND TeamMemberRole IN ('Primary Solution Architect', 'Solution Architect')"
    )
    return sorted({r["AccountId"] for r in rows})


# Only sync UCOs in the active U1–U5 lifecycle stages; exclude U6 (Live) and the
# closed Lost/Disqualified stages. Stages__c holds bare codes ('U1'..'U6', etc.).
ACTIVE_STAGES = ("U1", "U2", "U3", "U4", "U5")
STAGE_FILTER = "Stages__c IN ('" + "','".join(ACTIVE_STAGES) + "')"


def get_ucos(account_ids: list[str]) -> list[dict]:
    if not account_ids:
        return []
    ucos: list[dict] = []
    chunk = 200  # SOQL has a 100k char limit; chunk to stay well under it.
    for i in range(0, len(account_ids), chunk):
        ids = "','".join(account_ids[i : i + chunk])
        ucos.extend(sf_query(
            "SELECT Id, Name, Stages__c, Use_Case_Type__c, "
            "Full_Production_Date__c, MonthlyTotalDollarDBUs__c, "
            "Account__r.Name, Account__r.Owner.FirstName, Account__r.Owner.Name "
            f"FROM UseCase__c WHERE Account__c IN ('{ids}') "
            f"AND {STAGE_FILTER} "
            "ORDER BY Account__r.Name, Name"
        ))
    return ucos


# === Google Sheets ===

def sheets_token() -> str:
    result = subprocess.run(
        ["python3", str(GOOGLE_AUTH_PY), "token"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(
            "Could not get Google access token. Run /google-auth or "
            f"`python3 {GOOGLE_AUTH_PY} login` first.\n{result.stderr}"
        )
    return result.stdout.strip()


def sheets_call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": QUOTA_PROJECT,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    resp = requests.request(method, url, headers=headers, data=json.dumps(body) if body is not None else None)
    if resp.status_code >= 400:
        sys.exit(f"Sheets API {method} {path} failed: {resp.status_code} {resp.text}")
    return resp.json() if resp.text else {}


def encode_range(rng: str) -> str:
    return urllib.parse.quote(rng, safe="")


def read_existing(token: str) -> tuple[dict[str, dict[str, str]], dict[tuple[str, str], dict[str, str]]]:
    """Return ({uco_id: {mdk_key: val}}, {(account, uco_name): {mdk_key: val}})."""
    rng = encode_range(f"{SHEET_TAB}!A2:{LAST_COL_LETTER}")
    payload = sheets_call("GET", f"/values/{rng}", token)
    by_id: dict[str, dict[str, str]] = {}
    by_name: dict[tuple[str, str], dict[str, str]] = {}
    for row in payload.get("values", []):
        row = row + [""] * (NUM_COLS - len(row))
        mdk = {key: row[idx] for idx, key in MDK_COLS}
        if any(mdk.values()):  # only preserve rows with at least one MDK value
            uco_id = row[UCO_ID_COL].strip()
            if uco_id:
                by_id[uco_id] = mdk
            account, uco_name = row[0].strip(), row[2].strip()
            if account and uco_name:
                by_name[(account, uco_name)] = mdk
    return by_id, by_name


def build_rows(
    ucos: list[dict],
    by_id: dict[str, dict[str, str]],
    by_name: dict[tuple[str, str], dict[str, str]],
) -> list[list[str | float]]:
    rows: list[list[str | float]] = []
    empty_mdk = {key: "" for _, key in MDK_COLS}
    for u in ucos:
        account = (u.get("Account__r") or {})
        account_name = account.get("Name") or ""
        owner = (account.get("Owner") or {})
        ae = owner.get("FirstName") or owner.get("Name") or ""
        uco_name = u.get("Name") or ""
        mdk = by_id.get(u["Id"]) or by_name.get((account_name, uco_name)) or empty_mdk
        rows.append([
            account_name,
            ae,
            uco_name,
            u.get("Stages__c") or "",
            u.get("Use_Case_Type__c") or "",
            u.get("Full_Production_Date__c") or "",
            u.get("MonthlyTotalDollarDBUs__c") or "",
            mdk["pov"],
            mdk["pov_notes"],
            mdk["recommended_stage"],
            u["Id"],
        ])
    return rows


def write_sheet(rows: list[list[str]], token: str) -> None:
    # Header (idempotent)
    header_rng = encode_range(f"{SHEET_TAB}!A1:{LAST_COL_LETTER}1")
    sheets_call(
        "PUT",
        f"/values/{header_rng}?valueInputOption=USER_ENTERED",
        token,
        body={"values": [HEADERS]},
    )
    # Clear data rows
    clear_rng = encode_range(f"{SHEET_TAB}!A2:{LAST_COL_LETTER}")
    sheets_call("POST", f"/values/{clear_rng}:clear", token, body={})
    # Write fresh data
    if rows:
        write_rng = encode_range(f"{SHEET_TAB}!A2")
        sheets_call(
            "PUT",
            f"/values/{write_rng}?valueInputOption=USER_ENTERED",
            token,
            body={"values": rows},
        )


def main() -> None:
    ensure_sf_auth()

    print(f"Looking up SF user for {USER_EMAIL}...")
    user_id = get_user_id()
    print(f"  User Id: {user_id}")

    print("Finding accounts where I'm a Solution Architect...")
    account_ids = get_sa_account_ids(user_id)
    print(f"  Found {len(account_ids)} accounts")

    print("Querying UCOs...")
    ucos = get_ucos(account_ids)
    print(f"  Found {len(ucos)} UCOs")

    print("Reading existing sheet to preserve MDK POV columns...")
    token = sheets_token()
    by_id, by_name = read_existing(token)
    print(f"  Preserving MDK values for {len(by_id)} rows by Id, "
          f"{len(by_name)} by (account, uco_name)")

    rows = build_rows(ucos, by_id, by_name)

    print(f"Writing {len(rows)} rows...")
    write_sheet(rows, token)
    print(f"Done: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


if __name__ == "__main__":
    main()
