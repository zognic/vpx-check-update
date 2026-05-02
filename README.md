# vpx_check_update

**Author:** Modhack  
**Platform:** Batocera Linux  
**Category:** Service / EmulationStation notification

---

## What it does

`vpx_check_update` is a Batocera service that automatically checks whether your local Visual Pinball X (VPX) tables have updates available in the **Visual Pinball Spreadsheet (VPS) database**.

When you navigate to the **vpinball** system in EmulationStation, the service silently runs in the background and:

1. Downloads the latest VPS database from `virtualpinballspreadsheet.github.io`
2. Scans all `.vpx` files in `/userdata/roms/vpinball` recursively
3. Matches each file to a DB entry using fuzzy title comparison (with year bonus)
4. Detects the table's author/team from the filename (VPW, Bigus, etc.)
5. Compares the local version (extracted from the filename) against the DB version
6. If any tables are outdated, displays an overlay notification in EmulationStation:

```
◎  5 VPX tables available for update
```

The check only runs **once at a time** — a lockfile prevents duplicate runs if you navigate away and back quickly.

---

## How it works internally

```
Batocera boot
  └── Service starts (case start)
        └── Installs ES hook → scripts/system-selected/vpx_check_notif.sh

EmulationStation — user selects vpinball system
  └── ES fires system-selected event → $1 = "vpinball"
        └── Hook checks lockfile → not running?
              └── Spawns background process
                    ├── Downloads VPS DB (JSON)
                    ├── Walks /userdata/roms/vpinball/*.vpx
                    ├── Fuzzy-matches titles + detects authors
                    ├── Compares versions
                    └── POST http://localhost:1234/notify → ES overlay

Batocera shutdown / service disabled
  └── Service stops (case stop)
        └── Removes ES hook and lockfile
```

---

## Installation

### 1. Copy the service file

```bash
cp vpx_check_update /userdata/system/services/
```

> **Important:** The filename must contain only letters `A–Z`, digits `0–9` and underscores.  
> Do **not** add a `.sh` extension — Batocera services must have no extension.

### 2. Make the service executable

```bash
chmod +x /userdata/system/services/vpx_check_update
```

> Without execute permission, Batocera will not be able to start the service.

### 3. Enable the service

Either from the command line:

```bash
batocera-services enable vpx_check_update
batocera-services start vpx_check_update
```

Or from the EmulationStation UI:

```
Main Menu → System Settings → Services → vpx_check_update → Enable
```

### 4. Verify installation

After enabling, check that the ES hook was created:

```bash
ls /userdata/system/configs/emulationstation/scripts/system-selected/
# Expected: vpx_check_notif.sh
```

List active services:

```bash
batocera-services list user
```

---

## Disabling the service

From the ES UI:

```
Main Menu → System Settings → Services → vpx_check_update → Disable
```

Or from the command line:

```bash
batocera-services stop vpx_check_update
batocera-services disable vpx_check_update
```

This automatically removes the ES hook script and any leftover lockfile.

---

## Requirements

| Requirement | Notes |
|---|---|
| Batocera v38+ | Services system required |
| Network access | VPS DB is downloaded at runtime |
| `python3` | Pre-installed on Batocera |
| `requests` library | Pre-installed on Batocera |
| `curl` | Pre-installed on Batocera |
| VPX roms directory | `/userdata/roms/vpinball/` must exist |

---

## Author detection

The script recognises common author/team aliases found in filenames:

| Filename contains | Detected as |
|---|---|
| `VPW`, `VPWmod` | VPin Workshop |
| `Bigus`, `Bigus(MOD)` | Bigus1 |
| Any author from the VPS DB | Matched automatically |

Version numbers are extracted directly from the filename (e.g. `TableName (VPW) 1.2.3.vpx` → `1.2.3`).

---

## Troubleshooting

**Notification does not appear**  
- Make sure EmulationStation is running (the HTTP API is on `localhost:1234`)  
- Check that `PublicWebAccess` or local access is not blocked  
- Verify the hook script exists and is executable:
  ```bash
  ls -la /userdata/system/configs/emulationstation/scripts/system-selected/
  ```

**Check runs multiple times**  
- The lockfile at `/tmp/vpx_check_notif.lock` prevents this — it is removed automatically when the check completes

**No match found for my tables**  
- The fuzzy match threshold is `0.62` — tables with unusual naming may not match  
- Version must be present in the filename for comparison to work

---

## Standalone CLI (`utils/vpx_check_update.py`)

A standalone Python version of the same matcher is provided in `utils/` for running outside of EmulationStation — useful for inspecting the full list of outdated tables, debugging fuzzy matches, or running on a desktop.

```bash
# scan the default Batocera directory
./utils/vpx_check_update.py

# scan an arbitrary directory
./utils/vpx_check_update.py --dir ~/vpinball

# also show files already up to date and files with no DB match
./utils/vpx_check_update.py --all --no-match

# cache the VPS DB locally so repeat runs are fast
./utils/vpx_check_update.py --cache ~/.cache/vpsdb.json
```

Output is colored when run on a TTY and looks like:

```
Scanned: 42 file(s) under /userdata/roms/vpinball
  up-to-date:      29
  outdated:        8
  unknown version: 2
  no DB match:     3

━━━ Updates available (8) ━━━
  ↑ Futurama (Original 2024) v1.2.1.vpx              1.2.1 → 1.2.2  (Futurama 2024)
  ↑ Terrifier (original)v1.0.1 -pg13.vpx             1.0.1 → 1.0.2  (Terrifier 2024)
  …
```

Exit code is `1` when at least one table is outdated, `0` otherwise — handy for cron / CI use.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

