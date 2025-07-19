"""
Quick test to check current admin users and fix login issues
"""
from app import create_app, db
from app.models import User

def check_admin():
    app = create_app()
    with app.app_context():
        print("Checking for existing admin users...")
        
        # Check all users
        users = User.query.all()
        print(f"Total users in database: {len(users)}")
        
        for user in users:
            print(f"- {user.username} (role: {user.role}, super_admin: {user.is_super_admin}, confirmed: {user.is_confirmed})")
        
        # Check for admin users
        admin_users = User.query.filter_by(role='admin').all()
        super_admins = User.query.filter_by(is_super_admin=True).all()
        
        print(f"\nAdmin users: {len(admin_users)}")
        print(f"Super admin users: {len(super_admins)}")

if __name__ == '__main__':
    check_admin()
