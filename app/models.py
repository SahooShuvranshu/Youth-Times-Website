from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
import string

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(10), default='user')
    is_super_admin = db.Column(db.Boolean, default=False)  # Cannot be demoted
    name = db.Column(db.String(150), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=True)
    profile_image = db.Column(db.String(200), nullable=True)  # For uploaded image URLs
    date_of_birth = db.Column(db.Date, nullable=True)  # New: Date of birth
    gender = db.Column(db.String(20), nullable=True)  # New: Gender field
    is_confirmed = db.Column(db.Boolean, default=False)
    location = db.Column(db.String(100), nullable=True)
    website = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def is_admin(self):
        return self.role == 'admin' or self.is_super_admin
    
    @property
    def profile_image_url(self):
        """Return profile image URL or placeholder"""
        if self.profile_image:
            return self.profile_image
        else:
            # Generate placeholder with user initials
            initials = ""
            if self.name:
                name_parts = self.name.split()
                initials = "".join([part[0].upper() for part in name_parts[:2]])
            elif self.username:
                initials = self.username[:2].upper()
            else:
                initials = "U"
            return f"https://via.placeholder.com/150x150/cccccc/666666?text={initials}"

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hash_id = db.Column(db.String(20), unique=True, nullable=False)  # Unique hash identifier
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, published
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    credibility_score = db.Column(db.Float, nullable=True)  # Professional credibility rating 0-100
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    tags = db.Column(db.String(500), nullable=True)  # Comma-separated tags
    image_url = db.Column(db.String(500), nullable=True)
    views = db.Column(db.Integer, default=0)
    editor_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author = db.relationship('User', foreign_keys=[author_id], backref='authored_articles')
    submitter = db.relationship('User', foreign_keys=[submitted_by], backref='submitted_articles')
    category = db.relationship('Category', backref='articles')
    
    def __init__(self, **kwargs):
        super(Article, self).__init__(**kwargs)
        if not self.hash_id:
            self.hash_id = self.generate_hash_id()
    
    def generate_hash_id(self):
        """Generate a unique hash ID for the article"""
        while True:
            # Generate a 12-character hash using letters and numbers
            hash_id = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            # Ensure it doesn't already exist (but avoid querying during initialization)
            try:
                if not Article.query.filter_by(hash_id=hash_id).first():
                    return hash_id
            except:
                # If we can't query (during initial creation), just return the hash
                return hash_id

class LogEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    # Optionally link back to article
    article = db.relationship('Article', backref='logs')

class Notification(db.Model):
    """User notifications for article status changes and actions"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=True)
    message = db.Column(db.String(200), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    # Relationships
    user = db.relationship('User', backref='notifications')
    article = db.relationship('Article', backref='notifications')

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(7), default='#3B82F6')  # Hex color for category badge

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    is_deleted = db.Column(db.Boolean, default=False)  # For tracking filtered comments
    article = db.relationship('Article', backref='comments')
    user = db.relationship('User', backref='comments')

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    article = db.relationship('Article', backref='likes')
    user = db.relationship('User', backref='likes')
    
    # Ensure a user can only like an article once
    __table_args__ = (db.UniqueConstraint('article_id', 'user_id', name='unique_article_user_like'),)

class Newsletter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    subscribed_at = db.Column(db.DateTime, default=db.func.now())

class Analytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)  # 'view', 'share', 'comment'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    article = db.relationship('Article', backref='analytics')
    user = db.relationship('User', backref='analytics')

class TickerMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<TickerMessage \'{self.message}\'>'
