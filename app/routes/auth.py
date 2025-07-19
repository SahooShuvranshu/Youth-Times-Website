from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from .. import db, login_manager, oauth  # import oauth
from ..models import User, Article
import logging
import os
import smtplib
from email.mime.text import MIMEText
import itsdangerous
from itsdangerous import URLSafeTimedSerializer
from flask import current_app, abort

bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def send_email(to_address, subject, body):
    """Send email with proper error handling"""
    try:
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = os.getenv('SMTP_PORT')
        smtp_user = os.getenv('SMTP_USERNAME')
        smtp_pass = os.getenv('SMTP_PASSWORD')
        from_address = os.getenv('EMAIL_SENDER')
        
        if not all([smtp_server, smtp_port, smtp_user, smtp_pass, from_address]):
            print("Email configuration missing. Email not sent.")
            return False
            
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = from_address
        msg['To'] = to_address
        
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# Helpers for email confirmation
def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=current_app.config.get('SECURITY_PASSWORD_SALT'))

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt=current_app.config.get('SECURITY_PASSWORD_SALT'),
            max_age=expiration
        )
    except itsdangerous.exc.BadSignature:
        return False
    return email

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form.get('email')
        password = request.form['password']
        
        # Validation
        if not email:
            flash('Email is required.', 'warning')
            return render_template('register.html')
        
        if not username or not password:
            flash('Username and password are required.', 'warning')
            return render_template('register.html')
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'warning')
            return render_template('register.html')
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'warning')
            return render_template('register.html')
        
        # Create new user
        hashed_password = generate_password_hash(password)
        user = User(username=username, password=hashed_password, email=email)
        
        try:
            db.session.add(user)
            db.session.commit()
            
            # Check if email is configured
            if os.getenv('SMTP_USERNAME') and os.getenv('SMTP_PASSWORD'):
                # Send confirmation email
                token = generate_confirmation_token(user.email)
                confirm_url = url_for('auth.confirm_email', token=token, _external=True)
                
                email_body = f"""
                Welcome to Youth Times!
                
                Please click the following link to confirm your email address:
                {confirm_url}
                
                This link will expire in 1 hour.
                
                If you didn't create this account, please ignore this email.
                """
                
                if send_email(user.email, 'Confirm Your Account - Youth Times', email_body):
                    flash('Registration successful! Please check your email to confirm your account before logging in.', 'success')
                else:
                    flash('Registration successful, but we couldn\'t send the confirmation email. Please contact support.', 'warning')
            else:
                # Auto-confirm if email not configured (development mode)
                user.is_confirmed = True
                db.session.commit()
                flash('Registration successful! You can now log in. (Email confirmation disabled in development)', 'success')
            
            return redirect(url_for('auth.login'))
            
        except IntegrityError:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'danger')
            return render_template('register.html')
    
    return render_template('register.html')

@bp.route('/confirm/<token>')
def confirm_email(token):
    """Confirm email address with token"""
    email = confirm_token(token)
    if not email:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))
    
    if user.is_confirmed:
        flash('Account already confirmed. Please login.', 'info')
        return redirect(url_for('auth.login'))
    
    # Confirm the user
    user.is_confirmed = True
    db.session.commit()
    
    flash('Your account has been confirmed! You can now log in.', 'success')
    return render_template('email_confirmed.html')

# Google OAuth routes
@bp.route('/login/google')
def google_login():
    """Initiate Google OAuth login"""
    try:
        redirect_uri = url_for('auth.google_callback', _external=True)
        return oauth.google.authorize_redirect(redirect_uri)
    except Exception as e:
        flash('Google login is not configured properly.', 'danger')
        return redirect(url_for('auth.login'))

@bp.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            flash('Failed to get user information from Google.', 'danger')
            return redirect(url_for('auth.login'))
        
        email = user_info.get('email')
        if not email:
            flash('Email not provided by Google.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Create new user
            username = email.split('@')[0]  # Use email prefix as username
            # Ensure username is unique
            counter = 1
            original_username = username
            while User.query.filter_by(username=username).first():
                username = f"{original_username}{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=email,
                name=user_info.get('name', ''),
                profile_image=user_info.get('picture', ''),
                password=generate_password_hash(os.urandom(16).hex()),  # Random password
                is_confirmed=True  # Google accounts are pre-verified
            )
            db.session.add(user)
            db.session.commit()
            flash('Account created successfully with Google!', 'success')
        else:
            # Update user info from Google
            user.name = user_info.get('name', user.name)
            user.profile_image = user_info.get('picture', user.profile_image)
            user.is_confirmed = True
            db.session.commit()
        
        login_user(user)
        flash('Successfully logged in with Google!', 'success')
        
        # Redirect based on user role
        if user.role == 'admin':
            return redirect(url_for('admin.admin_panel'))
        return redirect(url_for('articles.home'))
        
    except Exception as e:
        flash('An error occurred during Google authentication.', 'danger')
        return redirect(url_for('auth.login'))

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            # Check if email is confirmed (skip for admin and Google users)
            if not user.is_confirmed and user.role != 'admin':
                flash('Please confirm your email address before logging in. Check your email for the confirmation link.', 'warning')
                return render_template('login.html')
            
            login_user(user)
            logging.info(f"User '{user.username}' logged in successfully; role: {user.role}")
            
            # Handle 'next' parameter for protected routes
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            
            # Default redirects based on role
            if user.role == 'admin':
                return redirect(url_for('admin.admin_panel'))
            return redirect(url_for('articles.home'))
        else:
            flash("Invalid username or password.", 'danger')
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST' and 'update_profile' in request.form:
        current_user.name = request.form.get('name')
        current_user.bio = request.form.get('bio')
        current_user.email = request.form.get('email')
        current_user.profile_image = request.form.get('profile_image')
        current_user.location = request.form.get('location')
        current_user.website = request.form.get('website')
        current_user.gender = request.form.get('gender')
        
        # Handle Date of Birth
        dob_str = request.form.get('date_of_birth')
        if dob_str:
            from datetime import datetime
            try:
                current_user.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format.', 'danger')
                return redirect(url_for('auth.profile'))
        else:
            current_user.date_of_birth = None
        
        # Handle file upload (if implemented)
        # For now, we'll use the profile_image URL field
        
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('auth.profile'))
    # GET or no profile update, show profile
    user = current_user
    articles = Article.query.filter_by(submitted_by=user.id).order_by(Article.id.desc()).all()
    return render_template('profile.html', user=user, articles=articles)

@bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    old = request.form.get('old_password')
    new = request.form.get('new_password')
    confirm = request.form.get('confirm_password')
    if not check_password_hash(current_user.password, old):
        flash('Current password is incorrect.', 'danger')
    elif new != confirm:
        flash('New passwords do not match.', 'danger')
    else:
        current_user.password = generate_password_hash(new)
        db.session.commit()
        # send email notification
        if current_user.email:
            send_email(current_user.email, 'Your password has changed',
                       'Your password was changed successfully.')
        flash('Password changed successfully.', 'success')
    return redirect(url_for('auth.profile'))

@bp.route('/resend-confirmation')
def resend_confirmation():
    """Resend email confirmation"""
    username = request.args.get('username')
    if not username:
        flash('Username is required.', 'warning')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.login'))
    
    if user.is_confirmed:
        flash('Account already confirmed.', 'info')
        return redirect(url_for('auth.login'))
    
    # Generate and send new confirmation token
    token = generate_confirmation_token(user.email)
    confirm_url = url_for('auth.confirm_email', token=token, _external=True)
    
    email_body = f"""
    Confirmation Email Resent
    
    Please click the following link to confirm your email address:
    {confirm_url}
    
    This link will expire in 1 hour.
    """
    
    if send_email(user.email, 'Confirm Your Account - Youth Times', email_body):
        flash('Confirmation email has been resent. Please check your email.', 'success')
    else:
        flash('Failed to send confirmation email. Please try again later.', 'danger')
    
    return redirect(url_for('auth.login'))

@bp.route('/test-email')
def test_email():
    """Test route to verify email configuration"""
    if not current_user.is_authenticated or current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('auth.login'))
    
    test_email_addr = os.getenv('SMTP_USERNAME')
    if not test_email_addr:
        flash('Email not configured.', 'warning')
        return redirect(url_for('admin.admin_panel'))
    
    subject = 'Test Email - Youth Times'
    body = '''
    This is a test email from your Youth Times application.
    
    If you receive this email, your SMTP configuration is working correctly!
    
    Sent at: ''' + str(db.func.now())
    
    if send_email(test_email_addr, subject, body):
        flash(f'Test email sent successfully to {test_email_addr}!', 'success')
    else:
        flash('Failed to send test email. Check your SMTP configuration.', 'danger')
    
    return redirect(url_for('admin.admin_panel'))
