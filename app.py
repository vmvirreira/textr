import os
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, abort, flash, redirect, render_template, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy.pool import NullPool
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired

db = SQLAlchemy()


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
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "poolclass": NullPool,
            "pool_pre_ping": True,
        }

    db.init_app(app)
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
        supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
        self.base_url = supabase_url if supabase_url.endswith("/rest/v1") else supabase_url + "/rest/v1"
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
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
    text = StringField("Quote", validators=[DataRequired()])
    author = StringField("Author", validators=[DataRequired()])
    category = SelectField("Category", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Submit")


class CategoryForm(FlaskForm):
    name = StringField("Category Name", validators=[DataRequired()])
    submit = SubmitField("Submit")


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("Database tables created.")


def register_routes(app):
    @app.route("/")
    def index():
        categories = all_categories()
        return render_template("index.html", categories=categories)

    @app.route("/quote/new", methods=["GET", "POST"])
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
            return redirect(url_for("index"))
        return render_template("quote_form.html", form=form)

    @app.route("/category/new", methods=["GET", "POST"])
    def new_category():
        form = CategoryForm()
        if form.validate_on_submit():
            create_category(form.name.data)
            flash("Category added successfully!", "success")
            return redirect(url_for("index"))
        return render_template("category_form.html", form=form)

    @app.route("/quote/edit/<int:id>", methods=["GET", "POST"])
    def edit_quote(id):
        quote = get_quote_or_404(id)
        form = QuoteForm(obj=quote)
        form.category.choices = [(c.id, c.name) for c in all_categories()]
        if form.validate_on_submit():
            update_quote(id, form.text.data, form.author.data, form.category.data)
            flash("Quote updated!", "success")
            return redirect(url_for("index"))
        return render_template("quote_form.html", form=form)

    @app.route("/quote/delete/<int:id>", methods=["POST"])
    def delete_quote(id):
        delete_quote_by_id(id)
        flash("Quote deleted!", "success")
        return redirect(url_for("index"))

    @app.route("/quotes_carousel")
    def quotes_carousel():
        quotes = all_quotes()
        quotes_data = [{"text": quote.text, "author": quote.author} for quote in quotes]
        return render_template("quotes_carousel.html", quotes=quotes_data)


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
            db.create_all()
    app.run(debug=True)
