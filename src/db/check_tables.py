from sqlalchemy import inspect
from .database import engine

print("🔍 Checking tables in the connected database...")
inspector = inspect(engine)
tables = inspector.get_table_names()

if tables:
    print("✅ Tables found:")
    for t in tables:
        print("   -", t)
else:
    print("⚠️ No tables found! Looks like models didn’t register.")
