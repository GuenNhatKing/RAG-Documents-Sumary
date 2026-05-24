# addAdmin.py
"""Script to insert privileged users (admin, can_bo, quan_ly) into the database.
Run this once after the tables are created.
"""

from app.database import SessionLocal
from app.models import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], default="pbkdf2_sha256", deprecated="auto")

def add_user(username: str, password: str, role: str):
    db = SessionLocal()
    if db.query(User).filter(User.username == username).first():
        print(f"{username} already exists")
        db.close()
        return
    hashed = pwd_context.hash(password[:72])
    user = User(username=username, hashed_password=hashed, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    print(f"Created {role} user: {username}")

if __name__ == "__main__":
    add_user("alice", "secret", "admin")
    add_user("david", "secret", "can_bo")
    add_user("carol", "secret", "quan_ly")
