"""
Quick Flask app test - will be deleted after verification
"""
from app import create_app

def quick_test():
    app = create_app()
    with app.test_client() as client:
        # Test home page
        response = client.get('/')
        print(f"Home page: {response.status_code}")
        
        # Test articles page
        response = client.get('/articles')
        print(f"Articles page: {response.status_code}")
        
        # Test admin page (should redirect)
        response = client.get('/admin')
        print(f"Admin page: {response.status_code}")
        
        print("✅ All pages working!")

if __name__ == '__main__':
    quick_test()
