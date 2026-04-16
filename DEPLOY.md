# BlockVote v4 — Deployment Guide

## Why Data Gets Erased on Render

Render's **free tier has no persistent disk**. Every time the server restarts
(which happens after 15 minutes of inactivity), the filesystem resets.
Your `database/voters.db` is deleted. This is a Render limitation, not a bug
in the code.

---

## Best Free Deployment Options

### Option 1 — Oracle Cloud Always Free ✅ RECOMMENDED
**Completely free forever. Real VPS. Real face auth. Data never erases.**

#### Step 1: Create Oracle Cloud account
1. Go to https://cloud.oracle.com and sign up (needs a credit card for verification, but you are NOT charged)
2. Choose region: **Mumbai (ap-mumbai-1)** — closest to India
3. After signup, go to **Compute → Instances → Create Instance**
4. Choose:
   - Shape: **VM.Standard.E2.1.Micro** (Always Free)
   - OS: **Ubuntu 22.04**
   - Add your SSH key (or download the one Oracle generates)
5. Click **Create** — wait 2 minutes

#### Step 2: Connect to your server
```bash
# On Windows: use PuTTY or Windows Terminal
ssh ubuntu@YOUR_SERVER_IP
```

#### Step 3: Install everything
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python, pip, nginx
sudo apt install python3-pip python3-venv nginx -y

# Clone/upload your project
# Option A — upload via FileZilla (SFTP to YOUR_SERVER_IP, user: ubuntu)
# Option B — use GitHub
sudo apt install git -y
git clone https://github.com/YOURUSERNAME/blockvote-v4.git
cd blockvote-v4

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install flask flask-cors requests numpy Pillow gunicorn

# Install REAL face recognition (Option A — dlib)
sudo apt install cmake libboost-all-dev -y
pip install cmake dlib face_recognition

# OR install DeepFace (Option B — easier)
# pip install deepface tf-keras

# Create first officer account
python seed.py

# Test the app
python backend/app.py
# Open browser: http://YOUR_SERVER_IP:5000
# If it works, Ctrl+C and continue to step 4
```

#### Step 4: Run as a background service (stays on forever)
```bash
# Create systemd service
sudo nano /etc/systemd/system/blockvote.service
```

Paste this (replace YOUR_USERNAME and path):
```ini
[Unit]
Description=BlockVote v4
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/blockvote-v4
Environment="PATH=/home/ubuntu/blockvote-v4/venv/bin"
Environment="SECRET_KEY=your-long-random-secret-key-here-change-this"
ExecStart=/home/ubuntu/blockvote-v4/venv/bin/gunicorn backend.app:app --bind 127.0.0.1:5000 --workers 2 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable blockvote
sudo systemctl start blockvote
sudo systemctl status blockvote  # should say "active (running)"
```

#### Step 5: Set up Nginx (so you get a clean URL on port 80)
```bash
sudo nano /etc/nginx/sites-available/blockvote
```

Paste:
```nginx
server {
    listen 80;
    server_name YOUR_SERVER_IP;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/blockvote /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Open port 80 in Oracle Cloud firewall:
# Go to Oracle Cloud → Networking → Virtual Cloud Networks
# → Security Lists → Ingress Rules → Add Rule
# Protocol: TCP, Port: 80, Source: 0.0.0.0/0
```

#### Step 6: Open in browser
```
http://YOUR_SERVER_IP
```

Data persists forever. Face auth works. Never sleeps. **Cost: ₹0.**

---

### Option 2 — Railway (Easy but limited free credits)

1. Push code to GitHub
2. Go to railway.app → Deploy from GitHub
3. Add env vars: `SECRET_KEY=your-secret`, `PYTHONPATH=/app`
4. After deploy, open Shell tab and run: `python seed.py`

**Note:** Railway gives $5 free credit (~500 hours). After that you need to pay.
Face recognition will NOT work (cmake fails on Railway).

---

### Option 3 — Your own PC + ngrok (for demos/testing)

```bash
# Run locally
python backend/app.py

# In another terminal — make it publicly accessible
# Install ngrok: https://ngrok.com
ngrok http 5000

# Share the ngrok URL with anyone
# Data persists as long as your PC is on
# Real face auth works (install dlib on your PC)
```

---

## Face Authentication — Quick Install

### On Linux/Mac:
```bash
sudo apt install cmake libboost-all-dev -y    # Linux only
pip install cmake dlib face_recognition
# Restart the server — it auto-detects and switches to real mode
```

### On Windows:
1. Download and install **Visual C++ Build Tools** from:
   https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. Select "Desktop development with C++" during install
3. Open a new terminal (important — close old one):
```bash
pip install cmake
pip install dlib
pip install face_recognition
```
4. Restart the server — biometric mode shows "🟢 Real Face ID"

### DeepFace (easier, no cmake):
```bash
pip install deepface tf-keras
# Restart the server — auto-switches to DeepFace mode
```

---

## First-Time Setup After Deploy

Always run this once after a fresh install:
```bash
python seed.py
```
This creates the default officer account:
- **ID:** admin
- **Password:** Admin@2024
- **Login at:** /officer-login

Change the password after first login.
