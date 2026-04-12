# BlockVote v4 — Deployment Guide (Free on Render)

## Overview
- Platform: Render.com (free tier)
- Server: Gunicorn (production Flask)
- Database: SQLite (persisted on Render Disk)
- Biometric: Simulation mode on cloud (face_recognition needs a VPS for real use)

---

## Step 1 — Create a GitHub Account & Repo

1. Go to https://github.com and sign up (free)
2. Click **New repository**
3. Name it `blockvote-v4`
4. Set to **Public**
5. Click **Create repository**

---

## Step 2 — Upload Project to GitHub

### Option A — GitHub Website (no git needed)
1. Open your repo on GitHub
2. Click **uploading an existing file**
3. Drag and drop ALL files from your `blockvote-deploy` folder
4. Click **Commit changes**

### Option B — Git command line
```bash
cd blockvote-deploy
git init
git add .
git commit -m "initial deploy"
git remote add origin https://github.com/YOURUSERNAME/blockvote-v4.git
git push -u origin main
```

---

## Step 3 — Deploy on Render

1. Go to https://render.com → Sign up free
2. Click **New +** → **Web Service**
3. Click **Connect a repository** → select your `blockvote-v4` repo
4. Fill in settings:

| Setting | Value |
|---------|-------|
| Name | blockvote-v4 |
| Region | Singapore (closest to India) |
| Branch | main |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn backend.app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120` |
| Instance Type | **Free** |

5. Click **Advanced** → **Add Environment Variable**:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | any long random string e.g. `blockvote-secret-2024-xyz-abc` |
| `PYTHON_VERSION` | `3.11.9` |

6. Click **Create Web Service**

Render will build and deploy. Takes ~3 minutes.
Your URL will be: `https://blockvote-v4.onrender.com`

---

## Step 4 — Add Persistent Disk (Important!)

Without this, the database resets every time the server restarts.

1. In your Render service → click **Disks** in left sidebar
2. Click **Add Disk**
3. Set:
   - Name: `database`
   - Mount Path: `/opt/render/project/src/database`
   - Size: **1 GB** (free)
4. Click **Save**

The `database/` folder is now persistent across restarts.

---

## Done!

Your app is live at: `https://blockvote-v4.onrender.com`

**Important notes:**
- Free Render servers **sleep after 15 minutes** of inactivity. First request after sleep takes ~30 seconds to wake up.
- To keep it always awake, use https://uptimerobot.com (free) to ping your URL every 10 minutes.
- Officer auth code is still: **ECI2024**
