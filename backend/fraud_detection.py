"""
fraud_detection.py
Rule-based + pattern AI fraud detection for the voting system.
Detects: duplicate votes, IP flooding, rapid-fire attempts.
"""

from datetime import datetime, timedelta
from collections import defaultdict


class FraudDetector:
    """
    Tracks voting patterns and flags suspicious activity.
    All data stored in SQLite via the Database object (injected after init).
    In-memory counters track real-time patterns during a session.
    """

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.db       = None  # injected by app.py after DB is ready

        # In-memory session tracking (fast lookup)
        self._ip_attempts   = defaultdict(list)   # ip  → [timestamps]
        self._voter_attempts = defaultdict(int)    # voter_id → attempt count

    def set_db(self, db):
        """Inject database reference after both objects are created."""
        self.db = db

    # ─── Fraud Checks ─────────────────────────────────────────────────────────

    def check(self, voter_id: str, ip: str) -> dict:
        """
        Run all fraud checks before allowing a voter to proceed.
        Returns {'allowed': bool, 'reason': str}
        """

        # 1. IP rate limit: max 10 different verification attempts per IP per 10 min
        window = datetime.now() - timedelta(minutes=10)
        recent = [t for t in self._ip_attempts[ip] if t > window]
        if len(recent) >= 10:
            self._log("SYSTEM", ip, "IP_FLOOD",
                      f"More than 10 attempts from IP {ip} in 10 minutes", "HIGH")
            return {
                "allowed": False,
                "reason": "🚨 FRAUD ALERT: Too many verification attempts from this device! Please contact an administrator."
            }

        # 2. Record this attempt
        self._ip_attempts[ip].append(datetime.now())
        self._voter_attempts[voter_id] += 1

        # 3. Same voter multiple rapid attempts
        if self._voter_attempts[voter_id] > 5:
            self._log(voter_id, ip, "REPEATED_ATTEMPT",
                      f"Voter {voter_id} attempted verification {self._voter_attempts[voter_id]} times", "HIGH")
            return {
                "allowed": False,
                "reason": "🚨 FRAUD ALERT: Too many verification attempts for this voter ID!"
            }

        return {"allowed": True, "reason": ""}

    def log_duplicate(self, voter_id: str, ip: str):
        """Log a duplicate voting attempt (voter already voted)."""
        self._log(voter_id, ip, "DUPLICATE_VOTE",
                  f"Voter {voter_id} attempted to vote again from IP {ip}", "CRITICAL")

    def log_vote(self, voter_id: str, ip: str):
        """Reset attempt counter on successful vote."""
        self._voter_attempts[voter_id] = 0

    # ─── Stats & Log ──────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        if self.db:
            return self.db.get_fraud_counts()
        return {"total": 0, "critical": 0, "duplicates": 0}

    def get_log(self) -> list:
        if self.db:
            return self.db.get_fraud_log(20)
        return []

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _log(self, voter_id, ip, event_type, message, severity):
        print(f"⚠️  FRAUD [{severity}] {event_type}: {message}")
        if self.db:
            self.db.add_fraud_log(voter_id, ip, event_type, message, severity)
