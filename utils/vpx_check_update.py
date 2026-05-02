#!/usr/bin/env python3
# =============================================================================
# vpx_check_update.py — Standalone CLI version of the Batocera service
# Author  : Modhack
# Purpose : Scan a directory of .vpx tables, match them against the Visual
#           Pinball Spreadsheet (VPS) database, and print which ones have
#           updates available.
#
# Usage   : ./vpx_check_update.py [--dir PATH] [--all] [--no-match]
#           ./vpx_check_update.py --dir ~/vpinball
#           ./vpx_check_update.py --all      # show every file, not only outdated ones
#           ./vpx_check_update.py --no-match # also list files with no DB match
# =============================================================================

import argparse
import json
import os
import re
import sys
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

VPS_JSON_URL = "https://virtualpinballspreadsheet.github.io/vps-db/db/vpsdb.json"
DEFAULT_DIR  = Path("/userdata/roms/vpinball")
MIN_SCORE    = 0.62

GENERIC_WORDS = {
    'the', 'and', 'of', 'in', 'on', 'at', 'to', 'an', 'with',
    'le', 'la', 'les', 'de', 'du', 'no', 'vs',
}

AUTHOR_CANON_MAP = {
    "vpw": "vpw", "vpwteam": "vpw", "vpinworkshop": "vpw",
    "virtualpinworkshop": "vpw", "vpinworkshopteam": "vpw",
    "bigus": "bigus", "bigusmod": "bigus", "bigus1": "bigus",
    "jpsalas": "jpsalas", "g5k": "g5k", "lwlost": "lw", "lw": "lw",
}

FILENAME_AUTHOR_ALIASES = {
    "bigusmod": "Bigus1",
    "bigus":    "Bigus1",
    "vpwmod":   "VPin Workshop",
    "vpw":      "VPin Workshop",
}

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def norm_token(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def split_camelcase(s):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', s)

def tokenize(text):
    return [t for t in re.findall(r'[a-z0-9]{2,}', text.lower()) if t not in GENERIC_WORDS]

def extract_year(text):
    m = re.findall(r'(?:^|[^0-9])(19[3-9]\d|20[0-2]\d|2030)(?:[^0-9]|$)', text)
    return int(m[0]) if m else None

def clean_title_for_match(filename):
    name = Path(filename).stem
    name = split_camelcase(name)
    for pat in (r"\([^)]*\)", r"\[[^\]]*\]"):
        name = re.sub(pat, " ", name)
    name = re.sub(r"[vV]\.?\d+(?:\.\d+){0,3}(?![A-Za-z0-9.])", " ", name)
    name = re.sub(r"(?<![A-Za-z0-9])\d+(?:\.\d+){1,3}(?![A-Za-z0-9])", " ", name)
    for pat in (r"_+", r"-+", r"\s+"):
        name = re.sub(pat, " ", name)
    return name.strip()

def extract_version_from_text(text):
    cleaned = re.sub(r'\(\s*[^)]*\b(?:19[3-9]\d|20[0-2]\d|2030)\b[^)]*\)', '', text)
    m = re.findall(r'[vV]\.?(\d+(?:\.\d+){0,3})', cleaned)
    if m:
        return m[-1]
    cleaned = re.sub(r'\.vpx$', '', cleaned, flags=re.IGNORECASE)
    m = re.findall(r'(?<![\d.])(\d+\.\d+(?:\.\d+){0,2})(?!\d)', cleaned)
    if m:
        return m[-1]
    return None

def normalize_version(ver):
    if not ver:
        return None
    cleaned = re.sub(r'[^0-9\.]', '', ver)
    parts = [p for p in cleaned.split('.') if p]
    if not parts:
        return None
    try:
        return tuple(int(p) for p in parts)
    except Exception:
        return None

def compare_versions(a, b):
    ta, tb = normalize_version(a), normalize_version(b)
    if ta is None or tb is None:
        return None
    length = max(len(ta), len(tb))
    ta += (0,) * (length - len(ta))
    tb += (0,) * (length - len(tb))
    return -1 if ta < tb else (1 if ta > tb else 0)

# ---------------------------------------------------------------------------
# Author detection
# ---------------------------------------------------------------------------

def canonical_author_token(s):
    return AUTHOR_CANON_MAP.get(norm_token(s), norm_token(s))

def collect_authors(db):
    idx = {}
    for entry in db:
        for tf in (entry.get("tableFiles") or []):
            if tf.get("tableFormat") != "VPX":
                continue
            for a in (tf.get("authors") or []):
                s = a if isinstance(a, str) else str(a)
                na = norm_token(s)
                if na and na not in idx:
                    idx[na] = s
    return idx

def detect_author_from_filename(filename, authors_index):
    stem = Path(filename).stem
    nfile = norm_token(stem)
    for token, display in FILENAME_AUTHOR_ALIASES.items():
        if token in nfile:
            return canonical_author_token(display), display
    for chunk in re.findall(r'\(([^)]+)\)', stem):
        nchunk = norm_token(chunk)
        if not nchunk or re.fullmatch(r'\d{4}', nchunk):
            continue
        hits = [(len(na), orig) for na, orig in authors_index.items()
                if na and len(na) >= 3 and na in nchunk]
        if hits:
            hits.sort(reverse=True)
            chosen = hits[0][1]
            return canonical_author_token(chosen), chosen
    return None, None

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_entry(entry, filename):
    base = clean_title_for_match(filename).lower()
    file_tokens_list = tokenize(base)
    file_tokens = set(file_tokens_list)
    file_norm = norm_token(base)
    year = extract_year(filename)

    db_names = [(entry.get("name") or "").lower()]
    db_names += [str(a).lower() for a in (entry.get("altNames") or [])]

    best = 0.0
    for nm in db_names:
        if not nm:
            continue
        s_seq = SequenceMatcher(None, base, nm).ratio()
        db_tokens_list = tokenize(nm)
        db_tokens = set(db_tokens_list)
        s_fwd = (len(file_tokens & db_tokens) / len(db_tokens)) if db_tokens else 0
        db_norm = norm_token(nm)
        s_sub = 0.85 if (len(db_norm) >= 4 and db_norm in file_norm and s_seq >= 0.30) else 0
        s_rev = 0
        if len(file_norm) >= 6 and file_norm in db_norm:
            if year and entry.get("year"):
                try:
                    s_rev = 0.78 if abs(int(entry["year"]) - year) <= 3 else 0.70
                except Exception:
                    s_rev = 0.70
            else:
                s_rev = 0.70
        s_pre = 0
        if (len(file_tokens_list) >= 2 and len(db_tokens_list) >= 2
                and file_tokens_list[:2] == db_tokens_list[:2]):
            s_pre = 0.65
        best = max(best, s_seq, s_fwd, s_sub, s_rev, s_pre)

    if year and entry.get("year"):
        try:
            y = int(entry["year"])
            diff = abs(y - year)
            if diff == 0:
                best += 0.20
            elif diff <= 1:
                best += 0.10
            elif diff <= 3:
                best += 0.03
            elif diff >= 5:
                best -= 0.10
        except Exception:
            pass
    return best

def best_entry(db, filename, min_score=MIN_SCORE):
    cands = []
    for e in db:
        if not any(tf.get("tableFormat") == "VPX" for tf in (e.get("tableFiles") or [])):
            continue
        s = score_entry(e, filename)
        if s >= min_score:
            cands.append((s, e))
    if not cands:
        return None, 0.0
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1], cands[0][0]

def best_db_version(entry, author_canon):
    vpx_files = [tf for tf in (entry.get("tableFiles") or []) if tf.get("tableFormat") == "VPX"]
    if not vpx_files:
        return None
    candidates = []
    if author_canon:
        for tf in vpx_files:
            for a in (tf.get("authors") or []):
                s = a if isinstance(a, str) else str(a)
                if canonical_author_token(s) == author_canon:
                    candidates.append(tf)
                    break
        if not candidates:
            candidates = vpx_files
    else:
        candidates = vpx_files
    best_ver = None
    for tf in candidates:
        v = str(tf.get("version") or "").strip() or None
        if not v:
            continue
        if best_ver is None or compare_versions(v, best_ver) == 1:
            best_ver = v
    return best_ver

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

class C:
    """ANSI color codes (auto-disabled if stdout is not a TTY)."""
    if sys.stdout.isatty():
        R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"; B = "\033[34m"
        M = "\033[35m"; CY = "\033[36m"; D = "\033[2m"; X = "\033[0m"
    else:
        R = G = Y = B = M = CY = D = X = ""

def truncate(s, n):
    return s if len(s) <= n else s[:n-1] + "…"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_db(cache_path=None):
    if cache_path and Path(cache_path).is_file():
        with open(cache_path) as f:
            return json.load(f)
    print(f"{C.D}Downloading VPS database…{C.X}", file=sys.stderr)
    with urllib.request.urlopen(VPS_JSON_URL, timeout=60) as r:
        data = r.read()
    if cache_path:
        Path(cache_path).write_bytes(data)
    return json.loads(data)

def main():
    ap = argparse.ArgumentParser(
        description="Check VPX tables against the VPS database and list updates available.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--dir", "-d", type=Path, default=DEFAULT_DIR,
                    help=f"Directory to scan recursively (default: {DEFAULT_DIR})")
    ap.add_argument("--all", "-a", action="store_true",
                    help="Show every matched file, not only outdated ones")
    ap.add_argument("--no-match", "-n", action="store_true",
                    help="Also list files for which no DB entry was matched")
    ap.add_argument("--cache", type=Path,
                    help="Cache the VPS DB at this path (downloaded only if missing)")
    args = ap.parse_args()

    if not args.dir.exists():
        print(f"{C.R}Directory not found: {args.dir}{C.X}", file=sys.stderr)
        sys.exit(1)

    try:
        db = load_db(args.cache)
    except Exception as exc:
        print(f"{C.R}Failed to load VPS DB: {exc}{C.X}", file=sys.stderr)
        sys.exit(2)

    authors_index = collect_authors(db)

    files = sorted(p for p in args.dir.rglob("*.vpx"))
    if not files:
        print(f"{C.Y}No .vpx files found under {args.dir}{C.X}")
        return

    outdated, current, no_match, no_local_ver = [], [], [], []

    for path in files:
        filename = path.name
        author_canon, _ = detect_author_from_filename(filename, authors_index)
        entry, score = best_entry(db, filename)
        if not entry:
            no_match.append((filename, score))
            continue
        db_ver = best_db_version(entry, author_canon)
        loc_ver = extract_version_from_text(filename)
        if not loc_ver:
            no_local_ver.append((filename, entry, db_ver))
            continue
        cmp = compare_versions(loc_ver, db_ver)
        row = (filename, entry, loc_ver, db_ver, score)
        if cmp == -1:
            outdated.append(row)
        else:
            current.append(row)

    print(f"\n{C.B}Scanned:{C.X} {len(files)} file(s) under {args.dir}")
    print(f"  {C.G}up-to-date:{C.X}     {len(current)}")
    print(f"  {C.Y}outdated:{C.X}       {len(outdated)}")
    print(f"  {C.D}unknown version:{C.X} {len(no_local_ver)}")
    print(f"  {C.R}no DB match:{C.X}    {len(no_match)}")

    if outdated:
        print(f"\n{C.Y}━━━ Updates available ({len(outdated)}) ━━━{C.X}")
        for fn, e, lv, dv, sc in outdated:
            name = e.get("name") or "?"
            year = e.get("year") or "?"
            print(f"  {C.Y}↑{C.X} {truncate(fn, 60):60s}  "
                  f"{C.R}{lv}{C.X} → {C.G}{dv}{C.X}  "
                  f"{C.D}({name} {year}){C.X}")

    if args.all and current:
        print(f"\n{C.G}━━━ Up to date ({len(current)}) ━━━{C.X}")
        for fn, e, lv, dv, sc in current:
            name = e.get("name") or "?"
            year = e.get("year") or "?"
            print(f"  {C.G}={C.X} {truncate(fn, 60):60s}  "
                  f"{lv}  {C.D}({name} {year}){C.X}")

    if args.no_match and no_match:
        print(f"\n{C.R}━━━ No DB match ({len(no_match)}) ━━━{C.X}")
        for fn, sc in no_match:
            print(f"  {C.R}?{C.X} {truncate(fn, 70):70s}  {C.D}best score: {sc:.2f}{C.X}")

    if args.all and no_local_ver:
        print(f"\n{C.D}━━━ No local version found ({len(no_local_ver)}) ━━━{C.X}")
        for fn, e, dv in no_local_ver:
            name = e.get("name") or "?"
            print(f"  · {truncate(fn, 60):60s}  DB: {dv}  {C.D}({name}){C.X}")

    sys.exit(1 if outdated else 0)

if __name__ == "__main__":
    main()
