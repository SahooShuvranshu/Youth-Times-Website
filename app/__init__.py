from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
from config import Config
from sqlalchemy import inspect, text, event
from sqlalchemy.engine import Engine
import click
from flask import url_for
from authlib.integrations.flask_client import OAuth
from datetime import datetime

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
oauth = OAuth()

# Enable foreign key support for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if 'sqlite' in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Validate production configuration
    Config.validate_production_config()

    # Initialize Authlib OAuth
    oauth.init_app(app)
    # Register Google OAuth client only if credentials are provided
    if app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile'
            }
        )

    db.init_app(app)
    login_manager.init_app(app)

    # Register nl2br filter for Jinja2
    def nl2br(value):
        if value is None:
            return ''
        return value.replace('\n', '<br>')
    
    # Register excerpt filter for creating text excerpts from HTML
    def excerpt(value, length=200):
        import bleach
        try:
            # Remove HTML tags to get plain text
            text = bleach.clean(value, tags=[], strip=True)
            # Clean up extra whitespace
            text = ' '.join(text.split())
            # Truncate if needed
            if len(text) > length:
                text = text[:length].rsplit(' ', 1)[0] + '...'
            return text
        except Exception:
            return value[:length] + '...' if len(value) > length else value
    
    app.jinja_env.filters['nl2br'] = nl2br
    app.jinja_env.filters['excerpt'] = excerpt

    from . import models

    from .routes.articles import bp as articles_bp
    app.register_blueprint(articles_bp)
    
    from .routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    
    from .routes.admin import bp as admin_bp
    app.register_blueprint(admin_bp)
     
    # Removed mobile blueprint registration
    
    from .routes.weather import bp as weather_bp
    app.register_blueprint(weather_bp)

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()  # For both SQLite and Supabase
        
        # Ensure notification table has correct schema
        try:
            inspector = inspect(db.engine)
            if 'notification' in inspector.get_table_names():
                cols = [col['name'] for col in inspector.get_columns('notification')]
                
                # Fix notification table schema if needed
                if 'read' in cols and 'is_read' not in cols:
                    # Rename 'read' column to 'is_read'
                    db.session.execute(text('ALTER TABLE notification RENAME COLUMN read TO is_read'))
                    db.session.commit()
                    print("✅ Fixed notification.read -> notification.is_read")
                
                # Ensure timestamp column exists
                if 'timestamp' not in cols and 'created_at' in cols:
                    db.session.execute(text('ALTER TABLE notification RENAME COLUMN created_at TO timestamp'))
                    db.session.commit()
                    print("✅ Fixed notification.created_at -> notification.timestamp")
                    
        except Exception as e:
            print(f"⚠️ Database migration note: {e}")
        
        # Ensure trust_score column exists (SQLite won't auto-migrate)
        inspector = inspect(db.engine)
        cols = [col['name'] for col in inspector.get_columns('article')]
        if 'trust_score' not in cols:
            # Add trust_score column manually for existing SQLite databases
            db.session.execute(
                text('ALTER TABLE article ADD COLUMN trust_score FLOAT')
            )
            db.session.commit()
            print("✅ Added trust_score column to articles")

        # Ensure new User profile columns exist
        user_cols = [col['name'] for col in inspector.get_columns('user')]
        if 'name' not in user_cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN name VARCHAR(150)'))
        if 'bio' not in user_cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN bio TEXT'))
        if 'email' not in user_cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN email VARCHAR(150)'))
        if 'profile_image' not in user_cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN profile_image VARCHAR(200)'))
        if 'is_confirmed' not in user_cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN is_confirmed BOOLEAN DEFAULT 0'))
        if 'is_super_admin' not in user_cols:
            db.session.execute(text('ALTER TABLE user ADD COLUMN is_super_admin BOOLEAN DEFAULT 0'))
        
        # Ensure new Article columns exist
        article_cols = [col['name'] for col in inspector.get_columns('article')]
        if 'category_id' not in article_cols:
            db.session.execute(text('ALTER TABLE article ADD COLUMN category_id INTEGER'))
        if 'tags' not in article_cols:
            db.session.execute(text('ALTER TABLE article ADD COLUMN tags VARCHAR(500)'))
        if 'image_url' not in article_cols:
            db.session.execute(text('ALTER TABLE article ADD COLUMN image_url VARCHAR(500)'))
        if 'created_at' not in article_cols:
            # SQLite doesn't support non-constant defaults, so add column without default
            db.session.execute(text('ALTER TABLE article ADD COLUMN created_at DATETIME'))
            # Update existing articles with current timestamp
            db.session.execute(text("UPDATE article SET created_at = datetime('now') WHERE created_at IS NULL"))
        
        db.session.commit()
        
        # Create default categories
        from .models import Category
        default_categories = [
            {'name': 'News', 'description': 'Latest campus and world news', 'color': '#EF4444'},
            {'name': 'Sports', 'description': 'Sports coverage and updates', 'color': '#10B981'},
            {'name': 'Opinion', 'description': 'Editorial and opinion pieces', 'color': '#8B5CF6'},
            {'name': 'Arts & Culture', 'description': 'Arts, culture, and entertainment', 'color': '#F59E0B'},
            {'name': 'Technology', 'description': 'Tech news and innovations', 'color': '#3B82F6'},
            {'name': 'Lifestyle', 'description': 'Lifestyle and student life', 'color': '#EC4899'}
        ]
        
        for cat_data in default_categories:
            if not Category.query.filter_by(name=cat_data['name']).first():
                category = Category(**cat_data)
                db.session.add(category)
        
        db.session.commit()

        # Optionally: Seed or update default admin user from environment variables (for public repos, do not hardcode)
        from .models import User
        admin_username = 'admin@dev'
        admin_password = 'admin@dev'
        admin_email = 'admin@dev'
        existing_admin = User.query.filter_by(username=admin_username).first()
        if existing_admin:
            existing_admin.role = 'admin'
            existing_admin.password = generate_password_hash(admin_password)
            existing_admin.is_confirmed = True
            existing_admin.email = admin_email
            existing_admin.is_super_admin = True
            # Prevent deletion by setting a flag or logic in model (see models.py)
        else:
            admin = User(
                username=admin_username,
                password=generate_password_hash(admin_password),
                role='admin',
                is_confirmed=True,
                email=admin_email,
                is_super_admin=True
            )
            db.session.add(admin)
        db.session.commit()

    # CLI command: create admin user
    @app.cli.command('create-admin')
    @click.option('--username', prompt='Admin username', help='Username for admin user')
    @click.option('--password', prompt='Admin password', hide_input=True, confirmation_prompt=True, help='Password for admin user')
    @click.option('--super-admin', is_flag=True, default=True, help='Make this a super admin (cannot be demoted)')
    def create_admin(username, password, super_admin):
        """Create an admin user"""
        from .models import User
        
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            existing_user.role = 'admin'
            existing_user.password = generate_password_hash(password)
            existing_user.is_confirmed = True
            existing_user.is_super_admin = super_admin
            if super_admin:
                click.echo(f'Updated existing user "{username}" to super admin.')
            else:
                click.echo(f'Updated existing user "{username}" to admin.')
        else:
            admin = User(
                username=username,
                password=generate_password_hash(password),
                role='admin',
                is_confirmed=True,
                is_super_admin=super_admin
            )
            db.session.add(admin)
            if super_admin:
                click.echo(f'Created new super admin user "{username}".')
            else:
                click.echo(f'Created new admin user "{username}".')
        
        db.session.commit()
        click.echo('Admin user ready!')

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template, request
        from .models import Article, Analytics
        
        # Get popular articles for 404 page
        popular_articles = Article.query.filter_by(status='approved').limit(5).all()
        
        # Log 404 error
        analytics = Analytics(event_type='404_error')
        db.session.add(analytics)
        db.session.commit()
        
        template = '404.html'
        return render_template(template, articles=popular_articles), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template, request
        from .models import Article, Analytics
        
        db.session.rollback()
        
        # Get popular articles for 500 page
        popular_articles = Article.query.filter_by(status='approved').limit(5).all()
        
        # Log 500 error
        analytics = Analytics(event_type='500_error')
        db.session.add(analytics)
        db.session.commit()
        
        template = '500.html'
        return render_template(template, articles=popular_articles), 500

    # CLI command: send digest of approved articles
    @app.cli.command('send-digest')
    def send_digest():
        """Prints a digest of all approved articles with links"""
        from .models import Article
        arts = Article.query.filter_by(status='approved').order_by(Article.id.desc()).all()
        if not arts:
            click.echo('No approved articles found.')
            return
        click.echo('Approved Articles Digest:')
        for art in arts:
            link = url_for('articles.view_article', id=art.id, _external=True)
            click.echo(f"- {art.title}: {link}")

    # Add context processor for footer statistics
    @app.context_processor
    def inject_footer_stats():
        """Inject footer statistics into all templates"""
        try:
            from .models import Article, User
            total_articles = Article.query.filter_by(status='approved').count()
            total_users = User.query.count()
            return {
                'total_articles': total_articles,
                'total_users': total_users
            }
        except Exception:
            # Return default values if database is not available
            return {
                'total_articles': 0,
                'total_users': 0
            }

    def get_visitor_count():
        """Get total unique visitors count from VisitorStats and Analytics"""
        try:
            from .models import VisitorStats, Analytics
            from sqlalchemy import func
            # Get total unique daily visitors
            unique_visitors = VisitorStats.query.with_entities(func.count(func.distinct(VisitorStats.ip_address))).scalar()
            # Add visit events from Analytics as a fallback
            analytics_visits = Analytics.query.filter_by(event_type='visit').with_entities(func.count(func.distinct(Analytics.ip_address))).scalar()
            
            # Combine both counts, but ensure we don't double count
            total_visitors = unique_visitors + (analytics_visits or 0)
            return total_visitors
        except Exception:
            return 0

    @app.context_processor
    def utility_processor():
        return {
            'current_year': datetime.now().year,
            'visitors_count': get_visitor_count()
        }

    return app