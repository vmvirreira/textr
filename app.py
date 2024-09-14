from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, SelectField
from flask_wtf.file import FileAllowed
from wtforms.validators import DataRequired, URL
from werkzeug.utils import secure_filename
from flask import jsonify
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with your own secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quotes.db'
#app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///bookmarkr/instance/bookmarks.db"
print(os.getcwd())
#app.config['SQLALCHEMY_DATABASE_URI'] ='sqlite:///' + os.path.join(os.getcwd(), 'bookmarkr/instance/bookmarks.db') 
UPLOAD_FOLDER = 'textr/static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# Models
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quotes = db.relationship('Quote', backref='category', lazy=True)

class Quote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

# Forms
class QuoteForm(FlaskForm):
    text = StringField('Quote', validators=[DataRequired()])
    author = StringField('Author', validators=[DataRequired()])
    category = SelectField('Category', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit')

class CategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired()])
    submit = SubmitField('Submit')

# Routes
@app.route('/')
def index():
    categories = Category.query.all()
    return render_template('index.html', categories=categories)

@app.route('/quote/new', methods=['GET', 'POST'])
def new_quote():
    form = QuoteForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        quote = Quote(text=form.text.data, author=form.author.data, category_id=form.category.data)
        db.session.add(quote)
        db.session.commit()
        flash('Quote added successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('quote_form.html', form=form)

@app.route('/category/new', methods=['GET', 'POST'])
def new_category():
    form = CategoryForm()
    if form.validate_on_submit():
        category = Category(name=form.name.data)
        db.session.add(category)
        db.session.commit()
        flash('Category added successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('category_form.html', form=form)

@app.route('/quote/edit/<int:id>', methods=['GET', 'POST'])
def edit_quote(id):
    quote = Quote.query.get_or_404(id)
    form = QuoteForm(obj=quote)
    form.category.choices = [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        quote.text = form.text.data
        quote.author = form.author.data
        quote.category_id = form.category.data
        db.session.commit()
        flash('Quote updated!', 'success')
        return redirect(url_for('index'))
    return render_template('quote_form.html', form=form)

@app.route('/quote/delete/<int:id>', methods=['POST'])
def delete_quote(id):
    quote = Quote.query.get_or_404(id)
    db.session.delete(quote)
    db.session.commit()
    flash('Quote deleted!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        # Ensure the database is created if it doesn't exist
        if not os.path.exists('quotes.db'):
            db.create_all()
    app.run(debug=True)