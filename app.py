from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import os
import ssl
import pymysql
from dotenv import load_dotenv

load_dotenv()
pymysql.install_as_MySQLdb()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("SQLALCHEMY_DATABASE_URI")
app.config['SESSION_COOKIE_SECURE'] = os.getenv("SESSION_COOKIE_SECURE")
app.config['SESSION_COOKIE_HTTPONLY'] = os.getenv("SESSION_COOKIE_HTTPONLY")
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
app.config['PERMANENT_SESSION_LIFETIME'] = os.getenv("PERMANENT_SESSION_LIFETIME", )
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS")

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'max_overflow': 10,
    'pool_recycle': 280,
    'pool_pre_ping': True,
    'connect_args': {
        'ssl': ssl_context
    }
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----------------- Database Models -----------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    buys = db.relationship('BuyItem', backref='user', cascade="all, delete-orphan", lazy=True)
    wishes = db.relationship('WishItem', backref='user', cascade="all, delete-orphan", lazy=True)

class BuyItem(db.Model):
    __tablename__ = 'buy_items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Integer, default=1)
    estimated_price = db.Column(db.Float, default=0.0)
    store = db.Column(db.String(100), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    @property
    def is_overdue(self):
        if self.due_date and not self.is_completed:
            return date.today() > self.due_date
        return False

class WishItem(db.Model):
    __tablename__ = 'wish_items'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    estimated_cost = db.Column(db.Float, default=0.0)
    priority = db.Column(db.String(20), default='Medium')
    notes = db.Column(db.Text, nullable=True)
    is_achieved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    @property
    def is_overdue(self):
        if self.due_date and not self.is_achieved:
            return date.today() > self.due_date
        return False

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------- Auth Routes -----------------
@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('buy_list'))
    return redirect(url_for('login'))

# 1. Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('buy_list'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('buy_list'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

# 2. Registration Page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('buy_list'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username is already taken.', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account registered successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ----------------- Buy List Routes -----------------
# 3. Buy List Page
@app.route('/buy-list', methods=['GET', 'POST'])
@login_required
def buy_list():
    if request.method == 'POST':
        title = request.form.get('title')
        due_date_str = request.form.get('due_date')
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        
        if title:
            new_item = BuyItem(title=title, due_date=due_date, user_id=current_user.id)
            db.session.add(new_item)
            db.session.commit()
            return redirect(url_for('buy_list'))
            
    items = BuyItem.query.filter_by(user_id=current_user.id).order_by(BuyItem.created_at.desc()).all()
    return render_template('buy_list.html', items=items)

# 4. Buy List Detail Page
@app.route('/buy-list/<int:item_id>', methods=['GET', 'POST'])
@login_required
def buy_detail(item_id):
    item = BuyItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        if 'delete' in request.form:
            db.session.delete(item)
            db.session.commit()
            return redirect(url_for('buy_list'))
            
        due_date_str = request.form.get('due_date')
        item.title = request.form.get('title')
        item.description = request.form.get('description')
        item.quantity = int(request.form.get('quantity') or 1)
        item.estimated_price = float(request.form.get('estimated_price') or 0.0)
        item.store = request.form.get('store')
        item.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        item.is_completed = 'is_completed' in request.form
        db.session.commit()
        return redirect(url_for('buy_list'))
    return render_template('buy_detail.html', item=item)

# ----------------- Wishlist Routes -----------------
# 5. Long-Time Wishlist Page
@app.route('/wishlist', methods=['GET', 'POST'])
@login_required
def wishlist():
    if request.method == 'POST':
        title = request.form.get('title')
        due_date_str = request.form.get('due_date')
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        
        if title:
            new_wish = WishItem(title=title, due_date=due_date, user_id=current_user.id)
            db.session.add(new_wish)
            db.session.commit()
            return redirect(url_for('wishlist'))
            
    items = WishItem.query.filter_by(user_id=current_user.id).order_by(WishItem.created_at.desc()).all()
    return render_template('wishlist.html', items=items)

# 6. Wishlist Detail Page
@app.route('/wishlist/<int:item_id>', methods=['GET', 'POST'])
@login_required
def wishlist_detail(item_id):
    item = WishItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        if 'delete' in request.form:
            db.session.delete(item)
            db.session.commit()
            return redirect(url_for('wishlist'))
            
        due_date_str = request.form.get('due_date')
        item.title = request.form.get('title')
        item.description = request.form.get('description')
        item.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        item.estimated_cost = float(request.form.get('estimated_cost') or 0.0)
        item.priority = request.form.get('priority')
        item.notes = request.form.get('notes')
        item.is_achieved = 'is_achieved' in request.form
        db.session.commit()
        return redirect(url_for('wishlist'))
    return render_template('wishlist_detail.html', item=item)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()
