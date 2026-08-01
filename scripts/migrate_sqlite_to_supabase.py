import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import Category, Quote, app, db  # noqa: E402


def copy_sqlite_data(sqlite_path):
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        categories = conn.execute("select id, name from category").fetchall()
        quotes = conn.execute("select id, text, author, category_id from quote").fetchall()

    with app.app_context():
        db.create_all()
        category_id_map = {}

        for row in categories:
            category = Category.query.filter_by(name=row["name"]).first()
            if category is None:
                category = Category(name=row["name"])
                db.session.add(category)
                db.session.flush()
            category_id_map[row["id"]] = category.id

        for row in quotes:
            exists = Quote.query.filter_by(text=row["text"], author=row["author"]).first()
            if exists is None:
                db.session.add(
                    Quote(
                        text=row["text"],
                        author=row["author"],
                        category_id=category_id_map[row["category_id"]],
                    )
                )

        db.session.commit()
        print(f"Migrated {len(categories)} categories and {len(quotes)} quotes.")


if __name__ == "__main__":
    if not (os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")):
        raise SystemExit("Set SUPABASE_DATABASE_URL or DATABASE_URL before migrating.")

    sqlite_db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "instance" / "quotes.db"
    copy_sqlite_data(sqlite_db)
