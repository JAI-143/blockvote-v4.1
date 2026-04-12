"""
face_auth.py
Face-recognition biometric authentication using webcam capture.
Uses face_recognition library (dlib-based) with fallback to simulation.

Registration: capture → encode → store
Verification:  capture → encode → compare with stored
"""

import base64, hashlib, json, os, secrets, io
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# Try importing face_recognition (needs: pip install face_recognition)
try:
    import face_recognition
    import numpy as np
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

# Try PIL for image handling
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class FaceAuth:

    def __init__(self, base_dir: str):
        self.base_dir       = base_dir
        self.templates_path = os.path.join(base_dir, "database", "face_templates.json")
        self._templates     = self._load_templates()
        self.mode = "FACE_RECOGNITION" if FACE_RECOGNITION_AVAILABLE else "SIMULATION"
        print(f"[FaceAuth] Mode: {self.mode}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_templates(self) -> dict:
        if os.path.exists(self.templates_path):
            with open(self.templates_path) as f:
                return json.load(f)
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.templates_path), exist_ok=True)
        with open(self.templates_path, "w") as f:
            json.dump(self._templates, f, indent=2)

    # ── Image decoding ────────────────────────────────────────────────────────

    def _decode_image(self, image_b64: str):
        """Decode base64 image to numpy array (for face_recognition) or PIL image."""
        try:
            img_bytes = base64.b64decode(image_b64)
            if FACE_RECOGNITION_AVAILABLE and PIL_AVAILABLE:
                pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                return np.array(pil_img)
            elif PIL_AVAILABLE:
                return Image.open(io.BytesIO(img_bytes)).convert("RGB")
            return img_bytes
        except Exception as e:
            raise ValueError(f"Image decode error: {e}")

    def _image_hash(self, image_b64: str) -> str:
        """Create a stable hash from raw image bytes (fallback)."""
        return hashlib.sha256(base64.b64decode(image_b64)).hexdigest()

    # ── Face encoding (real) ──────────────────────────────────────────────────

    def _get_encoding(self, image_b64: str) -> tuple[bool, list | None, str]:
        """
        Extract face encoding from base64 image.
        Returns (face_found, encoding_list, message)
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return True, None, "simulation"

        try:
            img_array = self._decode_image(image_b64)
            locations = face_recognition.face_locations(img_array)
            if not locations:
                return False, None, "No face detected in image. Please ensure your face is clearly visible."
            if len(locations) > 1:
                return False, None, "Multiple faces detected. Please ensure only one face is in frame."
            encodings = face_recognition.face_encodings(img_array, locations)
            if not encodings:
                return False, None, "Could not extract face features. Please try again with better lighting."
            return True, encodings[0].tolist(), "Face detected successfully."
        except Exception as e:
            return False, None, f"Face processing error: {e}"

    # ── Public API ────────────────────────────────────────────────────────────

    def register(self, voter_id: str, image_b64: str) -> dict:
        """
        Register a voter's face biometric.
        image_b64: base64-encoded JPEG from webcam
        Returns: { success, hash, mode, message }
        """
        if voter_id in self._templates:
            rec = self._templates[voter_id]
            return {
                "success": True, "already_registered": True,
                "hash": rec["hash"], "mode": rec["mode"],
                "message": "Face biometric already registered."
            }

        if not image_b64:
            return {"success": False, "mode": self.mode, "message": "No face image provided. Please capture your face."}

        if FACE_RECOGNITION_AVAILABLE:
            found, encoding, msg = self._get_encoding(image_b64)
            if not found:
                return {"success": False, "mode": "FACE_RECOGNITION", "message": msg}
            face_hash = hashlib.sha256(json.dumps(encoding).encode()).hexdigest()
            self._templates[voter_id] = {
                "hash": face_hash,
                "encoding": encoding,
                "mode": "FACE_RECOGNITION",
                "registered_at": datetime.now(IST).isoformat()
            }
            self._save()
            return {
                "success": True, "hash": face_hash,
                "mode": "FACE_RECOGNITION",
                "message": "Face biometric registered successfully."
            }
        else:
            # Simulation mode — hash the image + a random salt
            salt    = secrets.token_hex(16)
            img_h   = self._image_hash(image_b64)
            face_hash = hashlib.sha256(f"{voter_id}:{img_h}:{salt}".encode()).hexdigest()
            self._templates[voter_id] = {
                "hash": face_hash,
                "salt": salt,
                "img_hash": img_h,
                "mode": "SIMULATION",
                "registered_at": datetime.now(IST).isoformat()
            }
            self._save()
            return {
                "success": True, "hash": face_hash,
                "mode": "SIMULATION",
                "message": "Face captured and registered (demo mode — install face_recognition for real biometric)."
            }

    def verify(self, voter_id: str, stored_hash: str, image_b64: str) -> dict:
        """
        Verify a voter's face against stored biometric.
        Returns: { success, mode, message }
        """
        if voter_id not in self._templates:
            return {"success": False, "mode": "none",
                    "message": "No face record found. Please register first."}

        if not image_b64:
            return {"success": False, "mode": self.mode, "message": "No face image provided."}

        rec  = self._templates[voter_id]
        mode = rec.get("mode", "SIMULATION")

        if mode == "FACE_RECOGNITION" and FACE_RECOGNITION_AVAILABLE:
            found, live_encoding, msg = self._get_encoding(image_b64)
            if not found:
                return {"success": False, "mode": mode, "message": msg}

            stored_encoding = rec.get("encoding")
            if not stored_encoding:
                return {"success": False, "mode": mode, "message": "Stored face data corrupted."}

            import numpy as np
            distance  = face_recognition.face_distance([np.array(stored_encoding)], np.array(live_encoding))[0]
            matched   = distance <= 0.55  # tolerance (lower = stricter)
            return {
                "success": matched, "mode": mode,
                "distance": round(float(distance), 4),
                "message": "Face verified." if matched else f"Face mismatch (distance={distance:.3f}). Please try again."
            }
        else:
            # Simulation: always passes (consistent with fingerprint simulation)
            return {
                "success": True, "mode": "SIMULATION",
                "message": "Face verified (simulation mode)."
            }

    def get_status(self) -> dict:
        return {
            "available": FACE_RECOGNITION_AVAILABLE,
            "mode":      self.mode,
            "registered_count": len(self._templates)
        }
