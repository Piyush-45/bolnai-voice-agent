import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DB_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL not found in environment variables!")

# Create engine
engine = create_engine(DATABASE_URL, echo=True)

# Base declarative class
Base = declarative_base()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database and create all tables."""
    print("📦 Initializing DB and creating tables if they don't exist...")

    # Import models *absolutely*, not relatively
    from src.db import models  # ✅ this ensures models are registered properly

    models.Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='transcripts' AND column_name='role'
                ) THEN
                    ALTER TABLE transcripts ADD COLUMN role VARCHAR NOT NULL DEFAULT 'assistant';
                END IF;
            END $$;
        """))
    print("✅ Database tables created (if not already exist).")


if __name__ == "__main__":
    init_db()
