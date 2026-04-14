# Database Persistence — Solving the Reset Problem

## The Problem
Render's free tier has no persistent disk. Every restart deletes `database/voters.db`.

## Best Free Solutions

### Option 1 — Railway (Free + Persistent) ✅ Recommended
Railway gives free persistent storage. Data survives restarts.

1. Go to **railway.app** → sign up with GitHub
2. New Project → Deploy from GitHub repo
3. Add env vars: `SECRET_KEY=your-random-string`, `PYTHONPATH=/app`
4. Done — database never resets

### Option 2 — Render + Persistent Disk ($1/month)
In Render service → Disks → Add Disk:
- Mount Path: `/opt/render/project/src/database`
- Size: 1 GB → $1/month

### Option 3 — Quick Re-seed Script
Run this after every restart to recreate the officer account:

```python
# seed.py — run once after deploy
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from backend.database import Database
db = Database(os.path.dirname(__file__))
if not db.officer_exists("admin"):
    db.register_officer("admin", "Admin Officer", "Returning Officer", "admin123")
    print("Officer 'admin' created — password: admin123")
```

Run: `python seed.py`
