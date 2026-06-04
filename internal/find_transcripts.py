#!/usr/bin/env python3
"""Find Gemini meeting transcripts for a customer in a date window.

Strategy: calendar-first. We query Max's Google Calendar for events matching
the customer name, then look for Drive docs whose filename timestamp matches
each event's start time. Cheap and reliable — no need to scan the whole folder
or open docs to identify them.

Usage:
    python3 scripts/find_transcripts.py --customer Procurify --since 2026-04-22
    python3 scripts/find_transcripts.py --customer Cancap --since 2026-04-01 --until 2026-05-01

Output: list of (calendar event, transcript doc) pairs. If no calendar events
match, exits with "nothing to match". If events exist but no transcripts match,
exits with "no transcripts found" — that's a real answer, not a reason to keep
searching Gmail or Max's Drive.

Auth: uses application-default credentials. If `gcloud auth application-default
print-access-token` fails, run `gcloud auth application-default login` first.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request

AE_FOLDERS = {
    "Silvana": "1V9ssE4qJmc_gbtpqCSWyYZuPbWtIzP72",
    "Faisal": "1ZEdaMnurRQ54wzIfQK8G-AGtzrYM8k8h",
}
QUOTA_PROJECT = "gcp-dev-field-eng-aiapiquota"
CALENDAR_OWNER = "max.duganknight@databricks.com"

TS_PATTERN = re.compile(r"(\d{4})/(\d{2})/(\d{2})\s+(\d{1,2}):(\d{2})")


def get_token() -> str:
    r = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(
            "Could not get application-default token. Run:\n"
            "  gcloud auth application-default login"
        )
    return r.stdout.strip()


def http_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": QUOTA_PROJECT,
    })
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def list_calendar_events(token: str, customer: str, since: dt.date, until: dt.date) -> list[dict]:
    qp = urllib.parse.urlencode({
        "timeMin": f"{since.isoformat()}T00:00:00Z",
        "timeMax": f"{until.isoformat()}T23:59:59Z",
        "maxResults": 250,
        "singleEvents": "true",
        "orderBy": "startTime",
        "q": customer,
    })
    cal = urllib.parse.quote(CALENDAR_OWNER, safe="")
    data = http_get(f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events?{qp}", token)
    out = []
    for e in data.get("items", []):
        start = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date")
        if start:
            out.append({"summary": e.get("summary", ""), "start": start})
    return out


def list_folder_docs(token: str, folder_id: str, since: dt.date, until: dt.date) -> list[dict]:
    lo = since - dt.timedelta(days=2)
    hi = until + dt.timedelta(days=7)
    q = " and ".join([
        f"'{folder_id}' in parents",
        "trashed=false",
        "mimeType='application/vnd.google-apps.document'",
        "name contains 'Notes by Gemini'",
        f"modifiedTime > '{lo.isoformat()}T00:00:00Z'",
        f"modifiedTime < '{hi.isoformat()}T23:59:59Z'",
    ])
    qp = urllib.parse.urlencode({
        "q": q,
        "orderBy": "modifiedTime desc",
        "pageSize": 200,
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
        "fields": "files(id,name,modifiedTime,owners(emailAddress))",
    })
    return http_get(f"https://www.googleapis.com/drive/v3/files?{qp}", token).get("files", [])


def fetch_doc_text(token: str, doc_id: str) -> str:
    url = f"https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=text/plain"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "X-Goog-User-Project": QUOTA_PROJECT,
    })
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="replace")


def save_transcript(text: str, customer: str, ev_date: str, doc_id: str) -> pathlib.Path:
    out_dir = pathlib.Path("/tmp/transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", customer.lower()).strip("_")
    path = out_dir / f"{slug}_{ev_date}_{doc_id[:8]}.txt"
    path.write_text(text)
    return path


def list_max_drive_docs(token: str, since: dt.date, until: dt.date) -> list[dict]:
    lo = since - dt.timedelta(days=2)
    hi = until + dt.timedelta(days=7)
    q = " and ".join([
        "name contains 'Notes by Gemini'",
        "trashed=false",
        "mimeType='application/vnd.google-apps.document'",
        "'me' in owners",
        f"modifiedTime > '{lo.isoformat()}T00:00:00Z'",
        f"modifiedTime < '{hi.isoformat()}T23:59:59Z'",
    ])
    qp = urllib.parse.urlencode({
        "q": q,
        "orderBy": "modifiedTime desc",
        "pageSize": 200,
        "fields": "files(id,name,modifiedTime)",
    })
    return http_get(f"https://www.googleapis.com/drive/v3/files?{qp}", token).get("files", [])


def parse_title_ts(name: str) -> tuple[str, str] | None:
    m = TS_PATTERN.search(name)
    if not m:
        return None
    y, mo, d, h, mi = m.groups()
    return (f"{y}-{mo}-{d}", f"{int(h):02d}:{int(mi):02d}")


def event_local(start_iso: str) -> tuple[str, str] | None:
    if "T" not in start_iso:
        return None
    date_part, time_part = start_iso.split("T", 1)
    hh, mm = time_part.split(":")[:2]
    return (date_part, f"{int(hh):02d}:{int(mm):02d}")


def minute_diff(a: str, b: str) -> int:
    h1, m1 = map(int, a.split(":"))
    h2, m2 = map(int, b.split(":"))
    return abs((h1 * 60 + m1) - (h2 * 60 + m2))


def match(events: list[dict], docs: list[dict], tolerance_min: int = 10) -> list[dict]:
    seen = set()
    matches = []
    for ev in events:
        ev_local = event_local(ev["start"])
        if not ev_local:
            continue
        ev_date, ev_time = ev_local
        for doc in docs:
            ts = parse_title_ts(doc["name"])
            if not ts:
                continue
            doc_date, doc_time = ts
            if doc_date != ev_date:
                continue
            if minute_diff(doc_time, ev_time) > tolerance_min:
                continue
            key = (ev["start"], doc["id"])
            if key in seen:
                continue
            seen.add(key)
            matches.append({"event": ev, "doc": doc})
    return matches


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--customer", required=True, help="Customer name (calendar query term).")
    p.add_argument("--since", required=True, help="YYYY-MM-DD")
    p.add_argument("--until", help="YYYY-MM-DD (default: today)")
    p.add_argument("--json", action="store_true", help="Emit JSON for programmatic use.")
    p.add_argument("--fetch", action="store_true",
                   help="Download matched transcripts to /tmp/transcripts/ as plain text.")
    args = p.parse_args()

    since = dt.date.fromisoformat(args.since)
    until = dt.date.fromisoformat(args.until) if args.until else dt.date.today()

    token = get_token()
    events = list_calendar_events(token, args.customer, since, until)

    if args.json:
        result = {"customer": args.customer, "since": str(since), "until": str(until),
                  "events": events, "matches": []}

    if not events:
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"No calendar events for '{args.customer}' from {since} to {until}.")
            print("Nothing to match against. Done.")
        return

    if not args.json:
        print(f"Calendar events for '{args.customer}' from {since} to {until}: {len(events)}")
        for ev in events:
            print(f"  {ev['start']:32} | {ev['summary']}")

    docs: list[dict] = []
    for ae, fid in AE_FOLDERS.items():
        try:
            d = list_folder_docs(token, fid, since, until)
            if not args.json:
                print(f"\n{ae}'s folder: {len(d)} Gemini docs in window")
            docs.extend(d)
        except Exception as e:
            print(f"{ae}'s folder: ERROR {e}", file=sys.stderr)
    try:
        md = list_max_drive_docs(token, since, until)
        if not args.json:
            print(f"Max's Drive: {len(md)} Gemini docs in window")
        docs.extend(md)
    except Exception as e:
        print(f"Max's Drive: ERROR {e}", file=sys.stderr)

    matches = match(events, docs)

    saved_paths: dict[str, pathlib.Path] = {}
    if args.fetch and matches:
        for m in matches:
            doc_id = m["doc"]["id"]
            if doc_id in saved_paths:
                continue
            ev_date = m["event"]["start"].split("T", 1)[0]
            try:
                text = fetch_doc_text(token, doc_id)
                saved_paths[doc_id] = save_transcript(text, args.customer, ev_date, doc_id)
            except Exception as e:
                print(f"Fetch failed for {doc_id}: {e}", file=sys.stderr)

    if args.json:
        for m in matches:
            entry = {
                "event_summary": m["event"]["summary"],
                "event_start": m["event"]["start"],
                "doc_id": m["doc"]["id"],
                "doc_name": m["doc"]["name"],
                "doc_url": f"https://docs.google.com/document/d/{m['doc']['id']}/edit",
            }
            if m["doc"]["id"] in saved_paths:
                entry["local_path"] = str(saved_paths[m["doc"]["id"]])
            result["matches"].append(entry)
        print(json.dumps(result, indent=2))
        return

    print(f"\n=== Matched transcripts: {len(matches)} ===")
    if not matches:
        print("No transcripts matched these meetings.")
        print("(Either none were recorded, or filenames don't include the meeting time.)")
        print("Falling back to Gmail is unlikely to help — Gemini transcripts go to Drive, not email.")
        return
    for m in matches:
        ev, doc = m["event"], m["doc"]
        print(f"- {ev['start']} | {ev['summary']}")
        print(f"    {doc['name']}")
        print(f"    https://docs.google.com/document/d/{doc['id']}/edit")
        if doc["id"] in saved_paths:
            print(f"    saved: {saved_paths[doc['id']]}")


if __name__ == "__main__":
    main()
