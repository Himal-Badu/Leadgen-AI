"""Database interaction layer for the shared team-db (Turso-synced SQLite).

Uses the team-db CLI to read/write the shared database.
This module provides a clean Python API over the CLI interface.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# True when the shared team-db CLI exists on this machine. On serverless
# runtimes (Vercel) it does not, so we fall back to a local SQLite file.
_TEAM_DB_AVAILABLE = shutil.which("team-db") is not None
_LOCAL_DB_PATH: Optional[str] = None


def _local_db_path() -> str:
    """Return the path of the local SQLite fallback DB (DATA_DIR/localpulse.db)."""
    global _LOCAL_DB_PATH
    if _LOCAL_DB_PATH is None:
        data_dir = os.environ.get("DATA_DIR", "/tmp/localpulse-data")
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        _LOCAL_DB_PATH = os.path.join(data_dir, "localpulse.db")
    return _LOCAL_DB_PATH


def _run_local_sqlite(sql: str) -> list[dict[str, Any]]:
    """Execute SQL against the local SQLite fallback DB and return rows."""
    conn = sqlite3.connect(_local_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql)
        if sql.lstrip().upper().startswith("SELECT"):
            return [dict(r) for r in cur.fetchall()]
        conn.commit()
        return []
    finally:
        conn.close()


def _run_team_db(sql: str, max_retries: int = 3) -> list[dict[str, Any]]:
    """Execute a SQL statement via the team-db CLI and return parsed JSON rows.

    The shared DB is synced across concurrent writers (web app, agents, tests),
    so transient "file locked by another process" errors can occur. Retry
    briefly with a short backoff before giving up.

    Serverless safety: when the team-db CLI is missing (Vercel) — or when
    DATABASE_URL is configured (storage treated as external/optional) — we
    transparently fall back to a local SQLite file under DATA_DIR so the app
    never crashes on import or query just because the CLI is absent.
    """
    if not _TEAM_DB_AVAILABLE or os.environ.get("DATABASE_URL"):
        return _run_local_sqlite(sql)
    last_error: Optional[str] = None
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["team-db", sql],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as e:
            last_error = f"team-db timed out after 30s: {e}"
            time.sleep(0.5 * (attempt + 1))
            continue
        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                return []
            try:
                return json.loads(output)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse team-db output: {e} — got: {output}")
        last_error = result.stderr.strip()
        # Only retry transient lock errors, not genuine SQL failures.
        if "Locking error" in last_error or "lock" in last_error.lower():
            time.sleep(0.5 * (attempt + 1))
            continue
        raise RuntimeError(f"team-db error: {last_error}")
    raise RuntimeError(f"team-db error: {last_error}")


# ─── Snapshot CRUD ────────────────────────────────────────────────────────────

def create_snapshot(
    business_name: str,
    location: str,
    website: str = "",
) -> str:
    """Create a new business health snapshot. Returns the new snapshot ID."""
    snap_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    initial_data = json.dumps({
        "business_info": {
            "name": business_name,
            "location": location,
            "website": website,
        },
    })
    sql = (
        f"INSERT INTO snapshots (id, business_name, location, website, status, data, created_at, updated_at) "
        f"VALUES ("
        f"'{snap_id}', "
        f"'{_esc(business_name)}', "
        f"'{_esc(location)}', "
        f"'{_esc(website)}', "
        f"'pending', "
        f"'{_esc(initial_data)}', "
        f"'{now}', "
        f"'{now}'"
        f")"
    )
    _run_team_db(sql)
    return snap_id


def get_snapshot(snapshot_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a snapshot by ID."""
    rows = _run_team_db(
        f"SELECT id, business_name, location, website, status, data, created_at, updated_at "
        f"FROM snapshots WHERE id = '{snapshot_id}'"
    )
    if not rows:
        return None
    row = rows[0]
    if row.get("data"):
        row["data"] = json.loads(row["data"])
    return row


def claim_next_snapshot(current_status: str, target_status: str) -> Optional[dict[str, Any]]:
    """Atomically claim the next snapshot for processing.

    Returns the snapshot row (with parsed data) or None if none available.
    Updates status to target_status atomically.
    """
    now = datetime.now(timezone.utc).isoformat()
    # Select the oldest pending snapshot
    rows = _run_team_db(
        f"SELECT id, business_name, location, website, status, data, created_at, updated_at "
        f"FROM snapshots WHERE status = '{current_status}' "
        f"ORDER BY created_at ASC LIMIT 1"
    )
    if not rows:
        return None
    row = rows[0]

    # Claim it by updating status
    _run_team_db(
        f"UPDATE snapshots SET status = '{target_status}', updated_at = '{now}' "
        f"WHERE id = '{row['id']}' AND status = '{current_status}'"
    )

    # Verify we claimed it
    updated = _run_team_db(
        f"SELECT status FROM snapshots WHERE id = '{row['id']}'"
    )
    if not updated or updated[0]["status"] != target_status:
        return None  # Another process claimed it first

    if row.get("data"):
        row["data"] = json.loads(row["data"])
    return row


def update_snapshot_data(snapshot_id: str, data_key: str, value: Any) -> None:
    """Update a section of the snapshot's data JSON blob (e.g., 'scout_data', 'analyzer_insights')."""
    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        raise ValueError(f"Snapshot {snapshot_id} not found")
    data = snapshot.get("data", {}) or {}
    data[data_key] = value
    now = datetime.now(timezone.utc).isoformat()
    _run_team_db(
        f"UPDATE snapshots SET data = '{_esc(json.dumps(data))}', updated_at = '{now}' "
        f"WHERE id = '{snapshot_id}'"
    )


def update_snapshot_status(snapshot_id: str, status: str) -> None:
    """Update the status of a snapshot."""
    now = datetime.now(timezone.utc).isoformat()
    _run_team_db(
        f"UPDATE snapshots SET status = '{status}', updated_at = '{now}' "
        f"WHERE id = '{snapshot_id}'"
    )


def list_snapshots(status: Optional[str] = None) -> list[dict[str, Any]]:
    """List snapshots, optionally filtered by status."""
    if status:
        rows = _run_team_db(
            f"SELECT id, business_name, location, website, status, created_at, updated_at "
            f"FROM snapshots WHERE status = '{status}' ORDER BY created_at DESC"
        )
    else:
        rows = _run_team_db(
            f"SELECT id, business_name, location, website, status, created_at, updated_at "
            f"FROM snapshots ORDER BY created_at DESC"
        )
    for row in rows:
        if row.get("data"):
            try:
                row["data"] = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                pass
    return rows


# ─── Outreach CRUD ────────────────────────────────────────────────────────────

def create_outreach(
    snapshot_id: str,
    channel: str,
    subject: str,
    body: str,
    status: str = "drafted",
) -> str:
    """Create an outreach record. Returns the new outreach ID."""
    out_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sql = (
        f"INSERT INTO outreach (id, snapshot_id, channel, status, subject, body, created_at, updated_at) "
        f"VALUES ("
        f"'{out_id}', "
        f"'{snapshot_id}', "
        f"'{channel}', "
        f"'{status}', "
        f"'{_esc(subject)}', "
        f"'{_esc(body)}', "
        f"'{now}', "
        f"'{now}'"
        f")"
    )
    _run_team_db(sql)
    return out_id


def get_outreach_by_snapshot(snapshot_id: str) -> list[dict[str, Any]]:
    """Retrieve all outreach records for a snapshot."""
    rows = _run_team_db(
        f"SELECT id, snapshot_id, channel, status, subject, body, created_at, updated_at "
        f"FROM outreach WHERE snapshot_id = '{snapshot_id}' ORDER BY created_at DESC"
    )
    return rows


def update_outreach_status(outreach_id: str, status: str) -> None:
    """Update the status of an outreach record."""
    now = datetime.now(timezone.utc).isoformat()
    _run_team_db(
        f"UPDATE outreach SET status = '{status}', updated_at = '{now}' "
        f"WHERE id = '{outreach_id}'"
    )


def list_outreach(status: Optional[str] = None) -> list[dict[str, Any]]:
    """List outreach records, optionally filtered by status."""
    if status:
        rows = _run_team_db(
            f"SELECT id, snapshot_id, channel, status, subject, body, created_at, updated_at "
            f"FROM outreach WHERE status = '{status}' ORDER BY created_at DESC"
        )
    else:
        rows = _run_team_db(
            f"SELECT id, snapshot_id, channel, status, subject, body, created_at, updated_at "
            f"FROM outreach ORDER BY created_at DESC"
        )
    return rows


def _esc(value: str) -> str:
    """Escape a string for SQLite by doubling single quotes."""
    return value.replace("'", "''")