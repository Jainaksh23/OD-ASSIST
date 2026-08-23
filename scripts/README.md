# OD Assist Utility Scripts

This folder contains reusable maintenance and utility scripts for managing the OD Assist application. 

These scripts can be executed directly from this `scripts/` directory or from the root directory.

## Available Scripts

### `check_duplicates.py`
Scans the PostgreSQL database for duplicate sources (based on exact matching `source_url`). 
If duplicates are found, it automatically cleans them up by keeping the most recently processed/completed version and deleting the rest (including their associated chunks).

**Usage:**
```bash
python scripts/check_duplicates.py
```

### `process_pending.py`
A robust, generic worker script that auto-processes all pending sources in the database.
- Checks for and resets any sources that have been stuck in "processing" for > 1 hour.
- Safe to run alongside the main application.
- Good for manually triggering bulk background jobs if the main auto-processor is busy.

**Usage:**
```bash
python scripts/process_pending.py
```

### `seed_admin.py`
A setup script used to create the initial admin user account.
- Reads `ADMIN_PASSWORD` from the `.env` file (defaults to `OkieDokie@123`).
- Username is always `odadmin`.
- Safe to run multiple times (it will just skip if the user already exists).

**Usage:**
```bash
python scripts/seed_admin.py
```
