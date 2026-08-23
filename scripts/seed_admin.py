"""
seed_admin.py — Run once to create the initial admin user.

Usage:
    python seed_admin.py

Reads ADMIN_PASSWORD from environment (default: OkieDokie@123).
Username is always: odadmin
Safe to re-run — skips creation if user already exists.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from db.db import SessionLocal, init_db
from db.models import User
from api.auth import get_password_hash

ADMIN_USERNAME = "odadmin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "OkieDokie@123")


def seed():
    print("Initializing database...")
    init_db()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if existing:
            print(f"Admin user '{ADMIN_USERNAME}' already exists — skipping.")
            return

        admin = User(
            username=ADMIN_USERNAME,
            password_hash=get_password_hash(ADMIN_PASSWORD),
            role="admin",
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin user created: username='{ADMIN_USERNAME}'")
        print("   Password is set from ADMIN_PASSWORD env var.")
        print("   Change it by updating ADMIN_PASSWORD and re-running this script.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
