from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from ..models import Article, User, LogEntry, Notification, Analytics, Comment, Newsletter, Category, TickerMessage
from .. import db
from werkzeug.security import generate_password_hash
from .auth import send_email  # import email helper
import logging

bp = Blueprint('admin', __name__)

@bp.route('/admin')
@bp.route('/admin/')
@login_required
def admin_panel():
    logging.info(f"Admin panel access attempt by user '{current_user.username}' with role '{current_user.role}'")
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    # Search and paginate pending articles
    article_search = request.args.get('article_search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    pending_query = Article.query.filter_by(status='pending')
    if article_search:
        pending_query = pending_query.filter(
            (Article.title.ilike(f"%{article_search}%")) |
            (Article.content.ilike(f"%{article_search}%"))
        )
    pending_query = pending_query.order_by(Article.id.desc())
    pag = pending_query.paginate(page=page, per_page=per_page, error_out=False)
    pending = pag.items
    # Search registered users
    user_search = request.args.get('user_search', '')
    user_page = request.args.get('user_page', 1, type=int)
    users_query = User.query
    if user_search:
        users_query = users_query.filter(
            (User.username.ilike(f"%{user_search}%")) |
            (User.role.ilike(f"%{user_search}%"))
        )
    users_pag = users_query.order_by(User.id).paginate(page=user_page, per_page=per_page, error_out=False)
    users = users_pag.items
    # Search in all articles
    all_search = request.args.get('all_search', '')
    all_page = request.args.get('all_page', 1, type=int)
    all_articles_query = Article.query
    if all_search:
        all_articles_query = all_articles_query.filter(
            Article.title.ilike(f"%{all_search}%")
        )
    all_pag = all_articles_query.order_by(Article.id.desc()).paginate(page=all_page, per_page=per_page, error_out=False)
    all_articles = all_pag.items
    # Paginate logs with optional filtering
    log_search = request.args.get('log_search', '')
    log_page = request.args.get('log_page', 1, type=int)
    logs_query = LogEntry.query
    if log_search:
        logs_query = logs_query.filter(LogEntry.action.ilike(f"%{log_search}%"))
    logs_pag = logs_query.order_by(LogEntry.timestamp.desc()).paginate(page=log_page, per_page=per_page, error_out=False)
    logs = logs_pag.items
    return render_template(
        'admin_panel.html',
        articles=pending,
        article_search=article_search,
        users=users,
        user_search=user_search,
        users_pag=users_pag,
        user_page=user_page,
        all_articles=all_articles,
        all_search=all_search,
        all_pag=all_pag,
        all_page=all_page,
        logs=logs,
        pag=pag,
        log_search=log_search,
        logs_pag=logs_pag,
        log_page=log_page
    )

@bp.route('/admin/approve/<string:hash_id>')
@login_required
def approve_article(hash_id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    reason = request.args.get('reason', '')
    article.status = 'approved'

    # Add article title to ticker
    ticker_message = TickerMessage(message=f"NEW ARTICLE: {article.title}")
    db.session.add(ticker_message)

    db.session.commit()
    # Log and notify
    entry = LogEntry(article_id=article.id, action=f"Approved by admin '{current_user.username}'")
    db.session.add(entry)
    notif = Notification(user_id=article.submitted_by, article_id=article.id,
                         message=f"Your article '{article.title}' was approved.{f' Reason: {reason}' if reason else ''}")
    db.session.add(notif)
    db.session.commit()
    flash('Article approved successfully.', 'success')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/ticker', methods=['GET', 'POST'])
@login_required
def manage_ticker():
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    
    if request.method == 'POST':
        message = request.form.get('message')
        if message:
            new_message = TickerMessage(message=message)
            db.session.add(new_message)
            db.session.commit()
            flash('Ticker message added successfully.', 'success')
        return redirect(url_for('admin.manage_ticker'))

    messages = TickerMessage.query.order_by(TickerMessage.created_at.desc()).all()
    return render_template('manage_ticker.html', messages=messages)

@bp.route('/admin/ticker/delete/<int:id>')
@login_required
def delete_ticker_message(id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    
    message = TickerMessage.query.get_or_404(id)
    db.session.delete(message)
    db.session.commit()
    flash('Ticker message deleted successfully.', 'success')
    return redirect(url_for('admin.manage_ticker'))

@bp.route('/admin/reject/<string:hash_id>')
@login_required
def reject_article(hash_id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    reason = request.args.get('reason', '')
    article.status = 'rejected'
    db.session.commit()
    # Log and notify
    entry = LogEntry(article_id=article.id, action=f"Rejected by admin '{current_user.username}'")
    db.session.add(entry)
    notif = Notification(user_id=article.submitted_by, article_id=article.id,
                         message=f"Your article '{article.title}' was rejected.{f' Reason: {reason}' if reason else ''}")
    db.session.add(notif)
    db.session.commit()
    flash('Article rejected successfully.', 'info')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/delete/<string:hash_id>')
@login_required
def delete_article(hash_id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    db.session.delete(article)
    db.session.commit()
    # Record log
    entry = LogEntry(article_id=article.id, action=f"Deleted by admin '{current_user.username}'")
    db.session.add(entry)
    db.session.commit()
    flash('Article deleted successfully.', 'warning')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/edit/<string:hash_id>', methods=['GET', 'POST'])
@login_required
def edit_article(hash_id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    if request.method == 'POST':
        article.title = request.form['title']
        article.content = request.form['content']
        db.session.commit()
        # Record log
        entry = LogEntry(article_id=article.id, action=f"Edited by admin '{current_user.username}'")
        db.session.add(entry)
        db.session.commit()
        flash('Article updated successfully.', 'success')
        return redirect(url_for('admin.admin_panel'))
    return render_template('admin_edit_article.html', article=article)

@bp.route('/admin/delete_user/<int:id>')
@login_required
def delete_user(id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    user = User.query.get_or_404(id)
    # Prevent deletion of admin users and self
    if user.id != current_user.id and user.role != 'admin':
        db.session.delete(user)
        db.session.commit()
        # Record log for user deletion
        entry = LogEntry(action=f"Deleted user '{user.username}' by admin '{current_user.username}'")
        db.session.add(entry)
        db.session.commit()
        flash(f'User {user.username} deleted.', 'warning')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/promote/<int:id>')
@login_required
def promote_user(id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    
    # Only super admins can promote users
    if not current_user.is_super_admin:
        flash('Only super admins can promote users.', 'error')
        return redirect(url_for('admin.admin_panel'))
    
    user = User.query.get_or_404(id)
    
    # Don't promote if already admin
    if user.role == 'admin':
        flash(f'{user.username} is already an admin.', 'info')
        return redirect(url_for('admin.admin_panel'))
    
    # Promote to regular admin (not super admin)
    user.role = 'admin'
    user.is_super_admin = False  # Only CLI/startup can create super admins
    db.session.commit()
    
    # Record promotion log
    entry = LogEntry(action=f"Promoted user '{user.username}' to admin by super admin '{current_user.username}'")
    db.session.add(entry)
    
    # Notify the promoted user
    notif = Notification(user_id=user.id, article_id=None,
                         message=f"Congratulations! You have been promoted to admin by {current_user.username}.")
    db.session.add(notif)
    db.session.commit()
    
    flash(f'User {user.username} promoted to admin.', 'success')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/demote/<int:id>')
@login_required
def demote_user(id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    
    # Only super admins can demote users
    if not current_user.is_super_admin:
        flash('Only super admins can demote users.', 'error')
        return redirect(url_for('admin.admin_panel'))
    
    user = User.query.get_or_404(id)
    
    # Cannot demote yourself
    if user.id == current_user.id:
        flash('You cannot demote yourself.', 'error')
        return redirect(url_for('admin.admin_panel'))
    
    # Cannot demote super admins
    if user.is_super_admin:
        flash(f'Cannot demote {user.username} - super admins cannot be demoted.', 'error')
        return redirect(url_for('admin.admin_panel'))
    
    # Only demote if currently admin
    if user.role != 'admin':
        flash(f'{user.username} is not an admin.', 'info')
        return redirect(url_for('admin.admin_panel'))
    
    # Demote to regular user
    user.role = 'user'
    user.is_super_admin = False
    db.session.commit()
    
    # Record demotion log
    entry = LogEntry(action=f"Demoted admin '{user.username}' to user by super admin '{current_user.username}'")
    db.session.add(entry)
    
    # Notify the demoted user
    notif = Notification(user_id=user.id, article_id=None,
                         message=f"Your admin privileges have been revoked by {current_user.username}.")
    db.session.add(notif)
    db.session.commit()
    
    flash(f'Admin {user.username} demoted to user.', 'warning')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/reset_password/<int:id>')
@login_required
def reset_password(id):
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    
    user = User.query.get_or_404(id)
    
    # Permission checks based on current user role
    if current_user.is_super_admin:
        # Super admin can reset anyone's password (users, admins, other super admins)
        can_reset = True
    elif current_user.role == 'admin' and not current_user.is_super_admin:
        # Regular admin can only reset regular user passwords
        if user.role == 'admin' or user.is_super_admin:
            flash(f'Cannot reset password for {user.username} - admins can only reset regular user passwords.', 'error')
            return redirect(url_for('admin.admin_panel'))
        can_reset = True
    else:
        can_reset = False
    
    if not can_reset:
        flash('You do not have permission to reset passwords.', 'error')
        return redirect(url_for('admin.admin_panel'))
    
    # Cannot reset your own password through admin panel
    if user.id == current_user.id:
        flash('You cannot reset your own password through the admin panel. Use the profile settings.', 'error')
        return redirect(url_for('admin.admin_panel'))
    
    # Generate a more secure temporary password
    import secrets
    import string
    temp_pw = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    
    user.password = generate_password_hash(temp_pw)
    db.session.commit()
    
    # Record password reset log
    entry = LogEntry(action=f"Reset password for '{user.username}' by '{current_user.username}' ({current_user.role})")
    db.session.add(entry)
    
    # Notify the user
    notif = Notification(user_id=user.id, article_id=None,
                         message=f"Your password has been reset by {current_user.username}. Temporary password: {temp_pw}. Please log in and change it immediately.")
    db.session.add(notif)
    
    # Send email notification if user has email
    if user.email:
        try:
            send_email(user.email, 'Password Reset Notification',
                       f"Your password has been reset by an administrator. Temporary password: {temp_pw}. Please log in and change it immediately for security.")
        except Exception as e:
            logging.warning(f"Failed to send password reset email to {user.email}: {e}")
    
    db.session.commit()
    
    # Show different messages based on who reset the password
    role_text = "super admin" if current_user.is_super_admin else "admin"
    flash(f"Password for {user.username} reset successfully. Temporary password: {temp_pw}. User has been notified.", 'success')
    return redirect(url_for('admin.admin_panel'))

@bp.route('/admin/analytics')
@login_required
def analytics_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('articles.home'))
    
    # Get analytics data
    total_articles = Article.query.count()
    total_users = User.query.count()
    total_views = Analytics.query.filter_by(event_type='view').count()
    total_comments = Comment.query.count()
    newsletter_subscribers = Newsletter.query.filter_by(is_active=True).count()
    
    # Most viewed articles
    from sqlalchemy import func
    most_viewed = db.session.query(
        Article.id, Article.title, func.count(Analytics.id).label('views')
    ).join(Analytics, Article.id == Analytics.article_id)\
    .filter(Analytics.event_type == 'view')\
    .group_by(Article.id, Article.title)\
    .order_by(func.count(Analytics.id).desc())\
    .limit(10).all()
    
    # Recent activity (last 30 days)
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_views = Analytics.query.filter(
        Analytics.event_type == 'view',
        Analytics.timestamp >= thirty_days_ago
    ).count()
    
    # Category breakdown
    category_stats = db.session.query(
        Category.name, func.count(Article.id).label('article_count')
    ).join(Article, Category.id == Article.category_id)\
    .filter(Article.status == 'approved')\
    .group_by(Category.name).all()
    
    return render_template('analytics_dashboard.html',
                         total_articles=total_articles,
                         total_users=total_users,
                         total_views=total_views,
                         total_comments=total_comments,
                         newsletter_subscribers=newsletter_subscribers,
                         most_viewed=most_viewed,
                         recent_views=recent_views,
                         category_stats=category_stats)
