import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import (  # noqa: E402
    all_categories,
    all_quotes,
    app,
    create_category,
    create_quote,
    db,
    use_supabase_rest,
)


def record_id(record):
    return record["id"] if isinstance(record, dict) else record.id


def copy_sqlite_data(sqlite_path):
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")

    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        categories = conn.execute("select id, name from category").fetchall()
        quotes = conn.execute("select id, text, author, category_id from quote").fetchall()

    with app.app_context():
        if not use_supabase_rest():
            db.create_all()

        categories_by_name = {category.name: category for category in all_categories()}
        existing_quotes = {(quote.text, quote.author) for quote in all_quotes()}
        category_id_map = {}
        categories_created = 0
        quotes_created = 0

        for row in categories:
            category = categories_by_name.get(row["name"])
            if category is None:
                category = create_category(row["name"])
                categories_by_name[row["name"]] = category
                categories_created += 1
            category_id_map[row["id"]] = record_id(category)

        for row in quotes:
            quote_key = (row["text"], row["author"])
            if quote_key not in existing_quotes:
                create_quote(
                    text=row["text"],
                    author=row["author"],
                    category_id=category_id_map[row["category_id"]],
                )
                existing_quotes.add(quote_key)
                quotes_created += 1

        print(
            f"Created {categories_created} categories and {quotes_created} quotes "
            f"from {len(categories)} categories and {len(quotes)} quotes."
        )


if __name__ == "__main__":
    has_database_url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    has_rest_credentials = os.environ.get("SUPABASE_URL") and os.environ.get(
        "SUPABASE_SERVICE_ROLE_KEY"
    )
    if not (has_database_url or has_rest_credentials):
        raise SystemExit(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or set "
            "SUPABASE_DATABASE_URL/DATABASE_URL before migrating."
        )

    sqlite_db = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "instance" / "quotes.db"
    copy_sqlite_data(sqlite_db)
