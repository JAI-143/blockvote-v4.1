"""
seed.py — Run once after fresh deployment to create the first officer account.
Usage: python seed.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend.database import Database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db = Database(BASE_DIR)

OFFICER_ID  = "admin"
NAME        = "Admin Officer"
DESIGNATION = "Chief Election Officer"
PASSWORD    = "Admin@2024"

if db.officer_exists(OFFICER_ID):
    print(f"Officer '{OFFICER_ID}' already exists. Nothing to do.")
else:
    db.register_officer(OFFICER_ID, NAME, DESIGNATION, PASSWORD)
    print(f"✅ Officer created!")
    print(f"   ID:       {OFFICER_ID}")
    print(f"   Password: {PASSWORD}")
    print(f"   Login at: /officer-login")
    print()
    print("⚠️  Change the password after first login!")
