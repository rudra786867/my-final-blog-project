import os
import smtplib
from datetime import date
from functools import wraps

from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Import your forms (ensure forms.py is in the same folder)
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

# 1. Load local .env only if it exists (for local testing)
if os.path.exists(".env"):
    load_dotenv()

app = Flask(__name__)

# 2. CONFIGURATION - IMPORTANT: Only do this ONCE
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key')

# Fix for PostgreSQL URL (Render/Heroku sometimes use postgres:// which SQLAlchemy 2.0 hates)
db_url = os.environ.get('DATABASE_URL', 'sqlite:///posts.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

# 3. INITIALIZE EXTENSIONS
ckeditor = CKEditor(app)
Bootstrap5(app)
login_manager = LoginManager()
login_manager.init_app(app)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
db.init_app(app)

gravatar = Gravatar(app, size=100, rating='g', default='retro')

# 4. DATABASE MODELS
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")

class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    author = relationship("User", back_populates="posts")
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments = relationship("Comment", back_populates="parent_post")

class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")
    post_id: Mapped[str] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")

with app.app_context():
    db.create_all()

# 5. AUTHENTICATION HELPERS
@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function

# 6. ROUTES
@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        if result.scalar():
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))
        hash_and_salted_password = generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=8)
        new_user = User(email=form.email.data, name=form.name.data, password=hash_and_salted_password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("get_all_posts"))
    return render_template("register.html", form=form, current_user=current_user)

@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
        if not user or not check_password_hash(user.password, form.password.data):
            flash("Invalid credentials, please try again.")
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('get_all_posts'))
    return render_template("login.html", form=form, current_user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


# DEBUG ROUTES - YE ADD KAR
@app.route('/test')
def test():
    return "<h1>🎉 SERVER PERFECT! Templates issue!</h1><p><a href='/'>Home</a> | <a href='/debug'>Debug</a></p>"


@app.route('/debug')
def debug():
    import os
    return f"""
    <h1>DEBUG INFO</h1>
    <p>Current dir: {os.getcwd()}</p>
    <p>Templates folder exists: {os.path.exists('templates')}</p>
    <p>index.html exists: {os.path.exists('templates/index.html') if os.path.exists('templates') else 'No templates folder'}</p>
    <p>Files in current dir: {os.listdir('.') if os.path.exists('.') else 'Cannot list'}</p>
    """


@app.route('/')
def get_all_posts():
    try:
        posts = db.session.execute(db.select(BlogPost)).scalars().all()
    except:
        posts = []

    # FAIL-SAFE: Agar index.html nahi hai to plain HTML bhej
    try:
        return render_template("index.html", all_posts=posts, current_user=current_user)
    except:
        return """
        <h1>🎉 Rudra's Blog - LIVE!</h1>
        <p>No posts yet. <a href="/register">Register</a> | <a href="/login">Login</a></p>
        <p><a href="/test">Test Server</a> | <a href="/debug">Debug Info</a></p>
        """


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for("login"))
        new_comment = Comment(text=comment_form.comment_text.data, comment_author=current_user, parent_post=requested_post)
        db.session.add(new_comment)
        db.session.commit()
    return render_template("post.html", post=requested_post, current_user=current_user, form=comment_form)

@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(title=form.title.data, subtitle=form.subtitle.data, body=form.body.data, img_url=form.img_url.data, author=current_user, date=date.today().strftime("%B %d, %Y"))
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)

@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(title=post.title, subtitle=post.subtitle, img_url=post.img_url, author=post.author, body=post.body)
    if edit_form.validate_on_submit():
        post.title, post.subtitle, post.img_url, post.body = edit_form.title.data, edit_form.subtitle.data, edit_form.img_url.data, edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)

@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))

@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        send_email(request.form["name"], request.form["email"], request.form["phone"], request.form["message"])
        return render_template("contact.html", msg_sent=True)
    return render_template("contact.html", msg_sent=False)

def send_email(name, email, phone, message):
    mail_address = os.environ.get("EMAIL_KEY")
    mail_pw = os.environ.get("PASSWORD_KEY")
    email_message = f"Subject:New Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage:{message}"
    with smtplib.SMTP("smtp.gmail.com", 465, timeout=10) as connection:
        connection.starttls()
        connection.login(mail_address, mail_pw)
        connection.sendmail(mail_address, mail_address, email_message)

if __name__ == "__main__":
    app.run(debug=True, port=5001)