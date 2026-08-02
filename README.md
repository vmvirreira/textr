# textr

Small Flask app for presenting curated quotes and moderating public submissions.

## Local Development

Create a virtual environment, install dependencies, then run Flask:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
$env:SECRET_KEY = "dev-secret"
$env:ADMIN_TOKEN = "dev-admin-token"
$env:FLASK_APP = "app.py"
.\.venv\Scripts\flask init-db
.\.venv\Scripts\flask run
```

Without Supabase or database environment variables, the app uses local SQLite at `instance/quotes.db`.

## Supabase Setup

1. Create a Supabase project.
2. In the Supabase SQL editor, run `supabase/schema.sql`.
3. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

The app uses Supabase REST mode when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set. It can also use direct Postgres mode if `SUPABASE_DATABASE_URL` or `DATABASE_URL` is set.

Public submissions are always stored in the `Pending Review` category. Quotes in that category are excluded from Slides until an administrator moves them to another category.

## Administration

Open `/admin/login` and enter the `ADMIN_TOKEN`. The authenticated admin area supports adding, editing, moving, and deleting quotes, plus adding, editing, and deleting empty categories.

Public visitors can submit quotes at `/submit`. They cannot choose a category or access administrative routes.

For direct Postgres mode on Vercel/serverless, use the Supabase transaction pooler port `6543`. The app configures SQLAlchemy with `NullPool` for Postgres so connections are short-lived.

To copy the existing local SQLite data into Supabase:

```powershell
$env:SUPABASE_DATABASE_URL = "<supabase transaction pooler connection string>"
.\.venv\Scripts\python scripts\migrate_sqlite_to_supabase.py
```

## Vercel Setup

Set these Vercel environment variables:

```text
SECRET_KEY=<long random secret>
ADMIN_TOKEN=<long random admin token>
SUPABASE_URL=<supabase project URL>
SUPABASE_SERVICE_ROLE_KEY=<supabase service role key>
```

Deploy from the project root with:

```powershell
vercel
vercel --prod
```

Vercel uses `app.py` as the Python WSGI entrypoint and routes all paths through it via `vercel.json`.
