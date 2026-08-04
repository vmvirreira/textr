# textr

Small Flask app for presenting curated quotes, jokes, and poems while moderating public submissions.

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

Public submissions are stored in type-specific moderation categories such as `Pending Review - Quotes`, `Pending Review - Jokes`, and `Pending Review - Poems`. Every pending category is excluded from Slides until an administrator moves the item to a public category.

Create the public `Quotes`, `Jokes`, and `Poems` categories in Supabase. Existing categories that do not contain `joke` or `poem` in their name are treated as quotes for display purposes.

## Slides and external sources

Every Slides request shuffles the local Supabase content. Visitors can select All, Quotes, Jokes, or Poems from the category wheel. After one pass through the selected local set, the slideshow continues with items from `/api/content/random`. All mode tries the three providers in a new random order for each item, so one unavailable provider does not interrupt the stream. A specific category keeps using its matching provider.

- Quotes: ZenQuotes
- Jokes: JokeAPI with `safe-mode`
- Poems: PoetryDB

External requests run on the server, use short timeouts, and do not require browser-side credentials. Provider content is labeled and linked in the slide. If every eligible provider is unavailable, the current item remains visible and the next automatic or manual advance retries the request.

The slide page also includes an optional EDM/chill radio player. Its previous, play/pause, and next controls cycle through HTTPS SomaFM streams independently of the text slideshow.

## Administration

Open `/admin/login` and enter the `ADMIN_TOKEN`. The authenticated admin area supports adding, editing, moving, and deleting quotes, plus adding, editing, and deleting empty categories.

Public visitors can submit a quote, joke, or poem at `/submit`. They choose the intended type, but cannot publish directly or access administrative routes.

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
