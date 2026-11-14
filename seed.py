"""Run:  python seed.py   -> creates tables and demo data."""
from app.database import Base, SessionLocal, engine
import app.models  # noqa: F401
from app.seed import DEMO_ACCOUNTS, seed_demo

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    print("Demo data created." if seed_demo(db) else "Demo data already exists.")
print("\nDemo accounts:")
for name, email, password, role in DEMO_ACCOUNTS:
    print(f"  {role:9} {email}  /  {password}")
