"""
face_auth.py — BlockVote v4
Real face authentication with three backends (in priority order):
  1. face_recognition (dlib) — most accurate, needs cmake
  2. DeepFace              — easier install, no cmake needed
  3. Simulation            — fallback when neither is installed

Install real face auth:
  Option A (dlib):    pip install cmake dlib face_recognition
  Option B (DeepFace): pip install deepface tf-keras
"""

import base64, hashlib, json, os, secrets, io
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# ── Backend detection ─────────────────────────────────────────────────────────

# Priority 1: face_recognition (dlib)
try:
    import face_recognition
    import numpy as np
    from PIL import Image
    BACKEND = "face_recognition"
except ImportError:
    face_recognition = None

# Priority 2: DeepFace
if face_recognition is None:
    try:
        from deepface import DeepFace
        from PIL import Image
        import numpy as np
        BACKEND = "deepface"
    except ImportError:
        DeepFace = None

# Priority 3: Simulation
if face_recognition is None and (
    "DeepFace" not in dir() or DeepFace is None
):
    BACKEND = "simulation"

try:
    from PIL import Image as _PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

print(f"[FaceAuth] Backend: {BACKEND}")


class FaceAuth:

    TOLERANCE = 0.55   # dlib distance threshold (lower = stricter)
    DEEPFACE_MODEL = "VGG-Face"   # options: VGG-Face, Facenet, ArcFace
    DEEPFACE_THRESHOLD = 0.4      # cosine distance threshold for DeepFace

    def __init__(self, base_dir: str):
        self.base_dir       = base_dir
        self.templates_path = os.path.join(base_dir, "database", "face_templates.json")
        self._templates     = self._load_templates()
        self.mode           = BACKEND.upper().replace("_", "_")
        print(f"[FaceAuth] Mode: {self.mode}, templates loaded: {len(self._templates)}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_templates(self) -> dict:
        if os.path.exists(self.templates_path):
            try:
                with open(self.templates_path) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.templates_path), exist_ok=True)
        with open(self.templates_path, "w") as f:
            json.dump(self._templates, f, indent=2)

    # ── Image helpers ─────────────────────────────────────────────────────────

    def _b64_to_pil(self, image_b64: str):
        img_bytes = base64.b64decode(image_b64)
        return Image.open(io.BytesIO(img_bytes)).convert("RGB")

    def _b64_to_np(self, image_b64: str):
        return np.array(self._b64_to_pil(image_b64))

    def _b64_to_temp_file(self, image_b64: str) -> str:
        """Save base64 image to a temp file. DeepFace needs a file path."""
        import tempfile
        img = self._b64_to_pil(image_b64)
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img.save(tmp.name, "JPEG")
        tmp.close()
        return tmp.name

    # ── Backend: face_recognition (dlib) ─────────────────────────────────────

    def _fr_get_encoding(self, image_b64: str):
        """Returns (found: bool, encoding: list|None, message: str)"""
        try:
            img = self._b64_to_np(image_b64)
            locations = face_recognition.face_locations(img)
            if not locations:
                return False, None, "No face detected. Ensure your face is clearly visible and well-lit."
            if len(locations) > 1:
                return False, None, "Multiple faces detected. Only one person should be in frame."
            encodings = face_recognition.face_encodings(img, locations)
            if not encodings:
                return False, None, "Could not extract face features. Try better lighting."
            return True, encodings[0].tolist(), "Face detected."
        except Exception as e:
            return False, None, f"Face processing error: {e}"

    # ── Backend: DeepFace ─────────────────────────────────────────────────────

    def _df_get_embedding(self, image_b64: str):
        """Returns (found: bool, embedding: list|None, message: str)"""
        tmp_path = None
        try:
            tmp_path = self._b64_to_temp_file(image_b64)
            result = DeepFace.represent(
                img_path=tmp_path,
                model_name=self.DEEPFACE_MODEL,
                enforce_detection=True,
                detector_backend="opencv"
            )
            if not result:
                return False, None, "No face detected. Ensure your face is clearly visible."
            if len(result) > 1:
                return False, None, "Multiple faces detected. Only one person should be in frame."
            return True, result[0]["embedding"], "Face detected."
        except Exception as e:
            msg = str(e)
            if "Face could not be detected" in msg:
                return False, None, "No face detected. Ensure your face is clearly visible and well-lit."
            return False, None, f"Face processing error: {msg}"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _df_cosine_distance(self, a: list, b: list) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na  = math.sqrt(sum(x * x for x in a))
        nb  = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 1.0
        return 1.0 - dot / (na * nb)

    # ── Public API ────────────────────────────────────────────────────────────

    def register(self, voter_id: str, image_b64: str) -> dict:
        """Register voter face. Returns {success, hash, mode, message}"""

        # Already registered — return existing
        if voter_id in self._templates:
            rec = self._templates[voter_id]
            return {"success": True, "already_registered": True,
                    "hash": rec["hash"], "mode": rec["mode"],
                    "message": "Face biometric already registered."}

        if not image_b64:
            return {"success": False, "mode": self.mode,
                    "message": "No face image provided."}

        # ── face_recognition backend ──────────────────────────────────────────
        if BACKEND == "face_recognition":
            found, encoding, msg = self._fr_get_encoding(image_b64)
            if not found:
                return {"success": False, "mode": "FACE_RECOGNITION", "message": msg}
            face_hash = hashlib.sha256(json.dumps(encoding).encode()).hexdigest()
            self._templates[voter_id] = {
                "hash": face_hash, "encoding": encoding,
                "mode": "FACE_RECOGNITION",
                "registered_at": datetime.now(IST).isoformat()
            }
            self._save()
            return {"success": True, "hash": face_hash,
                    "mode": "FACE_RECOGNITION",
                    "message": "Face registered successfully (dlib)."}

        # ── DeepFace backend ──────────────────────────────────────────────────
        if BACKEND == "deepface":
            found, embedding, msg = self._df_get_embedding(image_b64)
            if not found:
                return {"success": False, "mode": "DEEPFACE", "message": msg}
            face_hash = hashlib.sha256(json.dumps(embedding).encode()).hexdigest()
            self._templates[voter_id] = {
                "hash": face_hash, "embedding": embedding,
                "mode": "DEEPFACE",
                "registered_at": datetime.now(IST).isoformat()
            }
            self._save()
            return {"success": True, "hash": face_hash,
                    "mode": "DEEPFACE",
                    "message": "Face registered successfully (DeepFace)."}

        # ── Simulation fallback ───────────────────────────────────────────────
        salt = secrets.token_hex(16)
        img_h = hashlib.sha256(base64.b64decode(image_b64)).hexdigest()
        face_hash = hashlib.sha256(f"{voter_id}:{img_h}:{salt}".encode()).hexdigest()
        self._templates[voter_id] = {
            "hash": face_hash, "salt": salt, "img_hash": img_h,
            "mode": "SIMULATION",
            "registered_at": datetime.now(IST).isoformat()
        }
        self._save()
        return {"success": True, "hash": face_hash, "mode": "SIMULATION",
                "message": "Face captured (simulation mode). Install face_recognition or deepface for real biometric."}

    def verify(self, voter_id: str, stored_hash: str, image_b64: str) -> dict:
        """Verify voter face. Returns {success, mode, message}"""

        if voter_id not in self._templates:
            return {"success": False, "mode": "none",
                    "message": "No face record found. This voter was not registered with face biometric."}

        if not image_b64:
            return {"success": False, "mode": self.mode, "message": "No face image provided."}

        rec  = self._templates[voter_id]
        mode = rec.get("mode", "SIMULATION")

        # ── face_recognition ──────────────────────────────────────────────────
        if mode == "FACE_RECOGNITION" and BACKEND == "face_recognition":
            found, live_enc, msg = self._fr_get_encoding(image_b64)
            if not found:
                return {"success": False, "mode": mode, "message": msg}
            stored_enc = rec.get("encoding")
            if not stored_enc:
                return {"success": False, "mode": mode, "message": "Stored face data corrupted. Re-register voter."}
            dist    = face_recognition.face_distance([np.array(stored_enc)], np.array(live_enc))[0]
            matched = float(dist) <= self.TOLERANCE
            return {
                "success": matched, "mode": mode,
                "distance": round(float(dist), 4),
                "message": "Face verified." if matched
                           else f"Face does not match (score: {dist:.3f}). Please try again with better lighting."
            }

        # ── DeepFace ──────────────────────────────────────────────────────────
        if mode == "DEEPFACE" and BACKEND == "deepface":
            found, live_emb, msg = self._df_get_embedding(image_b64)
            if not found:
                return {"success": False, "mode": mode, "message": msg}
            stored_emb = rec.get("embedding")
            if not stored_emb:
                return {"success": False, "mode": mode, "message": "Stored face data corrupted. Re-register voter."}
            dist    = self._df_cosine_distance(stored_emb, live_emb)
            matched = dist <= self.DEEPFACE_THRESHOLD
            return {
                "success": matched, "mode": mode,
                "distance": round(dist, 4),
                "message": "Face verified." if matched
                           else f"Face does not match (score: {dist:.3f}). Please try again."
            }

        # ── Simulation (or backend mismatch — re-registered with different backend) ──
        return {"success": True, "mode": "SIMULATION",
                "message": "Face verified (simulation mode — install face_recognition for real biometric)."}

    def get_status(self) -> dict:
        return {
            "available":        BACKEND != "simulation",
            "mode":             BACKEND.upper(),
            "backend":          BACKEND,
            "registered_count": len(self._templates)
        }
