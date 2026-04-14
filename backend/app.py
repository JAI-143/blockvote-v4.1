"""
app.py — BlockVote v4
Roles: Election Officer (admin) | Ward In-Charge (terminal) | Voter (face login at terminal)
All timestamps in IST (UTC+5:30).
"""

import os, sys, hashlib, secrets
from functools import wraps
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from flask import Flask, request, jsonify, send_from_directory, session, Response
from flask_cors import CORS

from backend.database       import now_ist, parse_ist
from backend.blockchain_utils import BlockchainUtils
from backend.fraud_detection  import FraudDetector
from biometric.face_auth      import FaceAuth

IST = timezone(timedelta(hours=5, minutes=30))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True)

db         = Database(BASE_DIR)
blockchain = BlockchainUtils(BASE_DIR)
fraud      = FraudDetector(BASE_DIR)
face       = FaceAuth(BASE_DIR)
fraud.set_db(db)

FRONTEND = os.path.join(BASE_DIR, "frontend")

# ── Guards ────────────────────────────────────────────────────────────────────

def officer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("officer_id"):
            return jsonify({"success": False, "message": "Election officer login required."}), 401
        return f(*args, **kwargs)
    return decorated

def wic_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("wic_id"):
            return jsonify({"success": False, "message": "Ward In-Charge login required."}), 401
        return f(*args, **kwargs)
    return decorated

def election_not_active(f):
    """Block if the VOTER'S specific ward has an active election.
    For non-voter endpoints (init-election), block if ANY election is active."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # For voter add/remove, check only the target voter's ward
        if request.method in ("POST", "DELETE") and request.is_json:
            d = request.get_json(silent=True) or {}
            ward     = d.get("ward", "").strip()
            state    = d.get("state", "").strip()
            district = d.get("district", "").strip()
            if ward and state and district:
                active, election = db.is_election_active_now(state, district, ward)
            else:
                active, election = db.is_any_election_active_now()
        else:
            active, election = db.is_any_election_active_now()
        if active:
            return jsonify({
                "success": False,
                "message": f"Action blocked: Election '{election['name']}' is currently active in this ward.",
                "election": election["name"]
            }), 403
        return f(*args, **kwargs)
    return decorated

# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def home():           return send_from_directory(FRONTEND, "index.html")

@app.route("/register")
def register_page():  return send_from_directory(FRONTEND, "register.html")

# Ward In-Charge terminal (public entry point)
@app.route("/ward-login")
def ward_login():     return send_from_directory(FRONTEND, "ward-login.html")

@app.route("/ward-terminal")
def ward_terminal():  return send_from_directory(FRONTEND, "ward-terminal.html")

# Election Officer (hidden, accessible via direct URL)
@app.route("/officer-login")
def officer_login():  return send_from_directory(FRONTEND, "officer-login.html")

@app.route("/officer-portal")
def officer_portal(): return send_from_directory(FRONTEND, "officer-portal.html")

@app.route("/static/<path:fn>")
def static_f(fn):     return send_from_directory(os.path.join(BASE_DIR, "static"), fn)

# ── API: Time ─────────────────────────────────────────────────────────────────

@app.route("/api/time")
def api_time():
    now = datetime.now(IST)
    return jsonify({
        "success": True,
        "ist":     now.strftime("%Y-%m-%dT%H:%M:%S"),
        "display": now.strftime("%d %b %Y, %I:%M:%S %p IST"),
        "ts":      now.timestamp()
    })

@app.route("/api/biometric/status")
def api_biometric_status():
    return jsonify({"success": True, **face.get_status()})

# ── API: Ward In-Charge Login / Logout ───────────────────────────────────────

@app.route("/api/wic/login", methods=["POST"])
def api_wic_login():
    d      = request.get_json() or {}
    wic_id = d.get("wic_id", "").strip()
    pw     = d.get("password", "").strip()
    wic    = db.verify_wic(wic_id, pw)
    if not wic:
        return jsonify({"success": False, "message": "Invalid ID or password."})
    session["wic_id"]   = wic_id
    session["wic_ward"] = wic["ward"]
    session["wic_name"] = wic["name"]
    active, election    = db.is_election_active_now(wic["state"], wic["district"], wic["ward"])
    return jsonify({
        "success":          True,
        "wic_id":           wic["wic_id"],
        "name":             wic["name"],
        "ward":             wic["ward"],
        "district":         wic["district"],
        "state":            wic["state"],
        "election_active":  active,
        "active_election":  election["name"] if election else None,
        "election_id":      election["id"]   if election else None,
    })

@app.route("/api/wic/logout", methods=["POST"])
def api_wic_logout():
    session.pop("wic_id",   None)
    session.pop("wic_ward", None)
    session.pop("wic_name", None)
    return jsonify({"success": True})

@app.route("/api/wic/status")
def api_wic_status():
    """Check current ward in-charge session."""
    if not session.get("wic_id"):
        return jsonify({"success": False, "logged_in": False})
    return jsonify({
        "success":   True,
        "logged_in": True,
        "wic_id":    session["wic_id"],
        "ward":      session.get("wic_ward"),
        "name":      session.get("wic_name"),
    })

# ── API: Voter face-login at ward terminal ────────────────────────────────────

@app.route("/api/voter/verify", methods=["POST"])
@wic_required
def api_voter_verify():
    """Voter enters ID + face scan at the ward terminal to authenticate."""
    d        = request.get_json() or {}
    voter_id = d.get("voter_id", "").strip()
    face_b64 = d.get("face_image", "").strip()
    ip       = request.remote_addr
    ward     = session.get("wic_ward", "")

    fc = fraud.check(voter_id, ip)
    if not fc["allowed"]:
        return jsonify({"success": False, "message": fc["reason"]})

    voter = db.get_voter(voter_id)
    if not voter:
        return jsonify({"success": False, "message": "Voter ID not found. Please contact your election officer."})

    # Ward check — voter must belong to this ward terminal
    if voter["ward"].lower() != ward.lower():
        return jsonify({"success": False, "message": f"This voter is not registered in ward '{ward}'. Wrong terminal."})

    if voter["has_voted"]:
        fraud.log_duplicate(voter_id, ip)
        return jsonify({"success": False, "message": "DUPLICATE: This voter has already cast their vote."})

    if not face_b64:
        return jsonify({"success": False, "message": "Face image required."})

    fp = face.verify(voter_id, voter["face_hash"], face_b64)
    if not fp["success"]:
        return jsonify({"success": False, "message": f"Face verification failed: {fp['message']}"})

    # Check active election for this ward
    active, election = db.is_election_active_now(voter["state"], voter["district"], voter["ward"])
    if not active:
        elections = db.get_elections_for_voter(voter["state"], voter["district"], voter["ward"])
        msg = "No active election in your ward right now."
        for e in elections:
            status = db.get_election_status(e)
            if status == "REGISTRATION_OPEN":
                msg = f"Registration is open for '{e['name']}'. Voting starts {e['election_start']} IST."
        return jsonify({"success": False, "message": msg})

    candidates = db.get_candidates(election["id"])
    public_candidates = [{k: v for k, v in c.items() if k != "votes"} for c in candidates]

    return jsonify({
        "success":   True,
        "voter": {
            "voter_id":      voter["voter_id"],
            "name":          voter["name"],
            "ward":          voter["ward"],
            "blockchain_id": voter["blockchain_id"][:24] + "...",
        },
        "election": {
            "id":           election["id"],
            "name":         election["name"],
            "election_end": election["election_end"],
        },
        "candidates":  public_candidates,
        "face_mode":   fp["mode"],
        "current_ist": now_ist()
    })

# ── API: Cast Vote (from ward terminal) ──────────────────────────────────────

@app.route("/api/voter/vote", methods=["POST"])
@wic_required
def api_voter_vote():
    d            = request.get_json() or {}
    voter_id     = d.get("voter_id", "").strip()
    candidate_id = int(d.get("candidate_id", 0))
    election_id  = int(d.get("election_id", 0))
    ip           = request.remote_addr

    voter = db.get_voter(voter_id)
    if not voter:
        return jsonify({"success": False, "message": "Voter not found."})
    if voter["has_voted"]:
        return jsonify({"success": False, "message": "Already voted!"})

    # Ward must match session
    if voter["ward"].lower() != session.get("wic_ward", "").lower():
        return jsonify({"success": False, "message": "Ward mismatch."})

    active, election = db.is_election_active_now(voter["state"], voter["district"], voter["ward"])
    if not active or (election and election["id"] != election_id):
        return jsonify({"success": False, "message": "No active election or election ID mismatch."})

    candidate = db.get_candidate(candidate_id)
    if not candidate or candidate["election_id"] != election_id:
        return jsonify({"success": False, "message": "Invalid candidate."})

    voter_hash = hashlib.sha256(voter["blockchain_id"].encode()).hexdigest()
    tx_hash    = blockchain.cast_vote(voter_hash, candidate_id)
    db.mark_voted(voter_id, tx_hash, candidate_id, election_id)
    fraud.log_vote(voter_id, ip)

    return jsonify({
        "success":          True,
        "message":          "Vote recorded on the blockchain.",
        "transaction_hash": tx_hash[:30] + "...",
        "blockchain_mode":  blockchain.get_mode(),
        "voted_at_ist":     now_ist(),
    })

# ── API: Ward Terminal — live stats for WIC ────────────────────────────────

@app.route("/api/wic/stats")
@wic_required
def api_wic_stats():
    ward = session.get("wic_ward", "")
    voters = db.get_ward_voters(ward)
    total = len(voters)
    voted = sum(1 for v in voters if v["has_voted"])
    log = db.get_activity_log(limit=50)
    ward_log = [l for l in log if l["ward"] == ward][:20]
    return jsonify({
        "success":    True,
        "ward":       ward,
        "total":      total,
        "voted":      voted,
        "remaining":  total - voted,
        "pct":        round(voted * 100 / max(total, 1), 1),
        "log":        ward_log,
        "current_ist": now_ist()
    })

# ── API: Election Officer Registration ────────────────────────────────────────


# ── API: Public Voter Self-Registration ───────────────────────────────────────
@app.route("/api/register/voter", methods=["POST"])
def api_register_voter_public():
    """Voter self-registers via the public registration page."""
    d        = request.get_json() or {}
    voter_id = d.get("voter_id", "").strip()
    name     = d.get("name", "").strip()
    dob      = d.get("dob", "").strip()
    phone    = d.get("phone", "").strip()
    state    = d.get("state", "").strip()
    district = d.get("district", "").strip()
    ward     = d.get("ward", "").strip()
    face_b64 = d.get("face_image", "").strip()

    if not all([voter_id, name, state, district, ward]):
        return jsonify({"success": False, "message": "Voter ID, name, state, district and ward are required."})
    if db.voter_exists(voter_id):
        return jsonify({"success": False, "message": f"Voter ID '{voter_id}' is already registered."})
    if not face_b64:
        return jsonify({"success": False, "message": "Face image is required for biometric registration."})

    fp = face.register(voter_id, face_b64)
    if not fp["success"]:
        return jsonify({"success": False, "message": fp["message"]})

    blockchain_id = hashlib.sha256(
        f"{voter_id}:{name}:{os.urandom(8).hex()}".encode()
    ).hexdigest()

    db.register_voter(voter_id, name, dob, phone, state, district, ward, fp["hash"], blockchain_id)

    # Get elections for this voter location
    elections = db.get_elections_for_voter(state, district, ward) if hasattr(db, "get_elections_for_voter") else []
    election_info = []
    for e in elections:
        status = db.get_election_status(e) if hasattr(db, "get_election_status") else "UNKNOWN"
        election_info.append({
            "id": e["id"], "name": e["name"], "status": status,
            "election_start": e.get("election_start",""),
            "election_end":   e.get("election_end",""),
        })

    return jsonify({
        "success":       True,
        "message":       f"{name} registered successfully.",
        "blockchain_id": blockchain_id[:24] + "...",
        "face_mode":     fp["mode"],
        "elections":     election_info,
    })

@app.route("/api/officer/register", methods=["POST"])
def api_register_officer():
    d           = request.get_json() or {}
    officer_id  = d.get("officer_id", "").strip()
    name        = d.get("name", "").strip()
    designation = d.get("designation", "").strip()
    password    = d.get("password", "").strip()
    secret_code = d.get("secret_code", "").strip()

    if secret_code != os.environ.get("ECI_CODE", "ECI2024"):
        return jsonify({"success": False, "message": "Invalid ECI authorization code."})
    if not all([officer_id, name, designation, password]):
        return jsonify({"success": False, "message": "All fields required."})
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."})
    if db.officer_exists(officer_id):
        return jsonify({"success": False, "message": f"Officer ID '{officer_id}' already exists."})

    db.register_officer(officer_id, name, designation, password)
    return jsonify({"success": True, "message": f"Officer '{name}' registered."})

# ── API: Election Officer Login / Logout ──────────────────────────────────────

@app.route("/api/officer/login", methods=["POST"])
def api_officer_login():
    d          = request.get_json() or {}
    officer_id = d.get("officer_id", "").strip()
    password   = d.get("password", "").strip()
    officer    = db.verify_officer(officer_id, password)
    if not officer:
        return jsonify({"success": False, "message": "Invalid Officer ID or password."})
    session["officer_id"] = officer_id
    active, active_election = db.is_any_election_active_now()
    return jsonify({
        "success":         True,
        "officer_id":      officer["officer_id"],
        "name":            officer["name"],
        "designation":     officer["designation"],
        "election_active": active,
        "active_election": active_election["name"] if active_election else None,
    })

@app.route("/api/officer/logout", methods=["POST"])
def api_officer_logout():
    session.pop("officer_id", None)
    return jsonify({"success": True})

# ── API: Officer — Manage Ward In-Charge ─────────────────────────────────────

@app.route("/api/officer/wic", methods=["GET"])
@officer_required
def api_list_wic():
    return jsonify({"success": True, "wic_list": db.get_all_wic()})

@app.route("/api/officer/wic", methods=["POST"])
@officer_required
def api_create_wic():
    d        = request.get_json() or {}
    wic_id   = d.get("wic_id", "").strip()
    name     = d.get("name", "").strip()
    ward     = d.get("ward", "").strip()
    district = d.get("district", "").strip()
    state    = d.get("state", "").strip()
    password = d.get("password", "").strip()

    if not all([wic_id, name, ward, district, state, password]):
        return jsonify({"success": False, "message": "All fields required."})
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."})

    result = db.create_wic(wic_id, name, ward, district, state, password, session["officer_id"])
    return jsonify(result)

@app.route("/api/officer/wic/<wic_id>", methods=["DELETE"])
@officer_required
def api_delete_wic(wic_id):
    db.delete_wic(wic_id)
    return jsonify({"success": True, "message": f"Ward In-Charge '{wic_id}' removed."})

# ── API: Officer — Manage Voters ──────────────────────────────────────────────

@app.route("/api/officer/voters", methods=["GET"])
@officer_required
def api_officer_voters():
    return jsonify({"success": True, "voters": db.get_full_voter_list()})

@app.route("/api/officer/voter", methods=["POST"])
@officer_required
@election_not_active
def api_officer_add_voter():
    """Officer manually adds a voter (no face capture — voter does that later at terminal)."""
    d        = request.get_json() or {}
    voter_id = d.get("voter_id", "").strip()
    name     = d.get("name", "").strip()
    dob      = d.get("dob", "").strip()
    phone    = d.get("phone", "").strip()
    state    = d.get("state", "").strip()
    district = d.get("district", "").strip()
    ward     = d.get("ward", "").strip()
    face_b64 = d.get("face_image", "").strip()

    if not all([voter_id, name, state, district, ward]):
        return jsonify({"success": False, "message": "Voter ID, name, state, district, and ward are required."})
    if db.voter_exists(voter_id):
        return jsonify({"success": False, "message": f"Voter ID '{voter_id}' already registered."})
    if not face_b64:
        return jsonify({"success": False, "message": "Face image is required."})

    fp = face.register(voter_id, face_b64)
    if not fp["success"]:
        return jsonify({"success": False, "message": fp["message"]})

    blockchain_id = hashlib.sha256(
        f"{voter_id}:{name}:{os.urandom(8).hex()}".encode()
    ).hexdigest()

    db.register_voter(voter_id, name, dob, phone, state, district, ward, fp["hash"], blockchain_id)
    return jsonify({
        "success":       True,
        "message":       f"Voter '{name}' (ID: {voter_id}) added successfully.",
        "blockchain_id": blockchain_id[:24] + "...",
        "face_mode":     fp["mode"],
    })

@app.route("/api/officer/voter/<voter_id>", methods=["DELETE"])
@officer_required
def api_officer_remove_voter(voter_id):
    voter = db.get_voter(voter_id)
    if not voter:
        return jsonify({"success": False, "message": "Voter not found."})
    if voter["has_voted"]:
        return jsonify({"success": False, "message": "Cannot remove a voter who has already voted."})
    active, election = db.is_election_active_now(voter["state"], voter["district"], voter["ward"])
    if active:
        return jsonify({"success": False, "message": f"Cannot remove: Election '{election['name']}' active in this ward."}), 403
    db.remove_voter(voter_id)
    return jsonify({"success": True, "message": f"Voter '{voter_id}' removed successfully."})

# ── API: Officer — Elections & Candidates ─────────────────────────────────────

@app.route("/api/officer/elections", methods=["GET"])
@officer_required
def api_officer_elections():
    elections = db.get_all_elections()
    enriched = []
    for e in elections:
        e["status"]      = db.get_election_status(e)
        e["candidates"]  = db.get_candidates(e["id"])
        e["results"]     = db.get_election_results(e["id"])
        part = db.get_election_participation(e["id"])
        e["voted_count"] = part.get("voted", 0)
        enriched.append(e)
    active, _ = db.is_any_election_active_now()
    return jsonify({
        "success":    True,
        "elections":  enriched,
        "any_active": active,
        "current_ist": now_ist()
    })

@app.route("/api/officer/init-election", methods=["POST"])
@officer_required
def api_init_election():
    d              = request.get_json() or {}
    name           = d.get("name", "").strip()
    location_type  = d.get("location_type", "").strip()
    location_value = d.get("location_value", "").strip()
    state          = d.get("state", "").strip()
    district       = d.get("district", "").strip()
    reg_start      = d.get("registration_start", "").strip()
    reg_end        = d.get("registration_end", "").strip()
    elec_start     = d.get("election_start", "").strip()
    elec_end       = d.get("election_end", "").strip()

    if not all([name, location_type, reg_start, reg_end, elec_start, elec_end]):
        return jsonify({"success": False, "message": "All fields including dates are required."})

    valid_types = {"national", "state", "district", "ward", "college"}
    if location_type not in valid_types:
        return jsonify({"success": False, "message": f"Invalid location type. Choose: {', '.join(valid_types)}"})

    try:
        rs = parse_ist(reg_start); re = parse_ist(reg_end)
        es = parse_ist(elec_start); ee = parse_ist(elec_end)
    except Exception:
        return jsonify({"success": False, "message": "Invalid date format. Use YYYY-MM-DDTHH:MM:SS"})

    if rs >= re: return jsonify({"success": False, "message": "Registration end must be after start."})
    if es >= ee: return jsonify({"success": False, "message": "Election end must be after start."})
    if re >= es: return jsonify({"success": False, "message": "Election must start after registration ends."})

    election_id = db.create_election(
        name, location_type, location_value, state, district,
        reg_start, reg_end, elec_start, elec_end, session["officer_id"]
    )
    return jsonify({"success": True, "message": f"Election '{name}' initialized.", "election_id": election_id})

@app.route("/api/officer/add-candidate", methods=["POST"])
@officer_required
def api_add_candidate():
    active, active_election = db.is_any_election_active_now()
    if active:
        return jsonify({"success": False, "message": f"Cannot add candidates during active election: '{active_election['name']}'."}), 403

    d           = request.get_json() or {}
    election_id = int(d.get("election_id", 0))
    voter_id    = d.get("voter_id", "").strip()
    party       = d.get("party", "").strip()
    symbol      = d.get("symbol", "").strip()
    face_b64    = d.get("face_image", "").strip()

    if not all([election_id, voter_id, party]):
        return jsonify({"success": False, "message": "Election ID, voter ID, and party are required."})

    election = db.get_election(election_id)
    if not election:
        return jsonify({"success": False, "message": "Election not found."})

    status = db.get_election_status(election)
    if status in ("VOTING_ACTIVE", "ELECTION_ENDED"):
        return jsonify({"success": False, "message": f"Cannot add candidates when election is {status}."})

    voter = db.get_voter(voter_id)
    if not voter:
        return jsonify({"success": False, "message": f"Voter ID '{voter_id}' is not registered."})

    if face_b64:
        verify = face.verify(voter_id, voter["face_hash"], face_b64)
        if not verify["success"]:
            return jsonify({"success": False, "message": f"Biometric failed: {verify['message']}"})

    result = db.add_candidate(election_id, voter_id, voter["name"], party, symbol, session["officer_id"])
    return jsonify(result)

# ── API: Officer — Analytics ──────────────────────────────────────────────────

@app.route("/api/officer/analytics")
@officer_required
def api_officer_analytics():
    analytics  = db.get_officer_analytics()
    fraud_log  = db.get_fraud_log(50)
    elections  = db.get_all_elections()
    active, _  = db.is_any_election_active_now()
    wic_list   = db.get_all_wic()

    for e in elections:
        e["status"]      = db.get_election_status(e)
        e["candidates"]  = db.get_candidates(e["id"])
        e["results"]     = db.get_election_results(e["id"])
        part = db.get_election_participation(e["id"])
        e["voted_count"] = part.get("voted", 0)

    return jsonify({
        "success":         True,
        "analytics":       analytics,
        "fraud_log":       fraud_log,
        "elections":       elections,
        "wic_list":        wic_list,
        "voter_list":      db.get_full_voter_list(),
        "blockchain_mode": blockchain.get_mode(),
        "election_active": active,
        "current_ist":     now_ist()
    })

# ── API: Candidates public ────────────────────────────────────────────────────

@app.route("/api/candidates/<int:election_id>")
def api_candidates(election_id):
    election = db.get_election(election_id)
    if not election:
        return jsonify({"success": False, "message": "Election not found."})
    candidates = db.get_candidates(election_id)
    public = [{k: v for k, v in c.items() if k != "votes"} for c in candidates]
    return jsonify({
        "success":    True,
        "candidates": public,
        "election": {
            "id":     election["id"],
            "name":   election["name"],
            "status": db.get_election_status(election),
        }
    })

# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║         BLOCKVOTE v4 — ELECTION MANAGEMENT SYSTEM        ║
╠══════════════════════════════════════════════════════════╣
║  Ward Terminal  →  http://localhost:5000                 ║
║  Ward Login     →  http://localhost:5000/ward-login      ║
║  Officer Login  →  http://localhost:5000/officer-login   ║
║  Officer Portal →  http://localhost:5000/officer-portal  ║
╠══════════════════════════════════════════════════════════╣
║  ECI Auth Code: ECI2024   |   All times: IST (UTC+5:30)  ║
╚══════════════════════════════════════════════════════════╝
""")
    app.run(debug=True, port=5000, use_reloader=False)

# ── API: Public — ward list & ward elections ──────────────────────────────────

@app.route("/api/public/wards")
def api_public_wards():
    wards = db.get_wards()
    return jsonify({"success": True, "wards": wards})

@app.route("/api/public/ward/<ward>/elections")
def api_public_ward_elections(ward):
    # Return elections relevant to this ward
    voters_sample = None
    with db._conn() as c:
        row = c.execute("SELECT state, district FROM voters WHERE ward=? LIMIT 1", (ward,)).fetchone()
        if row:
            voters_sample = dict(row)
    if not voters_sample:
        return jsonify({"success": False, "message": "Ward not found or has no voters."})
    elections = db.get_elections_for_voter(voters_sample["state"], voters_sample["district"], ward)
    enriched = []
    for e in elections:
        status = db.get_election_status(e)
        part   = db.get_election_participation(e["id"])
        enriched.append({
            "id":           e["id"],
            "name":         e["name"],
            "location_type": e["location_type"],
            "status":       status,
            "election_start": e["election_start"],
            "election_end":   e["election_end"],
            "voted_count":  part.get("voted", 0),
        })
    return jsonify({"success": True, "ward": ward, "elections": enriched})

@app.route("/api/public/election/<int:election_id>/stats")
def api_public_election_stats(election_id):
    stats = db.get_election_stats(election_id)
    if not stats:
        return jsonify({"success": False, "message": "Election not found."})
    # Public: no candidate vote counts, no voter identity
    return jsonify({"success": True, **stats})

# ── API: Officer — election detail with voter log ─────────────────────────────

@app.route("/api/officer/election/<int:election_id>/detail")
@officer_required
def api_officer_election_detail(election_id):
    stats  = db.get_election_stats(election_id)
    if not stats:
        return jsonify({"success": False, "message": "Election not found."})
    voters = db.get_voted_voters_for_election(election_id)
    # Results only shown after election ends, and never show who voted for whom
    election = db.get_election(election_id)
    results  = []
    if db.get_election_status(election) == "ELECTION_ENDED":
        raw = db.get_election_results(election_id)
        # Strip enough to show totals without linking to individual voters
        results = [{"name": r["name"], "party": r["party"], "symbol": r["symbol"], "votes": r["votes"]} for r in raw]
    return jsonify({
        "success": True,
        **stats,
        "voted_voters": voters,  # voter_id, name, ward, voted_at only — no candidate
        "results": results,
    })
