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

### 2. Enable the service

Either from the command line:

```bash
batocera-services enable vpx_check_update
batocera-services start vpx_check_update
```

Or from the EmulationStation UI:

```
Main Menu → System Settings → Services → vpx_check_update → Enable
```

### 3. Verify installation

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

