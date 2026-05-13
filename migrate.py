"""
Apply schema migrations for the Visit table.
Safe to run on both fresh and existing databases.
"""
from app import app
from models import db
from sqlalchemy import text, inspect

NEW_COLUMNS = [
    ("event_type", "VARCHAR(100)"),
    ("email",      "VARCHAR(200)"),
]

with app.app_context():
    db.create_all()

    inspector = inspect(db.engine)
    existing = {col["name"] for col in inspector.get_columns("visit")}

    with db.engine.connect() as conn:
        for col_name, col_type in NEW_COLUMNS:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE visit ADD COLUMN {col_name} {col_type}"))
                print(f"Added column: visit.{col_name}")
            else:
                print(f"Already exists: visit.{col_name}")
        conn.commit()

print("Migration complete.")
