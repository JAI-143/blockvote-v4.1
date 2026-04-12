# BlockVote v4

## Role Architecture

```
Election Officer (ECI Admin)
    ↓ creates & manages
Ward In-Charge (terminal operator)
    ↓ activates terminal
Voter (authenticates via face at terminal)
```

## URL Map

| URL | Purpose | Who sees it |
|-----|---------|-------------|
| `/` or `/ward-login` | Ward In-Charge login | Public (main entry point) |
| `/ward-terminal` | Voter face-login + voting | WIC only (session protected) |
| `/officer-login` | Election Officer login | Hidden — direct URL only |
| `/officer-portal` | Full management dashboard | Officers only |

## How to Run

```bash
pip install -r requirements.txt
python backend/app.py
```

Open: http://localhost:5000

## Workflow

### Election Officer
1. Go to `/officer-login`
2. Register (first time, needs ECI code: **ECI2024**)
3. In portal: add voters, create ward in-charge accounts, initialize elections, add candidates

### Ward In-Charge
1. Go to `/` (main page)
2. Login with credentials created by Election Officer
3. Terminal activates — ward and live stats shown

### Voter
1. At the activated ward terminal, voter enters their **Voter ID**
2. Opens camera → scans face
3. System verifies face against registered biometric
4. If election is active for their ward → candidate list appears
5. Voter selects candidate → vote recorded on blockchain

## ECI Authorization Code
Default: `ECI2024`
Change via environment variable: `ECI_CODE=your-secret`

## Environment Variables
```
SECRET_KEY=long-random-string     # Flask session key
ECI_CODE=ECI2024                  # Officer registration code
```

## Face Recognition Modes
- **SIMULATION** (default): always passes — for testing without a camera library
- **FACE_RECOGNITION**: real dlib-based face matching (install: `pip install cmake dlib face_recognition`)
