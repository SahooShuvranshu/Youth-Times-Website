from flask import Blueprint, render_template, request, redirect, flash, current_app, url_for, Response, session
import logging
import threading
from xml.sax.saxutils import escape
import os
import cloudinary
import cloudinary.uploader
from werkzeug.utils import secure_filename
import markdown
import bleach
from markdown.extensions import codehilite, tables, fenced_code

from flask_login import login_required, current_user
from .. import db
from ..models import Article, LogEntry, Notification, User, Category, Comment, Newsletter, Analytics, TickerMessage
from ..scraper import verify_article

# Configure logging
logging.basicConfig(level=logging.INFO)

# Configure Cloudinary (for image uploads)
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

bp = Blueprint('articles', __name__)

def process_article_content(content):
    """Process article content to support both Markdown and HTML safely"""
    try:
        # Configure allowed HTML tags and attributes
        allowed_tags = [
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'code', 'pre', 'span', 'div',
            'table', 'thead', 'tbody', 'tr', 'th', 'td'
        ]
        
        allowed_attributes = {
            'a': ['href', 'title', 'target'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'span': ['class'],
            'div': ['class'],
            'table': ['class'],
            'th': ['class'],
            'td': ['class']
        }
        
        # First, convert Markdown to HTML
        md = markdown.Markdown(extensions=[
            'fenced_code',
            'tables',
            'nl2br',
            'codehilite'
        ])
        html_content = md.convert(content)
        
        # Then sanitize the HTML to prevent XSS
        clean_content = bleach.clean(
            html_content, 
            tags=allowed_tags, 
            attributes=allowed_attributes,
            strip=True
        )
        
        return clean_content
        
    except Exception as e:
        # Fallback to simple HTML escaping if markdown processing fails
        logging.warning(f"Markdown processing failed: {e}")
        return bleach.clean(content, tags=['p', 'br', 'strong', 'em'], strip=True)

def create_excerpt(html_content, max_length=200):
    """Create a plain text excerpt from HTML content"""
    try:
        # Remove HTML tags to get plain text
        text = bleach.clean(html_content, tags=[], strip=True)
        # Clean up extra whitespace
        text = ' '.join(text.split())
        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + '...'
        return text
    except Exception:
        return html_content[:max_length] + '...' if len(html_content) > max_length else html_content

@bp.route('/')
def home():
    # Get articles with categories for better display
    articles = Article.query.filter_by(status='approved').order_by(Article.created_at.desc()).limit(10).all()
    categories = Category.query.all()
    ticker_messages = TickerMessage.query.order_by(TickerMessage.created_at.desc()).all()
    
    # Get featured article (most viewed)
    featured_article = None
    if articles:
        # Get article with most views
        view_counts = {}
        for article in articles:
            view_count = Analytics.query.filter_by(article_id=article.id, event_type='view').count()
            view_counts[article.id] = view_count
        
        if view_counts:
            featured_article_id = max(view_counts, key=view_counts.get)
            featured_article = Article.query.get(featured_article_id)

    # Track unique homepage visits
    if 'visited_homepage' not in session:
        # This is a new visit
        new_visit = Analytics(event_type='homepage_view')
        db.session.add(new_visit)
        db.session.commit()
        session['visited_homepage'] = True

    # Get total unique homepage visits
    total_visits = Analytics.query.filter_by(event_type='homepage_view').count()

    return render_template(
        'home.html', 
        articles=articles, 
        categories=categories, 
        featured_article=featured_article,
        total_visits=total_visits,
        ticker_messages=ticker_messages
    )

@bp.route('/submit', methods=['GET', 'POST'])
@login_required
def submit_article():
    if request.method == 'POST':
        title = request.form['title']
        raw_content = request.form['content']
        category_id = request.form.get('category_id') or None
        tags = request.form.get('tags', '').strip()
        image_url = None
        
        # Process content to support Markdown and HTML
        processed_content = process_article_content(raw_content)
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                try:
                    # Upload to Cloudinary
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="youth_times/articles",
                        transformation=[{'width': 800, 'height': 600, 'crop': 'limit'}]
                    )
                    image_url = upload_result['secure_url']
                except Exception as e:
                    flash(f'Image upload failed: {str(e)}', 'warning')
        
        # Store submission immediately with pending status
        article = Article(
            title=title,
            content=processed_content,  # Use processed content
            status='pending',
            trust_score=None,
            submitted_by=current_user.id,
            category_id=category_id,
            tags=tags,
            image_url=image_url
        )
        db.session.add(article)
        db.session.commit()
        
        # Track analytics
        analytics = Analytics(
            article_id=article.id,
            event_type='submit',
            user_id=current_user.id,
            ip_address=request.remote_addr
        )
        db.session.add(analytics)
        db.session.commit()
        
        flash("Article submitted successfully. Authenticity check is running in the background.")
        # Background thread to verify trust score and apply threshold
        # Capture the Flask app for use in the thread
        app_ctx = current_app._get_current_object()
        def _background_verify(article_id, app):
            with app.app_context():
                art = Article.query.get(article_id)
                if not art:
                    return
                score = verify_article(art.title, art.content)
                if score < 50:
                    # Auto-delete low-trust articles
                    db.session.delete(art)
                    db.session.commit()
                    # Log deletion action and notify user
                    entry = LogEntry(article_id=article_id, action=f"Auto-deleted (trust {score}%)")
                    db.session.add(entry)
                    db.session.commit()
                    notif = Notification(user_id=art.submitted_by, article_id=article_id,
                                           message=f"Your article '{art.title}' was automatically deleted (trust {score}%).")
                    db.session.add(notif)
                    db.session.commit()
                    logging.info(f"Article ID {article_id} automatically discarded (trust {score}%).")
                else:
                    art.trust_score = score
                    db.session.commit()
                    # Log pending action and notify user
                    entry = LogEntry(article_id=article_id, action=f"Marked pending (trust {score}%)")
                    db.session.add(entry)
                    notif = Notification(user_id=art.submitted_by, article_id=article_id,
                                           message=f"Your article '{art.title}' passed authenticity check (trust {score}%) and is pending approval.")
                    db.session.add(notif)
                    db.session.commit()
                    logging.info(f"Article ID {article_id} marked pending with trust {score}%.")
        threading.Thread(target=_background_verify, args=(article.id, app_ctx), daemon=True).start()
        flash("Article submitted. Authenticity check running in background. You can view your submission below.")
        return redirect(url_for('articles.view_article', id=article.id))
    
    # GET request - show form with categories
    categories = Category.query.all()
    return render_template('submit_article.html', categories=categories)

@bp.route('/article/<int:id>')
def view_article(id):
    article = Article.query.get_or_404(id)
    
    # Track page view
    analytics = Analytics(
        article_id=article.id,
        event_type='view',
        user_id=current_user.id if current_user.is_authenticated else None,
        ip_address=request.remote_addr
    )
    db.session.add(analytics)
    db.session.commit()
    
    # Get approved comments
    comments = Comment.query.filter_by(article_id=id, is_approved=True).order_by(Comment.created_at.desc()).all()
    
    return render_template('article_detail.html', article=article, comments=comments)

@bp.route('/article/<int:id>/comment', methods=['POST'])
@login_required
def add_comment(id):
    article = Article.query.get_or_404(id)
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('Comment cannot be empty.', 'warning')
        return redirect(url_for('articles.view_article', id=id))
    
    comment = Comment(
        content=content,
        article_id=id,
        user_id=current_user.id,
        is_approved=False  # Comments need approval
    )
    db.session.add(comment)
    db.session.commit()
    
    # Track comment analytics
    analytics = Analytics(
        article_id=id,
        event_type='comment',
        user_id=current_user.id,
        ip_address=request.remote_addr
    )
    db.session.add(analytics)
    db.session.commit()
    
    flash('Comment submitted for approval.', 'success')
    return redirect(url_for('articles.view_article', id=id))

@bp.route('/newsletter/subscribe', methods=['POST'])
def subscribe_newsletter():
    email = request.form.get('email', '').strip()
    
    if not email:
        flash('Email is required.', 'warning')
        return redirect(url_for('articles.home'))
    
    # Check if already subscribed
    existing = Newsletter.query.filter_by(email=email).first()
    if existing:
        if existing.is_active:
            flash('You are already subscribed to our newsletter.', 'info')
        else:
            existing.is_active = True
            db.session.commit()
            flash('Welcome back! Your newsletter subscription has been reactivated.', 'success')
    else:
        newsletter = Newsletter(email=email)
        db.session.add(newsletter)
        db.session.commit()
        flash('Successfully subscribed to our newsletter!', 'success')
    
    return redirect(url_for('articles.home'))

@bp.route('/share/<int:id>/<platform>')
def share_article(id, platform):
    article = Article.query.get_or_404(id)
    
    # Track share analytics
    analytics = Analytics(
        article_id=id,
        event_type=f'share_{platform}',
        user_id=current_user.id if current_user.is_authenticated else None,
        ip_address=request.remote_addr
    )
    db.session.add(analytics)
    db.session.commit()
    
    article_url = url_for('articles.view_article', id=id, _external=True)
    
    share_urls = {
        'twitter': f"https://twitter.com/intent/tweet?text={article.title}&url={article_url}",
        'facebook': f"https://www.facebook.com/sharer/sharer.php?u={article_url}",
        'linkedin': f"https://www.linkedin.com/sharing/share-offsite/?url={article_url}",
        'whatsapp': f"https://wa.me/?text={article.title} {article_url}"
    }
    
    if platform in share_urls:
        return redirect(share_urls[platform])
    
    return redirect(url_for('articles.view_article', id=id))

@bp.route('/rss')
def rss_feed():
    """
    Generate an RSS feed of latest approved articles.
    """
    articles = Article.query.filter_by(status='approved').order_by(Article.id.desc()).all()
    items = ''
    for art in articles:
        link = request.url_root.rstrip('/') + url_for('articles.view_article', id=art.id)
        items += f"""
        <item>
            <title>{escape(art.title)}</title>
            <link>{link}</link>
            <description>{escape(art.content)}</description>
        </item>
        """
    rss = f"""<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>Youth Times RSS</title>
        <link>{request.url_root}</link>
        <description>Latest approved articles</description>
        {items}
      </channel>
    </rss>"""
    return Response(rss, mimetype='application/rss+xml')
# Route to view user notifications
@bp.route('/notifications')
@login_required
def notifications():
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
    # Mark all as read
    for n in notes:
        n.is_read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notes)
@bp.route('/search')
def search():
    q = request.args.get('q', '')
    results = []
    if q:
        results = Article.query.filter(Article.status=='approved')
        results = results.filter(
            (Article.title.ilike(f"%{q}%")) | (Article.content.ilike(f"%{q}%"))
        ).all()
    return render_template('search_results.html', query=q, results=results)

@bp.route('/category/<int:category_id>')
def category_articles(category_id):
    category = Category.query.get_or_404(category_id)
    articles = Article.query.filter_by(status='approved', category_id=category_id).order_by(Article.created_at.desc()).all()
    return render_template('category_articles.html', articles=articles, category=category)

@bp.route('/articles')
def articles_list():
    """Articles listing page with all published articles"""
    try:
        # Get all approved articles with pagination
        page = request.args.get('page', 1, type=int)
        per_page = 12  # Show 12 articles per page
        
        articles = Article.query.filter_by(status='approved').order_by(Article.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        categories = Category.query.all()
        
        # Track page visit for analytics
        analytics = Analytics(
            event_type='articles_page_view',
            user_id=current_user.id if current_user.is_authenticated else None,
            ip_address=request.remote_addr
        )
        db.session.add(analytics)
        db.session.commit()
        
        return render_template('articles.html', 
                             articles=articles.items,
                             pagination=articles,
                             categories=categories)
    except Exception as e:
        current_app.logger.error(f"Error in articles_list route: {str(e)}")
        flash('Error loading articles page. Please try again later.', 'error')
        return redirect(url_for('articles.home'))

@bp.route('/about')
def about_us():
    """About Us page showing team members, college, and internship information"""
    try:
        # Team members data
        team_members = [
            {
                'name': 'Rajesh Kumar',
                'role': 'Lead Developer & Project Manager',
                'bio': 'Computer Science student passionate about web development and news technology. Leads the technical development of Youth Times.',
                'image': 'team/rajesh.jpg',
                'skills': ['Python', 'Flask', 'JavaScript', 'Database Design']
            },
            {
                'name': 'Priya Sharma',
                'role': 'Frontend Developer & UI/UX Designer',
                'bio': 'Creative designer focused on user experience and responsive web design. Ensures Youth Times looks great on all devices.',
                'image': 'team/priya.jpg',
                'skills': ['HTML/CSS', 'JavaScript', 'UI/UX Design', 'Responsive Design']
            },
            {
                'name': 'Arjun Patel',
                'role': 'Backend Developer & Database Administrator',
                'bio': 'Database enthusiast and backend specialist. Manages the technical infrastructure and data architecture of Youth Times.',
                'image': 'team/arjun.jpg',
                'skills': ['Python', 'SQLAlchemy', 'Database Design', 'API Development']
            },
            {
                'name': 'Sneha Reddy',
                'role': 'Content Manager & QA Tester',
                'bio': 'Journalism student with a passion for digital media. Ensures content quality and tests all features thoroughly.',
                'image': 'team/sneha.jpg',
                'skills': ['Content Writing', 'Quality Assurance', 'Social Media', 'Editorial']
            },
            {
                'name': 'Vikram Singh',
                'role': 'Data Analyst & Algorithm Developer',
                'bio': 'Data science enthusiast who developed the credibility scoring algorithm and analytics features for Youth Times.',
                'image': 'team/vikram.jpg',
                'skills': ['Python', 'Data Analysis', 'Machine Learning', 'Statistics']
            },
            {
                'name': 'Anita Gupta',
                'role': 'Marketing & User Research Specialist',
                'bio': 'Business student focused on user research and digital marketing. Helps understand user needs and promote Youth Times.',
                'image': 'team/anita.jpg',
                'skills': ['Market Research', 'Digital Marketing', 'User Research', 'Social Media Strategy']
            }
        ]

        # College information
        college_info = {
            'name': 'Nilachal Polytechnic',
            'location': 'Bhubaneswar, Odisha, India',
            'description': 'A premier technical institution known for excellence in engineering and computer science education.',
            'established': '1985',
            'specialties': ['Computer Science', 'Electronics', 'Mechanical Engineering', 'Civil Engineering'],
            'website': 'https://www.nilachalpolytechnic.ac.in/',
            'image': 'college/nilachal_campus.jpg'
        }

        # Internship information
        internship_info = {
            'company': 'OKCL (Odisha Knowledge Corporation Limited)',
            'program': 'Python Development Internship',
            'duration': '6 months',
            'description': 'Comprehensive internship program focusing on real-world Python development, web technologies, and project management.',
            'skills_learned': [
                'Python Programming',
                'Flask Web Framework',
                'Database Design & Management',
                'Frontend Development',
                'Project Management',
                'Team Collaboration',
                'Agile Development'
            ],
            'project_goal': 'Develop a modern, responsive news platform with advanced features like credibility scoring, weather integration, and user management.',
            'website': 'https://okcl.org/',
            'image': 'internship/okcl_office.jpg'
        }

        return render_template('about_us.html', 
                             team_members=team_members,
                             college_info=college_info,
                             internship_info=internship_info)
    except Exception as e:
        current_app.logger.error(f"Error in about_us route: {str(e)}")
        flash('Error loading About Us page. Please try again later.', 'error')
        return redirect(url_for('articles.home'))

@bp.route('/editorial-guidelines')
def editorial_guidelines():
    return render_template('editorial_guidelines.html')

@bp.route('/contact')
def contact():
    return render_template('contact.html')

@bp.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@bp.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@bp.route('/dmca-policy')
def dmca_policy():
    return render_template('dmca_policy.html')
