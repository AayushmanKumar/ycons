"""SQLite storage: companies, markets, members, snapshots, pings.

One file (data/radar.db). Snapshots build the history Crustdata doesn't keep
(search and ad fields are current-value only).
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "radar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY,          -- crustdata_company_id
    name        TEXT NOT NULL,
    domain      TEXT NOT NULL,
    size        TEXT
);
CREATE TABLE IF NOT EXISTS markets (
    key         TEXT PRIMARY KEY,             -- 'self' or a client key
    role        TEXT NOT NULL CHECK (role IN ('you', 'client')),
    self_id     INTEGER NOT NULL REFERENCES companies(id),
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_members (
    market_key  TEXT NOT NULL REFERENCES markets(key) ON DELETE CASCADE,
    domain      TEXT NOT NULL,
    company_id  INTEGER REFERENCES companies(id),
    is_self     INTEGER NOT NULL DEFAULT 0,
    kept        INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    PRIMARY KEY (market_key, domain)
);
CREATE TABLE IF NOT EXISTS snapshots (
    company_id         INTEGER NOT NULL REFERENCES companies(id),
    fetched_at         TEXT NOT NULL,         -- when we fetched it
    source_updated_at  TEXT,                  -- Crustdata's own refresh timestamp
    payload            TEXT NOT NULL,         -- normalised company record (JSON)
    PRIMARY KEY (company_id, fetched_at)
);
CREATE TABLE IF NOT EXISTS pings (
    key         TEXT PRIMARY KEY,             -- company + event + period: never sent twice
    market_key  TEXT NOT NULL,
    company_id  INTEGER,
    kind        TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    payload     TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=DB_PATH):
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    return db


# ---- companies & markets ---------------------------------------------------

def upsert_company(db, cid, name, domain, size=None):
    db.execute(
        "INSERT INTO companies (id, name, domain, size) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, domain = excluded.domain, size = excluded.size",
        (cid, name, domain, size))


def save_market(db, key, role, self_id, members):
    """members: [{domain, company_id, is_self, kept, reason}]. Replaces the member list."""
    with db:
        db.execute(
            "INSERT INTO markets (key, role, self_id, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET role = excluded.role, self_id = excluded.self_id",
            (key, role, self_id, now()))
        db.execute("DELETE FROM market_members WHERE market_key = ?", (key,))
        db.executemany(
            "INSERT INTO market_members (market_key, domain, company_id, is_self, kept, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(key, m["domain"], m.get("company_id"), int(m.get("is_self", False)), int(m["kept"]), m["reason"])
             for m in members])


def delete_markets(db):
    """Forget all markets (companies, snapshots and pings are kept)."""
    with db:
        db.execute("DELETE FROM market_members")
        db.execute("DELETE FROM markets")


def markets(db):
    return [dict(r) for r in db.execute("SELECT * FROM markets ORDER BY role DESC, key")]


def members(db, key, kept_only=False):
    sql = ("SELECT mm.*, c.name, c.size FROM market_members mm "
           "LEFT JOIN companies c ON c.id = mm.company_id WHERE mm.market_key = ?")
    if kept_only:
        sql += " AND mm.kept = 1"
    return [dict(r) for r in db.execute(sql + " ORDER BY mm.is_self DESC, mm.domain", (key,))]


# ---- snapshots -------------------------------------------------------------

def latest_snapshot(db, company_id, as_of=None):
    """Most recent snapshot fetched on or before as_of (ISO string), or the latest overall."""
    sql, args = "SELECT * FROM snapshots WHERE company_id = ?", [company_id]
    if as_of:
        sql += " AND fetched_at <= ?"
        args.append(as_of)
    row = db.execute(sql + " ORDER BY fetched_at DESC LIMIT 1", args).fetchone()
    return {**dict(row), "payload": json.loads(row["payload"])} if row else None


def earliest_snapshot(db, company_id):
    row = db.execute("SELECT * FROM snapshots WHERE company_id = ? ORDER BY fetched_at LIMIT 1",
                     (company_id,)).fetchone()
    return {**dict(row), "payload": json.loads(row["payload"])} if row else None


def last_fetch(db):
    """Date (YYYY-MM-DD) of the most recent snapshot, or None."""
    row = db.execute("SELECT MAX(fetched_at) AS f FROM snapshots").fetchone()
    return row["f"][:10] if row and row["f"] else None


def add_snapshot(db, company_id, payload, source_updated_at, fetched_at=None):
    """Store a snapshot unless Crustdata hasn't refreshed the company since the last one.

    Returns True if a new snapshot was stored.
    """
    last = latest_snapshot(db, company_id)
    if last and source_updated_at and last["source_updated_at"] == source_updated_at:
        return False
    with db:
        db.execute(
            "INSERT OR REPLACE INTO snapshots (company_id, fetched_at, source_updated_at, payload) VALUES (?, ?, ?, ?)",
            (company_id, fetched_at or now(), source_updated_at, json.dumps(payload)))
    return True


# ---- pings -----------------------------------------------------------------

def add_ping(db, ping, first_seen=None):
    """Insert a ping if its key is new. Returns True if inserted (i.e. should be sent)."""
    with db:
        cur = db.execute(
            "INSERT OR IGNORE INTO pings (key, market_key, company_id, kind, first_seen, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ping["key"], ping["market"], ping.get("company_id"), ping["kind"], first_seen or now(), json.dumps(ping)))
    return cur.rowcount == 1


def pings(db, as_of=None):
    sql, args = "SELECT * FROM pings", []
    if as_of:
        sql += " WHERE first_seen <= ?"
        args.append(as_of)
    return [{**json.loads(r["payload"]), "first_seen": r["first_seen"]}
            for r in db.execute(sql + " ORDER BY first_seen DESC", args)]
