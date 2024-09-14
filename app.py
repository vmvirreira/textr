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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookmarks.db'
#app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///bookmarkr/instance/bookmarks.db"
print(os.getcwd())
#app.config['SQLALCHEMY_DATABASE_URI'] ='sqlite:///' + os.path.join(os.getcwd(), 'bookmarkr/instance/bookmarks.db') 
UPLOAD_FOLDER = 'bookmarkr/static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# Models
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    bookmarks = db.relationship('Bookmark', backref='category', lazy=True)

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    image = db.Column(db.String(150))
    order = db.Column(db.Integer, default=0)  # Add this to store the order of bookmarks
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)


# Forms
class BookmarkForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    url = StringField('URL', validators=[DataRequired(), URL()])
    image = FileField('Image', validators=[FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')])
    category = SelectField('Category', coerce=int)
    submit = SubmitField('Submit')

class CategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired()])
    submit = SubmitField('Submit')

# Routes for Categories
@app.route('/categories')
def categories():
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)

@app.route('/category/new', methods=['GET', 'POST'])
def new_category():
    form = CategoryForm()
    if form.validate_on_submit():
        category = Category(name=form.name.data)
        db.session.add(category)
        db.session.commit()
        flash('Category created successfully!', 'success')
        return redirect(url_for('categories'))
    return render_template('category_form.html', form=form)

@app.route('/category/edit/<int:category_id>', methods=['GET', 'POST'])
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        category.name = form.name.data
        db.session.commit()
        flash('Category updated successfully!', 'success')
        return redirect(url_for('categories'))
    return render_template('category_form.html', form=form)

@app.route('/category/delete/<int:category_id>', methods=['POST'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('categories'))

# Routes for Bookmarks
@app.route('/')
def index():
    categories = Category.query.all()
    for category in categories:
        category.bookmarks = Bookmark.query.filter_by(category_id=category.id).order_by(Bookmark.order).all()
    return render_template('index.html', categories=categories)

@app.route('/bookmark/new', methods=['GET', 'POST'])
def new_bookmark():
    form = BookmarkForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        filename = None
        if form.image.data:
            file = form.image.data
            filename = secure_filename(file.filename)
            # Ensure the upload directory exists before saving the file
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        bookmark = Bookmark(
            title=form.title.data,
            url=form.url.data,
            image=filename,
            category_id=form.category.data
        )
        db.session.add(bookmark)
        db.session.commit()
        flash('Bookmark created successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('bookmark_form.html', form=form)

@app.route('/bookmark/edit/<int:bookmark_id>', methods=['GET', 'POST'])
def edit_bookmark(bookmark_id):
    bookmark = Bookmark.query.get_or_404(bookmark_id)
    form = BookmarkForm(obj=bookmark)
    form.category.choices = [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        if form.image.data:
            file = form.image.data
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            bookmark.image = filename
        bookmark.title = form.title.data
        bookmark.url = form.url.data
        bookmark.category_id = form.category.data
        db.session.commit()
        flash('Bookmark updated successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('bookmark_form.html', form=form, bookmark=bookmark)

@app.route('/bookmark/delete/<int:bookmark_id>', methods=['POST'])
def delete_bookmark(bookmark_id):
    bookmark = Bookmark.query.get_or_404(bookmark_id)
    db.session.delete(bookmark)
    db.session.commit()
    flash('Bookmark deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/update_bookmark_order', methods=['POST'])
def update_bookmark_order():
    data = request.get_json()

    try:
        category_id = data['category_id']
        new_order = data['order']  # This is a list of bookmark IDs in the new order

        # Loop through the new order and update the database
        for index, bookmark_id in enumerate(new_order):
            bookmark = Bookmark.query.get(bookmark_id)
            if bookmark:
                bookmark.order = index  # Assuming you have an 'order' field in the Bookmark model
                db.session.commit()

        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))
    
if __name__ == '__main__':
    with app.app_context():
        # Ensure the database is created if it doesn't exist
        if not os.path.exists('bookmarks.db'):
            db.create_all()
    app.run(debug=True)

