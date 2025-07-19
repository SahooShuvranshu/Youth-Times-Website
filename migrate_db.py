"""
Database migration script to add new fields to existing tables
"""
from app import create_app, db
from app.models import User, Article
import secrets
import string

def generate_hash_id():
    """Generate a unique hash ID for the article"""
    while True:
        # Generate a 12-character hash using letters and numbers
        hash_id = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        # Ensure it doesn't already exist
        existing = db.session.execute(db.text("SELECT COUNT(*) FROM article WHERE hash_id = :hash_id"), {'hash_id': hash_id}).scalar()
        if existing == 0:
            return hash_id

def migrate_database():
    app = create_app()
    with app.app_context():
        print("Starting database migration...")
        
        try:
            # Check if columns already exist
            inspector = db.inspect(db.engine)
            
            # Get existing columns for user table
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            article_columns = [col['name'] for col in inspector.get_columns('article')]
            
            print(f"Current user columns: {user_columns}")
            print(f"Current article columns: {article_columns}")
            
            # Add missing columns to user table
            if 'date_of_birth' not in user_columns:
                print("Adding date_of_birth column to user table...")
                db.session.execute(db.text("ALTER TABLE user ADD COLUMN date_of_birth DATE"))
                
            if 'gender' not in user_columns:
                print("Adding gender column to user table...")
                db.session.execute(db.text("ALTER TABLE user ADD COLUMN gender VARCHAR(20)"))
            
            # Add missing columns to article table
            if 'hash_id' not in article_columns:
                print("Adding hash_id column to article table...")
                db.session.execute(db.text("ALTER TABLE article ADD COLUMN hash_id VARCHAR(20)"))
                
                # Generate hash_ids for existing articles
                print("Generating hash_ids for existing articles...")
                articles = db.session.execute(db.text("SELECT id FROM article")).fetchall()
                for article in articles:
                    hash_id = generate_hash_id()
                    db.session.execute(db.text("UPDATE article SET hash_id = :hash_id WHERE id = :id"), 
                                     {'hash_id': hash_id, 'id': article[0]})
                
                # Make hash_id unique
                print("Adding unique constraint to hash_id...")
                db.session.execute(db.text("CREATE UNIQUE INDEX idx_article_hash_id ON article(hash_id)"))
            
            db.session.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            print(f"Migration error: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate_database()
