import os

from flask import Flask, flash, redirect, render_template, url_for
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
        categories = Category.query.all()
        return render_template("index.html", categories=categories)

    @app.route("/quote/new", methods=["GET", "POST"])
    def new_quote():
        form = QuoteForm()
        form.category.choices = [(c.id, c.name) for c in Category.query.all()]
        if form.validate_on_submit():
            quote = Quote(
                text=form.text.data,
                author=form.author.data,
                category_id=form.category.data,
            )
            db.session.add(quote)
            db.session.commit()
            flash("Quote added successfully!", "success")
            return redirect(url_for("index"))
        return render_template("quote_form.html", form=form)

    @app.route("/category/new", methods=["GET", "POST"])
    def new_category():
        form = CategoryForm()
        if form.validate_on_submit():
            category = Category(name=form.name.data)
            db.session.add(category)
            db.session.commit()
            flash("Category added successfully!", "success")
            return redirect(url_for("index"))
        return render_template("category_form.html", form=form)

    @app.route("/quote/edit/<int:id>", methods=["GET", "POST"])
    def edit_quote(id):
        quote = Quote.query.get_or_404(id)
        form = QuoteForm(obj=quote)
        form.category.choices = [(c.id, c.name) for c in Category.query.all()]
        if form.validate_on_submit():
            quote.text = form.text.data
            quote.author = form.author.data
            quote.category_id = form.category.data
            db.session.commit()
            flash("Quote updated!", "success")
            return redirect(url_for("index"))
        return render_template("quote_form.html", form=form)

    @app.route("/quote/delete/<int:id>", methods=["POST"])
    def delete_quote(id):
        quote = Quote.query.get_or_404(id)
        db.session.delete(quote)
        db.session.commit()
        flash("Quote deleted!", "success")
        return redirect(url_for("index"))

    @app.route("/quotes_carousel")
    def quotes_carousel():
        quotes = Quote.query.all()
        quotes_data = [{"text": quote.text, "author": quote.author} for quote in quotes]
        return render_template("quotes_carousel.html", quotes=quotes_data)


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
            db.create_all()
    app.run(debug=True)
