# BlockVote v4 — Technology Stack

## Frontend
- **HTML5 + CSS3** — Plain HTML files served by Flask. No React/Vue.
- **Vanilla JavaScript** — Uses `fetch()` + `async/await` for API calls.
- **Webcam API** (`getUserMedia`) — Opens camera, captures JPEG frame for biometric.
- **Chart.js** — Hourly voting bar chart in Officer Portal.
- **Font:** Inter (Google Fonts)

## Backend
- **Python 3.11+** — Main language.
- **Flask** — Lightweight web server. Handles page routes + REST API.
- **Gunicorn** — Production WSGI server (used on Render/Railway).
- **Flask-CORS** — Allows browser cross-origin API calls.

## Database
- **SQLite** — File-based database at `database/voters.db`.

| Table | Purpose |
|-------|---------|
| `voters` | Voter details, face hash, voting status |
| `officers` | Election officer accounts |
| `ward_in_charges` | Ward In-Charge accounts |
| `elections` | Election name, location, date windows |
| `candidates` | Candidates per election |
| `voter_activity_log` | Real-time log of every vote |
| `fraud_log` | Duplicate votes, suspicious events |

## Biometric — Face Recognition
- **face_recognition** library (built on dlib / OpenCV)
- Captures 128-number face encoding from webcam image
- Stores SHA-256 hash of encoding — raw image never saved
- **Simulation mode**: if library not installed, biometric auto-passes

## Blockchain
- **Ethereum** (local via Ganache) — each vote = on-chain transaction
- **Web3.py** — Python library to talk to Ethereum node
- **Solidity** smart contract (`VotingContract.sol`) — one vote per voter enforced on-chain
- **Simulation mode**: if Ganache not running, votes stored in `sim_votes.json`

## Authentication
- **Flask sessions** — server-side session cookie for login state
- **Token auth** — `X-Auth-Token` header sent on every API call (fixes HTTPS/Render cookie issues)
- **SHA-256** password hashing for officers and ward in-charges

## Deployment
- **Render.com** (free tier) — auto-deploys on GitHub push
- **IST (UTC+5:30)** — all timestamps stored and displayed in Indian Standard Time
