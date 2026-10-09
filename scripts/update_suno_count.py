#!/usr/bin/env python3
"""Fetch the public Suno track count for a handle and write it to data/suno.json.

Fail safe: on any error or implausible value, the existing file is left untouched
and the script exits 0, so the page keeps showing the last good value.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

HANDLE = os.environ.get("SUNO_HANDLE", "evevev")
OUT = os.environ.get("SUNO_OUT", "data/suno.json")
URL = (f"https://studio-api-prod.suno.com/api/profiles/{HANDLE}"
       "?clips_sort_by=created_at&playlists_sort_by=created_at&page=1")

def main():
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "enactedvolition-site-count/1.0",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        count = data.get("num_total_clips")
        if not isinstance(count, int) or not (0 < count < 100000) or data.get("handle") != HANDLE:
            raise ValueError(f"unexpected response: num_total_clips={count!r} handle={data.get('handle')!r}")
    except Exception as e:  # keep the last value
        print(f"::warning::Suno count fetch failed, keeping last value: {e}")
        return 0
    old = None
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT)).get("tracks")
        except Exception:
            pass
    if old == count:
        print(f"unchanged: {count}")
        return 0
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    payload = {"handle": HANDLE, "tracks": count,
               "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": f"https://suno.com/@{HANDLE} (public profile API, num_total_clips)"}
    with open(OUT + ".tmp", "w") as f:
        json.dump(payload, f, indent=2); f.write("\n")
    os.replace(OUT + ".tmp", OUT)
    print(f"updated: {old} -> {count}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
