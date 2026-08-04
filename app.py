import os
import json
import hmac
import random
import re
from functools import wraps
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, abort, flash, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect, FlaskForm
from sqlalchemy.pool import NullPool
from wtforms import PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length

db = SQLAlchemy()
csrf = CSRFProtect()
SUBMISSION_CATEGORY = "Pending Review"
CONTENT_TYPES = {
    "quotes": "Quotes",
    "jokes": "Jokes",
    "poems": "Poems",
}
SYSTEM_RANDOM = random.SystemRandom()


def database_url():
    url = os.environ.get("SUPABASE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url and url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url or "sqlite:///quotes.db"


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["ADMIN_TOKEN"] = os.environ.get("ADMIN_TOKEN", "").lstrip("\ufeff").strip()
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL"))

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "poolclass": NullPool,
            "pool_pre_ping": True,
        }

    db.init_app(app)
    csrf.init_app(app)
    register_commands(app)
    register_routes(app)
    return app


def use_supabase_rest():
    return bool(
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        and not os.environ.get("SUPABASE_DATABASE_URL")
        and not os.environ.get("DATABASE_URL")
    )


class SupabaseRestClient:
    def __init__(self):
        supabase_url = os.environ["SUPABASE_URL"].lstrip("\ufeff").strip().rstrip("/")
        self.base_url = supabase_url if supabase_url.endswith("/rest/v1") else supabase_url + "/rest/v1"
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].lstrip("\ufeff").strip()
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def request(self, method, table, query=None, payload=None):
        url = f"{self.base_url}/{table}"
        if query:
            url = f"{url}?{query}"

        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers=self.headers, method=method)

        try:
            with urlopen(request, timeout=15) as response:
                data = response.read().decode("utf-8")
                return json.loads(data) if data else []
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {table} failed: {error.code} {detail}") from error


def supabase_client():
    return SupabaseRestClient()


def as_category(row):
    return SimpleNamespace(id=row["id"], name=row["name"], quotes=[])


def as_quote(row):
    return SimpleNamespace(
        id=row["id"],
        text=row["text"],
        author=row["author"],
        category_id=row["category_id"],
    )


def all_categories():
    if not use_supabase_rest():
        return Category.query.order_by(Category.id).all()

    client = supabase_client()
    categories = [as_category(row) for row in client.request("GET", "category", "select=*&order=id.asc")]
    quotes = [as_quote(row) for row in client.request("GET", "quote", "select=*&order=id.asc")]
    by_id = {category.id: category for category in categories}

    for quote in quotes:
        category = by_id.get(quote.category_id)
        if category:
            category.quotes.append(quote)

    return categories


def all_quotes():
    if not use_supabase_rest():
        return Quote.query.order_by(Quote.id).all()

    return [as_quote(row) for row in supabase_client().request("GET", "quote", "select=*&order=id.asc")]


def get_quote_or_404(id):
    if not use_supabase_rest():
        return Quote.query.get_or_404(id)

    query = urlencode({"id": f"eq.{id}", "select": "*"})
    rows = supabase_client().request("GET", "quote", query)
    if not rows:
        abort(404)
    return as_quote(rows[0])


def create_category(name):
    if not use_supabase_rest():
        category = Category(name=name)
        db.session.add(category)
        db.session.commit()
        return category

    return supabase_client().request("POST", "category", payload={"name": name})[0]


def get_category_or_404(id):
    if not use_supabase_rest():
        return Category.query.get_or_404(id)

    query = urlencode({"id": f"eq.{id}", "select": "*"})
    rows = supabase_client().request("GET", "category", query)
    if not rows:
        abort(404)
    return as_category(rows[0])


def update_category(id, name):
    if not use_supabase_rest():
        category = Category.query.get_or_404(id)
        category.name = name
        db.session.commit()
        return category

    query = urlencode({"id": f"eq.{id}"})
    rows = supabase_client().request("PATCH", "category", query, {"name": name})
    if not rows:
        abort(404)
    return rows[0]


def delete_category_by_id(id):
    if not use_supabase_rest():
        category = Category.query.get_or_404(id)
        db.session.delete(category)
        db.session.commit()
        return

    query = urlencode({"id": f"eq.{id}"})
    supabase_client().request("DELETE", "category", query)


def category_named(name):
    return next((category for category in all_categories() if category.name == name), None)


def is_pending_category(name):
    return name.casefold().startswith(SUBMISSION_CATEGORY.casefold())


def pending_category_name(content_type):
    return f"{SUBMISSION_CATEGORY} - {CONTENT_TYPES[content_type]}"


def ensure_submission_category(content_type="quotes"):
    name = pending_category_name(content_type)
    return category_named(name) or create_category(name)


def content_type_for_category(name):
    normalized = name.casefold()
    if "joke" in normalized:
        return "jokes"
    if "poem" in normalized:
        return "poems"
    return "quotes"


def fetch_json(url):
    external_request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "textr/1.0"},
    )
    try:
        with urlopen(external_request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("The external content provider is temporarily unavailable.") from error


def fetch_external_content(content_type):
    if content_type == "quotes":
        payload = fetch_json("https://zenquotes.io/api/random")
        if not isinstance(payload, list) or not payload or not payload[0].get("q"):
            raise RuntimeError("The quote provider returned an invalid response.")
        return {
            "text": payload[0]["q"].strip(),
            "author": (payload[0].get("a") or "Unknown").strip(),
            "category": "quotes",
            "source": "ZenQuotes",
            "source_url": "https://zenquotes.io/",
        }

    if content_type == "jokes":
        payload = fetch_json("https://v2.jokeapi.dev/joke/Any?type=single&safe-mode")
        if payload.get("error") or not payload.get("joke"):
            raise RuntimeError("The joke provider returned an invalid response.")
        return {
            "text": payload["joke"].strip(),
            "author": "JokeAPI",
            "category": "jokes",
            "source": "JokeAPI",
            "source_url": "https://jokeapi.dev/",
        }

    payload = fetch_json("https://poetrydb.org/random/1")
    if not isinstance(payload, list) or not payload or not payload[0].get("lines"):
        raise RuntimeError("The poem provider returned an invalid response.")
    poem = payload[0]
    lines = [line.strip() for line in poem["lines"][:24]]
    text = "\n".join(lines).strip()
    if len(poem["lines"]) > 24:
        text += "\n..."
    return {
        "text": text[:2000],
        "author": (poem.get("author") or "Unknown").strip(),
        "title": (poem.get("title") or "Untitled").strip(),
        "category": "poems",
        "source": "PoetryDB",
        "source_url": "https://poetrydb.org/",
    }


def fetch_random_external_content():
    content_types = list(CONTENT_TYPES)
    SYSTEM_RANDOM.shuffle(content_types)
    for content_type in content_types:
        try:
            return fetch_external_content(content_type)
        except RuntimeError:
            continue
    raise RuntimeError("External content providers are temporarily unavailable.")


def create_quote(text, author, category_id):
    if not use_supabase_rest():
        quote = Quote(text=text, author=author, category_id=category_id)
        db.session.add(quote)
        db.session.commit()
        return quote

    return supabase_client().request(
        "POST",
        "quote",
        payload={"text": text, "author": author, "category_id": category_id},
    )[0]


def update_quote(id, text, author, category_id):
    if not use_supabase_rest():
        quote = Quote.query.get_or_404(id)
        quote.text = text
        quote.author = author
        quote.category_id = category_id
        db.session.commit()
        return quote

    query = urlencode({"id": f"eq.{id}"})
    rows = supabase_client().request(
        "PATCH",
        "quote",
        query,
        {"text": text, "author": author, "category_id": category_id},
    )
    if not rows:
        abort(404)
    return rows[0]


def delete_quote_by_id(id):
    if not use_supabase_rest():
        quote = Quote.query.get_or_404(id)
        db.session.delete(quote)
        db.session.commit()
        return

    query = urlencode({"id": f"eq.{id}"})
    supabase_client().request("DELETE", "quote", query)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quotes = db.relationship("Quote", backref="category", lazy=True)


class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)


class QuoteForm(FlaskForm):
    text = TextAreaField("Text", validators=[DataRequired(), Length(max=500)])
    author = StringField("Author or source", validators=[DataRequired(), Length(max=100)])
    category = SelectField("Category", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Submit")


class CategoryForm(FlaskForm):
    name = StringField("Category Name", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Submit")


class PublicQuoteForm(FlaskForm):
    content_type = SelectField(
        "Type",
        choices=[(key, label[:-1] if label.endswith("s") else label) for key, label in CONTENT_TYPES.items()],
        validators=[DataRequired()],
    )
    text = TextAreaField("Text", validators=[DataRequired(), Length(max=500)])
    author = StringField("Author or source", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Submit for review")


class AdminLoginForm(FlaskForm):
    token = PasswordField("Admin token", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class EmptyForm(FlaskForm):
    submit = SubmitField()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def safe_next_url(value):
    return value if value and value.startswith("/") and not value.startswith("//") else None


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("Database tables created.")


def register_routes(app):
    @app.route("/")
    def index():
        return redirect(url_for("quotes_carousel"))

    @app.context_processor
    def template_context():
        return {"is_admin": bool(session.get("is_admin")), "logout_form": EmptyForm()}

    @app.route("/submit", methods=["GET", "POST"])
    def submit_quote():
        form = PublicQuoteForm()
        if form.validate_on_submit():
            category = ensure_submission_category(form.content_type.data)
            category_id = category["id"] if isinstance(category, dict) else category.id
            create_quote(form.text.data, form.author.data, category_id)
            flash("Thanks. Your submission was sent for review.", "success")
            return redirect(url_for("quotes_carousel"))
        return render_template("submit_quote.html", form=form)

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get("is_admin"):
            return redirect(url_for("admin_dashboard"))

        form = AdminLoginForm()
        if form.validate_on_submit():
            configured_token = app.config["ADMIN_TOKEN"]
            if configured_token and hmac.compare_digest(form.token.data, configured_token):
                session.clear()
                session["is_admin"] = True
                return redirect(safe_next_url(request.args.get("next")) or url_for("admin_dashboard"))
            flash("Invalid admin token.", "danger")
        return render_template("admin_login.html", form=form)

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        form = EmptyForm()
        if not form.validate_on_submit():
            abort(400)
        session.clear()
        flash("Signed out.", "success")
        return redirect(url_for("quotes_carousel"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        categories = all_categories()
        return render_template("index.html", categories=categories)

    @app.route("/quote/new", methods=["GET", "POST"])
    @admin_required
    def new_quote():
        form = QuoteForm()
        form.category.choices = [(c.id, c.name) for c in all_categories()]
        if form.validate_on_submit():
            create_quote(
                text=form.text.data,
                author=form.author.data,
                category_id=form.category.data,
            )
            flash("Quote added successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template("quote_form.html", form=form)

    @app.route("/category/new", methods=["GET", "POST"])
    @admin_required
    def new_category():
        form = CategoryForm()
        if form.validate_on_submit():
            name = form.name.data.strip()
            if category_named(name):
                flash("That category already exists.", "warning")
            else:
                create_category(name)
                flash("Category added successfully!", "success")
                return redirect(url_for("manage_categories"))
        return render_template("category_form.html", form=form)

    @app.route("/admin/categories")
    @admin_required
    def manage_categories():
        return render_template("categories.html", categories=all_categories())

    @app.route("/category/edit/<int:category_id>", methods=["GET", "POST"])
    @admin_required
    def edit_category(category_id):
        category = get_category_or_404(category_id)
        form = CategoryForm(obj=category)
        if form.validate_on_submit():
            name = form.name.data.strip()
            duplicate = category_named(name)
            if duplicate and duplicate.id != category_id:
                flash("That category already exists.", "warning")
            else:
                update_category(category_id, name)
                flash("Category updated.", "success")
                return redirect(url_for("manage_categories"))
        return render_template("category_form.html", form=form, category=category)

    @app.post("/category/delete/<int:category_id>")
    @admin_required
    def delete_category(category_id):
        form = EmptyForm()
        if not form.validate_on_submit():
            abort(400)
        if any(quote.category_id == category_id for quote in all_quotes()):
            flash("Move or delete this category's quotes before deleting it.", "warning")
        else:
            delete_category_by_id(category_id)
            flash("Category deleted.", "success")
        return redirect(url_for("manage_categories"))

    @app.route("/quote/edit/<int:id>", methods=["GET", "POST"])
    @admin_required
    def edit_quote(id):
        quote = get_quote_or_404(id)
        form = QuoteForm(obj=quote)
        form.category.choices = [(c.id, c.name) for c in all_categories()]
        if request.method == "GET":
            form.category.data = quote.category_id
        if form.validate_on_submit():
            update_quote(id, form.text.data, form.author.data, form.category.data)
            flash("Quote updated!", "success")
            return redirect(url_for("admin_dashboard"))
        return render_template("quote_form.html", form=form)

    @app.route("/quote/delete/<int:id>", methods=["POST"])
    @admin_required
    def delete_quote(id):
        form = EmptyForm()
        if not form.validate_on_submit():
            abort(400)
        delete_quote_by_id(id)
        flash("Quote deleted!", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/quotes_carousel")
    def quotes_carousel():
        categories = all_categories()
        category_by_id = {
            category.id: category
            for category in categories
            if not is_pending_category(category.name)
        }
        quotes_data = [
            {
                "text": quote.text,
                "author": quote.author,
                "category": content_type_for_category(category_by_id[quote.category_id].name),
                "source": "textr",
            }
            for quote in all_quotes()
            if quote.category_id in category_by_id
        ]
        SYSTEM_RANDOM.shuffle(quotes_data)
        selected = request.args.get("category", "all").casefold()
        if selected not in {"all", *CONTENT_TYPES}:
            selected = "all"
        response = make_response(
            render_template(
                "quotes_carousel.html",
                quotes=quotes_data,
                content_types=CONTENT_TYPES,
                selected_category=selected,
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/content/random")
    def random_external_content():
        content_type = request.args.get("type", "all").casefold()
        if content_type not in {"all", *CONTENT_TYPES}:
            return jsonify({"error": "Choose all, quotes, jokes, or poems."}), 400
        try:
            item = (
                fetch_random_external_content()
                if content_type == "all"
                else fetch_external_content(content_type)
            )
        except RuntimeError as error:
            return jsonify({"error": str(error)}), 503
        response = jsonify(item)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/content/next.js")
    def external_content_script():
        content_type = request.args.get("type", "all").casefold()
        request_id = request.args.get("request_id", "")
        if content_type not in {"all", *CONTENT_TYPES} or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            return "/* Invalid external content request. */", 400, {"Content-Type": "application/javascript"}

        try:
            item = (
                fetch_random_external_content()
                if content_type == "all"
                else fetch_external_content(content_type)
            )
            payload = {"requestId": request_id, "item": item}
        except RuntimeError as error:
            payload = {"requestId": request_id, "error": str(error)}

        serialized = (
            json.dumps(payload, ensure_ascii=True)
            .replace("<", r"\u003c")
            .replace(">", r"\u003e")
            .replace("&", r"\u0026")
        )
        response = make_response(f"window.textrReceiveExternalItem({serialized});")
        response.headers["Content-Type"] = "application/javascript; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        return response


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
            db.create_all()
    app.run(debug=True)
