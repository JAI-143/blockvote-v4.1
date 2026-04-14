"""
database.py — BlockVote v4
SQLite database with ward-in-charge role.
All timestamps stored in IST (UTC+5:30).
"""

import os, sqlite3, hashlib, csv, io
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S")


def parse_ist(dt_str: str) -> datetime:
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=IST)
    except Exception:
        return datetime.min.replace(tzinfo=IST)


class Database:

    def __init__(self, base_dir: str):
        db_dir = os.path.join(base_dir, "database")
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, "voters.db")
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        ts = now_ist()
        with self._conn() as c:
            c.executescript(f"""
                CREATE TABLE IF NOT EXISTS voters (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    voter_id         TEXT    UNIQUE NOT NULL,
                    name             TEXT    NOT NULL,
                    dob              TEXT,
                    phone            TEXT,
                    state            TEXT    NOT NULL DEFAULT '',
                    district         TEXT    NOT NULL DEFAULT '',
                    ward             TEXT    NOT NULL DEFAULT '',
                    face_hash        TEXT    NOT NULL DEFAULT '',
                    blockchain_id    TEXT    NOT NULL,
                    has_voted        INTEGER DEFAULT 0,
                    voted_election   INTEGER,
                    tx_hash          TEXT,
                    candidate_id     INTEGER,
                    voted_at         TEXT,
                    registered_at    TEXT    DEFAULT '{ts}'
                );

                CREATE TABLE IF NOT EXISTS election_officers (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    officer_id    TEXT    UNIQUE NOT NULL,
                    name          TEXT    NOT NULL,
                    designation   TEXT    NOT NULL,
                    password_hash TEXT    NOT NULL,
                    registered_at TEXT    DEFAULT '{ts}'
                );

                CREATE TABLE IF NOT EXISTS ward_incharge (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    wic_id        TEXT    UNIQUE NOT NULL,
                    name          TEXT    NOT NULL,
                    ward          TEXT    NOT NULL,
                    district      TEXT    NOT NULL DEFAULT '',
                    state         TEXT    NOT NULL DEFAULT '',
                    password_hash TEXT    NOT NULL,
                    created_by    TEXT    NOT NULL,
                    created_at    TEXT    DEFAULT '{ts}'
                );

                CREATE TABLE IF NOT EXISTS elections (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    name                TEXT    NOT NULL,
                    location_type       TEXT    NOT NULL,
                    location_value      TEXT    NOT NULL,
                    state               TEXT    DEFAULT '',
                    district            TEXT    DEFAULT '',
                    registration_start  TEXT    NOT NULL,
                    registration_end    TEXT    NOT NULL,
                    election_start      TEXT    NOT NULL,
                    election_end        TEXT    NOT NULL,
                    created_by          TEXT    NOT NULL,
                    created_at          TEXT    DEFAULT '{ts}',
                    is_active           INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    election_id  INTEGER NOT NULL,
                    voter_id     TEXT    NOT NULL,
                    name         TEXT    NOT NULL,
                    party        TEXT    NOT NULL,
                    symbol       TEXT    DEFAULT '',
                    added_by     TEXT    NOT NULL,
                    added_at     TEXT    DEFAULT '{ts}',
                    FOREIGN KEY(election_id) REFERENCES elections(id),
                    FOREIGN KEY(voter_id) REFERENCES voters(voter_id)
                );

                CREATE TABLE IF NOT EXISTS fraud_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    voter_id    TEXT,
                    ip_address  TEXT,
                    event_type  TEXT,
                    message     TEXT,
                    severity    TEXT,
                    occurred_at TEXT    DEFAULT '{ts}'
                );

                CREATE TABLE IF NOT EXISTS voter_activity_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    voter_id    TEXT    NOT NULL,
                    name        TEXT    NOT NULL,
                    ward        TEXT    NOT NULL,
                    election_id INTEGER,
                    action      TEXT    NOT NULL,
                    occurred_at TEXT    DEFAULT '{ts}'
                );
            """)

    # ──────────────────────────────── VOTERS ─────────────────────────────────

    def voter_exists(self, voter_id: str) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT id FROM voters WHERE voter_id=?", (voter_id,)
            ).fetchone() is not None

    def register_voter(self, voter_id, name, dob, phone, state, district, ward, face_hash, blockchain_id):
        ts = now_ist()
        with self._conn() as c:
            c.execute(
                """INSERT INTO voters
                   (voter_id,name,dob,phone,state,district,ward,face_hash,blockchain_id,registered_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (voter_id, name, dob, phone, state, district, ward, face_hash, blockchain_id, ts)
            )
        self._log_activity(voter_id, name, ward, None, "REGISTERED")

    def get_voter(self, voter_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM voters WHERE voter_id=?", (voter_id,)).fetchone()
        return dict(row) if row else None

    def remove_voter(self, voter_id: str) -> bool:
        """Remove a voter (election officer only, not if already voted)."""
        with self._conn() as c:
            cur = c.execute("DELETE FROM voters WHERE voter_id=? AND has_voted=0", (voter_id,))
        return cur.rowcount > 0

    def mark_voted(self, voter_id: str, tx_hash: str, candidate_id: int, election_id: int):
        ts = now_ist()
        with self._conn() as c:
            c.execute(
                "UPDATE voters SET has_voted=1,tx_hash=?,candidate_id=?,voted_at=?,voted_election=? WHERE voter_id=?",
                (tx_hash, candidate_id, ts, election_id, voter_id)
            )
        voter = self.get_voter(voter_id)
        if voter:
            self._log_activity(voter_id, voter["name"], voter["ward"], election_id, "VOTED")

    # ── Activity Log ──────────────────────────────────────────────────────────

    def _log_activity(self, voter_id, name, ward, election_id, action):
        ts = now_ist()
        with self._conn() as c:
            c.execute(
                "INSERT INTO voter_activity_log (voter_id,name,ward,election_id,action,occurred_at) VALUES(?,?,?,?,?,?)",
                (voter_id, name, ward, election_id, action, ts)
            )

    def get_activity_log(self, election_id: int = None, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            if election_id:
                rows = c.execute(
                    "SELECT * FROM voter_activity_log WHERE election_id=? ORDER BY occurred_at DESC LIMIT ?",
                    (election_id, limit)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM voter_activity_log ORDER BY occurred_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def export_voter_log_csv(self, election_id: int = None) -> str:
        logs = self.get_activity_log(election_id, limit=10000)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["voter_id","name","ward","election_id","action","occurred_at"])
        writer.writeheader()
        writer.writerows(logs)
        return output.getvalue()

    # ── Ward Stats ────────────────────────────────────────────────────────────

    def get_ward_stats(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT ward,
                       COUNT(*)                     AS registered,
                       SUM(has_voted)               AS voted,
                       ROUND(SUM(has_voted)*100.0/MAX(COUNT(*),1),1) AS pct
                FROM voters GROUP BY ward ORDER BY ward
            """).fetchall()
        return [dict(r) for r in rows]

    def get_ward_voters(self, ward: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT voter_id,name,has_voted,voted_at,registered_at FROM voters WHERE ward=? ORDER BY name",
                (ward,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Election Officers ─────────────────────────────────────────────────────

    def officer_exists(self, officer_id: str) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT id FROM election_officers WHERE officer_id=?", (officer_id,)
            ).fetchone() is not None

    def register_officer(self, officer_id, name, designation, password):
        ph = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as c:
            c.execute(
                "INSERT INTO election_officers (officer_id,name,designation,password_hash) VALUES(?,?,?,?)",
                (officer_id, name, designation, ph)
            )

    def verify_officer(self, officer_id: str, password: str) -> dict | None:
        ph = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM election_officers WHERE officer_id=? AND password_hash=?",
                (officer_id, ph)
            ).fetchone()
        return dict(row) if row else None

    # ── Ward In-Charge ────────────────────────────────────────────────────────

    def wic_exists(self, wic_id: str) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT id FROM ward_incharge WHERE wic_id=?", (wic_id,)
            ).fetchone() is not None

    def create_wic(self, wic_id, name, ward, district, state, password, created_by) -> dict:
        if self.wic_exists(wic_id):
            return {"success": False, "message": f"Ward In-Charge ID '{wic_id}' already exists."}
        ph = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as c:
            c.execute(
                "INSERT INTO ward_incharge (wic_id,name,ward,district,state,password_hash,created_by) VALUES(?,?,?,?,?,?,?)",
                (wic_id, name, ward, district, state, ph, created_by)
            )
        return {"success": True, "message": f"Ward In-Charge '{name}' created for ward '{ward}'."}

    def verify_wic(self, wic_id: str, password: str) -> dict | None:
        ph = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM ward_incharge WHERE wic_id=? AND password_hash=?",
                (wic_id, ph)
            ).fetchone()
        return dict(row) if row else None

    def get_all_wic(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT wic_id,name,ward,district,state,created_by,created_at FROM ward_incharge ORDER BY ward"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_wic(self, wic_id: str) -> bool:
        with self._conn() as c:
            c.execute("DELETE FROM ward_incharge WHERE wic_id=?", (wic_id,))
        return True

    # ── Elections ─────────────────────────────────────────────────────────────

    def create_election(self, name, location_type, location_value, state, district,
                        reg_start, reg_end, election_start, election_end, created_by) -> int:
        ts = now_ist()
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO elections
                   (name,location_type,location_value,state,district,
                    registration_start,registration_end,election_start,election_end,created_by,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (name, location_type, location_value, state, district,
                 reg_start, reg_end, election_start, election_end, created_by, ts)
            )
            return cur.lastrowid

    def get_all_elections(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM elections ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_election(self, election_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM elections WHERE id=?", (election_id,)).fetchone()
        return dict(row) if row else None

    def get_elections_for_voter(self, state: str, district: str, ward: str) -> list[dict]:
        elections = self.get_all_elections()
        result = []
        for e in elections:
            lt = e["location_type"]
            lv = e["location_value"]
            if lt == "national":
                result.append(e)
            elif lt == "state" and e["state"].lower() == state.lower():
                result.append(e)
            elif lt == "district" and e["state"].lower() == state.lower() and e["district"].lower() == district.lower():
                result.append(e)
            elif lt in ("ward", "college") and lv.lower() == ward.lower():
                result.append(e)
        return result

    def is_election_active_now(self, state="", district="", ward="") -> tuple[bool, dict | None]:
        now = datetime.now(IST)
        elections = self.get_elections_for_voter(state, district, ward) if (state or district or ward) else self.get_all_elections()
        for e in elections:
            try:
                if parse_ist(e["election_start"]) <= now <= parse_ist(e["election_end"]):
                    return True, e
            except Exception:
                pass
        return False, None

    def is_any_election_active_now(self) -> tuple[bool, dict | None]:
        now = datetime.now(IST)
        for e in self.get_all_elections():
            try:
                if parse_ist(e["election_start"]) <= now <= parse_ist(e["election_end"]):
                    return True, e
            except Exception:
                pass
        return False, None

    def get_election_status(self, election: dict) -> str:
        now = datetime.now(IST)
        rs = parse_ist(election["registration_start"])
        re = parse_ist(election["registration_end"])
        es = parse_ist(election["election_start"])
        ee = parse_ist(election["election_end"])
        if now < rs:           return "UPCOMING_REGISTRATION"
        elif rs <= now <= re:  return "REGISTRATION_OPEN"
        elif re < now < es:    return "REGISTRATION_CLOSED"
        elif es <= now <= ee:  return "VOTING_ACTIVE"
        else:                  return "ELECTION_ENDED"

    # ── Candidates ────────────────────────────────────────────────────────────

    def add_candidate(self, election_id, voter_id, name, party, symbol, added_by) -> dict:
        voter = self.get_voter(voter_id)
        if not voter:
            return {"success": False, "message": f"Voter ID '{voter_id}' is not registered."}
        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM candidates WHERE election_id=? AND voter_id=?",
                (election_id, voter_id)
            ).fetchone()
            if existing:
                return {"success": False, "message": f"{name} is already a candidate in this election."}
            c.execute(
                "INSERT INTO candidates (election_id,voter_id,name,party,symbol,added_by) VALUES(?,?,?,?,?,?)",
                (election_id, voter_id, name, party, symbol, added_by)
            )
        return {"success": True, "message": f"Candidate {name} added successfully."}

    def get_candidates(self, election_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM voters v WHERE v.candidate_id=c.id AND v.voted_election=?) AS votes FROM candidates c WHERE c.election_id=? ORDER BY c.id",
                (election_id, election_id)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_candidate(self, candidate_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        return dict(row) if row else None

    # ── Analytics ────────────────────────────────────────────────────────────

    def get_officer_analytics(self) -> dict:
        with self._conn() as c:
            total_reg   = c.execute("SELECT COUNT(*) FROM voters").fetchone()[0]
            total_voted = c.execute("SELECT COUNT(*) FROM voters WHERE has_voted=1").fetchone()[0]
            fraud_total = c.execute("SELECT COUNT(*) FROM fraud_log").fetchone()[0]
            fraud_crit  = c.execute("SELECT COUNT(*) FROM fraud_log WHERE severity='CRITICAL'").fetchone()[0]
            ward_rows   = c.execute("""
                SELECT ward, COUNT(*) AS registered, SUM(has_voted) AS voted
                FROM voters GROUP BY ward ORDER BY ward
            """).fetchall()
            hourly = c.execute("""
                SELECT substr(voted_at,12,2)||':00' AS hour, COUNT(*) AS count
                FROM voters WHERE has_voted=1 AND voted_at IS NOT NULL
                GROUP BY hour ORDER BY hour
            """).fetchall()
        return {
            "total_registered":  total_reg,
            "total_voted":       total_voted,
            "participation_pct": round(total_voted*100/max(total_reg,1), 1),
            "fraud": {"total": fraud_total, "critical": fraud_crit},
            "wards": [dict(r) for r in ward_rows],
            "hourly_votes": [dict(r) for r in hourly],
        }

    def get_full_voter_list(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT voter_id,name,state,district,ward,blockchain_id,has_voted,tx_hash,voted_at,registered_at FROM voters ORDER BY ward,name"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_election_results(self, election_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""
                SELECT c.id, c.name, c.party, c.symbol,
                       COUNT(v.id) AS votes
                FROM candidates c
                LEFT JOIN voters v ON v.candidate_id=c.id AND v.voted_election=? AND v.has_voted=1
                WHERE c.election_id=?
                GROUP BY c.id ORDER BY votes DESC
            """, (election_id, election_id)).fetchall()
        return [dict(r) for r in rows]

    def get_election_participation(self, election_id: int) -> dict:
        election = self.get_election(election_id)
        if not election:
            return {}
        with self._conn() as c:
            voted = c.execute(
                "SELECT COUNT(*) FROM voters WHERE voted_election=? AND has_voted=1",
                (election_id,)
            ).fetchone()[0]
        return {"election": election, "voted": voted}

    # ── Fraud Log ─────────────────────────────────────────────────────────────

    def add_fraud_log(self, voter_id, ip, event_type, message, severity):
        ts = now_ist()
        with self._conn() as c:
            c.execute(
                "INSERT INTO fraud_log (voter_id,ip_address,event_type,message,severity,occurred_at) VALUES(?,?,?,?,?,?)",
                (voter_id, ip, event_type, message, severity, ts)
            )

    def get_fraud_log(self, limit=30) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM fraud_log ORDER BY occurred_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_fraud_counts(self) -> dict:
        with self._conn() as c:
            t  = c.execute("SELECT COUNT(*) FROM fraud_log").fetchone()[0]
            cr = c.execute("SELECT COUNT(*) FROM fraud_log WHERE severity='CRITICAL'").fetchone()[0]
            d  = c.execute("SELECT COUNT(*) FROM fraud_log WHERE event_type='DUPLICATE_VOTE'").fetchone()[0]
        return {"total": t, "critical": cr, "duplicates": d}

    def get_election_stats(self, election_id: int) -> dict:
        election = self.get_election(election_id)
        if not election:
            return {}
        lt = election["location_type"]
        lv = election["location_value"]
        st = election.get("state", "")
        di = election.get("district", "")
        with self._conn() as c:
            if lt == "national":
                total = c.execute("SELECT COUNT(*) FROM voters").fetchone()[0]
            elif lt == "state":
                total = c.execute("SELECT COUNT(*) FROM voters WHERE state=?", (st,)).fetchone()[0]
            elif lt == "district":
                total = c.execute("SELECT COUNT(*) FROM voters WHERE state=? AND district=?", (st, di)).fetchone()[0]
            else:
                total = c.execute("SELECT COUNT(*) FROM voters WHERE ward=?", (lv,)).fetchone()[0]
            voted = c.execute(
                "SELECT COUNT(*) FROM voters WHERE voted_election=? AND has_voted=1",
                (election_id,)
            ).fetchone()[0]
            hourly = c.execute("""
                SELECT substr(voted_at,12,2)||':00' AS hour, COUNT(*) AS count
                FROM voters WHERE voted_election=? AND has_voted=1 AND voted_at IS NOT NULL
                GROUP BY hour ORDER BY hour
            """, (election_id,)).fetchall()
        return {
            "election_id": election_id,
            "election_name": election["name"],
            "location_type": lt,
            "location_value": lv,
            "status": self.get_election_status(election),
            "election_start": election["election_start"],
            "election_end": election["election_end"],
            "total_registered": total,
            "total_voted": voted,
            "pct": round(voted * 100 / max(total, 1), 1),
            "hourly": [dict(r) for r in hourly],
        }

    def get_voted_voters_for_election(self, election_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT voter_id, name, ward, voted_at FROM voters WHERE voted_election=? AND has_voted=1 ORDER BY voted_at DESC",
                (election_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_wards(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT ward FROM voters ORDER BY ward").fetchall()
        return [r[0] for r in rows]