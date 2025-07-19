from app import create_app
from app.models import User
from app import db
from werkzeug.security import generate_password_hash
import logging
import os

app = create_app()

def setup_super_admin():
    """Setup super admin user if none exists"""
    with app.app_context():
        # Check if any super admin exists
        existing_super_admin = User.query.filter_by(is_super_admin=True).first()
        
        if not existing_super_admin:
            print("\n" + "="*60)
            print("🚀 YOUTH TIMES PROJECT - AUTOMATIC SETUP")
            print("="*60)
            print("No super admin found. Creating default admin...")
            print("-"*60)
            
            # Create default super admin user
            super_admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                role='admin',
                is_super_admin=True,
                is_confirmed=True,
                name='Super Admin'
            )
            
            db.session.add(super_admin)
            db.session.commit()
            
            print("-"*60)
            print("✅ Default super admin created successfully!")
            print(f"👤 Username: admin")
            print(f"🔐 Password: admin123")
            print("-"*60)
            print("📋 IMPORTANT NOTES:")
            print("• This super admin cannot be demoted by anyone")
            print("• Please change the password after first login")
            print("• You can create more admins from the admin panel")
            print("-"*60)
            print("🌐 Your application is ready to use!")
            print("="*60)
            print()
        else:
            print(f"✅ Super admin '{existing_super_admin.username}' already exists.")

# Print all registered routes for debugging admin endpoints
logger = logging.getLogger('werkzeug')
logger.setLevel(logging.DEBUG)
print("Registered routes:")
for rule in app.url_map.iter_rules():
    print(f"{rule.rule} -> {rule.endpoint}")

if __name__ == '__main__':
    # Check if admin exists, if not create a default one
    with app.app_context():
        existing_super_admin = User.query.filter_by(is_super_admin=True).first()
        if not existing_super_admin:
            # Create default admin for testing
            default_admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                role='admin',
                is_super_admin=True,
                is_confirmed=True,
                name='Default Admin'
            )
            db.session.add(default_admin)
            db.session.commit()
            print("✅ Default admin created: username=admin, password=admin123")
        else:
            print(f"✅ Admin user '{existing_super_admin.username}' exists")
    
    print("\n🚀 Starting Youth Times Project...")
    print("📍 Access your application at: http://127.0.0.1:5000")
    print("🔧 Admin Panel: http://127.0.0.1:5000/admin")
    print("-"*60)
    
    app.run(debug=True)
