"""
Route test - check if our routes work correctly
"""
from app import create_app

def test_routes():
    app = create_app()
    
    print("Testing routes configuration...")
    
    with app.test_client() as client:
        # Test home page
        try:
            response = client.get('/')
            print(f"Home page: {response.status_code}")
        except Exception as e:
            print(f"Home page error: {e}")
        
        # Test login page
        try:
            response = client.get('/login')
            print(f"Login page: {response.status_code}")
        except Exception as e:
            print(f"Login page error: {e}")
        
        # Test profile page (should redirect to login)
        try:
            response = client.get('/profile')
            print(f"Profile page: {response.status_code}")
        except Exception as e:
            print(f"Profile page error: {e}")
        
        # Test user profile page
        try:
            response = client.get('/user/admin@dev')
            print(f"User profile page: {response.status_code}")
        except Exception as e:
            print(f"User profile page error: {e}")

if __name__ == '__main__':
    test_routes()
