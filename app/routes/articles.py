from flask import Blueprint, render_template, request, redirect, flash, current_app, url_for, Response, session, jsonify
import logging
import threading
import re
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
from ..models import Article, LogEntry, Notification, User, Category, Comment, Newsletter, Analytics, TickerMessage, Like
from ..scraper import calculate_credibility_score
from ..weather import WeatherService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Profanity and threat detection lists
PROFANITY_WORDS = [
    'fuck', 'shit', 'damn', 'bitch', 'asshole', 'bastard', 'crap', 'piss', 
    'hell', 'whore', 'slut', 'dickhead', 'motherfucker', 'cock', 'pussy',
    'nigger', 'faggot', 'retard', 'spic', 'chink', 'kike', 'wetback'
]

THREAT_WORDS = [
    'kill', 'murder', 'death', 'die', 'bomb', 'shoot', 'gun', 'knife',
    'attack', 'hurt', 'harm', 'violence', 'threat', 'destroy', 'eliminate',
    'assassinate', 'terrorize', 'torture', 'beat up', 'stab', 'poison'
]

def contains_inappropriate_content(text):
    """Check if text contains profanity or threats"""
    text_lower = text.lower()
    
    # Check for profanity
    for word in PROFANITY_WORDS:
        if word in text_lower:
            return True, "profanity"
    
    # Check for threats
    for word in THREAT_WORDS:
        if word in text_lower:
            return True, "threat"
    
    return False, None

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

bp = Blueprint('articles', __name__)

@bp.route('/dmca-policy')
def dmca_policy():
    return render_template('dmca_policy.html')

@bp.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@bp.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@bp.route('/editorial-guidelines')
def editorial_guidelines():
    return render_template('editorial_guidelines.html')

@bp.route('/contact-us')
def contact_us():
    return render_template('contact_us.html')

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

def is_mobile_device():
    """Detect if user is on mobile device"""
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_patterns = [
        r'mobile', r'android', r'iphone', r'ipad', 
        r'tablet', r'phone', r'blackberry', r'opera mini'
    ]
    return any(re.search(pattern, user_agent) for pattern in mobile_patterns)

@bp.route('/')
def home():
    # Mobile redirect logic removed to prevent BuildError
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

    # Get weather data for Bhubaneswar (Youth Times location)
    weather_data = WeatherService.get_weather_widget_data('Bhubaneswar')

    return render_template(
        'home.html', 
        articles=articles, 
        categories=categories, 
        featured_article=featured_article,
        total_visits=total_visits,
        ticker_messages=ticker_messages,
        weather_data=weather_data
    )

@bp.route('/submit', methods=['GET', 'POST'])
@login_required
def submit_article():
    if request.method == 'POST':
        title = request.form['title']
        raw_content = request.form.get('content') or ''
        if not raw_content.strip():
            flash('Article content cannot be empty.', 'warning')
            categories = Category.query.all()
            return render_template('submit_article.html', categories=categories)
        category_id = request.form.get('category_id') or None
        tags = request.form.get('tags', '').strip()
        image_url = None
        
        # Process content to support Markdown and HTML
        processed_content = process_article_content(raw_content)
        import logging
        logging.warning(f"RAW CONTENT: '{raw_content}'")
        logging.warning(f"PROCESSED CONTENT: '{processed_content}'")
        if not processed_content.strip():
            flash('Article content cannot be empty after processing.', 'warning')
            categories = Category.query.all()
            return render_template('submit_article.html', categories=categories)
        
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
            credibility_score=None,
            submitted_by=current_user.id,
            author_id=current_user.id,  # Set author_id for proper relationship
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
                score = calculate_credibility_score(art.title, art.content)
                
                # Save credibility score for all articles
                art.credibility_score = score
                db.session.commit()
                
                # Log the credibility score calculation
                entry = LogEntry(article_id=article_id, action=f"Credibility score calculated: {score}%")
                db.session.add(entry)
                db.session.commit()
                
                # Notify user about credibility analysis
                notif = Notification(user_id=art.submitted_by, article_id=article_id,
                                       message=f"Your article '{art.title}' has been analyzed. Credibility score: {score}%")
                db.session.add(notif)
                db.session.commit()
                
                logging.info(f"Article ID {article_id} submitted with credibility score {score}% - pending admin review.")
        threading.Thread(target=_background_verify, args=(article.id, app_ctx), daemon=True).start()
        flash("Article submitted successfully. Credibility analysis running in background. All articles await admin approval.")
        return redirect(url_for('articles.view_article', hash_id=article.hash_id))
    
    # GET request - show form with categories
    categories = Category.query.all()
    return render_template('submit_article.html', categories=categories)

@bp.route('/article/<string:hash_id>')
def view_article(hash_id):
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    
    # Track page view
    analytics = Analytics(
        article_id=article.id,
        event_type='view',
        user_id=current_user.id if current_user.is_authenticated else None,
        ip_address=request.remote_addr
    )
    db.session.add(analytics)
    db.session.commit()
    
    # Get non-deleted comments
    comments = Comment.query.filter_by(article_id=article.id, is_deleted=False).order_by(Comment.created_at.desc()).all()
    
    # Get like information
    likes_count = Like.query.filter_by(article_id=article.id).count()
    user_liked = False
    if current_user.is_authenticated:
        user_liked = Like.query.filter_by(article_id=article.id, user_id=current_user.id).first() is not None
    
    return render_template('article_detail.html', article=article, comments=comments, 
                         likes_count=likes_count, user_liked=user_liked)

@bp.route('/article/<string:hash_id>/comment', methods=['POST'])
@login_required
def add_comment(hash_id):
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    content = request.form.get('content', '').strip()
    
    if not content:
        flash('Comment cannot be empty.', 'warning')
        return redirect(url_for('articles.view_article', hash_id=hash_id))
    
    # Check for inappropriate content
    is_inappropriate, violation_type = contains_inappropriate_content(content)
    
    if is_inappropriate:
        # Create notification for user about rule violation
        if violation_type == "profanity":
            message = "Your comment was removed due to inappropriate language. Please maintain respectful communication."
        else:  # threat
            message = "Your comment was removed due to threatening content. Such behavior violates our community guidelines."
        
        notif = Notification(
            user_id=current_user.id, 
            article_id=article.id,
            message=message
        )
        db.session.add(notif)
        db.session.commit()
        
        # Log the violation
        entry = LogEntry(
            article_id=article.id, 
            action=f"Comment by '{current_user.username}' automatically removed due to {violation_type}"
        )
        db.session.add(entry)
        db.session.commit()
        
        flash(f'Your comment was removed due to {violation_type}. Please follow our community guidelines.', 'error')
        return redirect(url_for('articles.view_article', hash_id=hash_id))
    
    # Create and save comment (automatically approved)
    comment = Comment(
        content=content,
        article_id=article.id,
        user_id=current_user.id,
        is_deleted=False
    )
    db.session.add(comment)
    db.session.commit()
    
    # Track comment analytics
    analytics = Analytics(
        article_id=article.id,
        event_type='comment',
        user_id=current_user.id,
        ip_address=request.remote_addr
    )
    db.session.add(analytics)
    db.session.commit()
    
    flash('Comment posted successfully!', 'success')
    return redirect(url_for('articles.view_article', hash_id=hash_id))

@bp.route('/article/<string:hash_id>/like', methods=['POST'])
@login_required
def like_article(hash_id):
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    existing_like = Like.query.filter_by(article_id=article.id, user_id=current_user.id).first()
    
    if existing_like:
        # Unlike the article
        db.session.delete(existing_like)
        db.session.commit()
        liked = False
    else:
        # Like the article
        like = Like(article_id=article.id, user_id=current_user.id)
        db.session.add(like)
        db.session.commit()
        liked = True
        
        # Track like analytics
        analytics = Analytics(
            article_id=article.id,
            event_type='like',
            user_id=current_user.id,
            ip_address=request.remote_addr
        )
        db.session.add(analytics)
        db.session.commit()
    
    # Return JSON response for AJAX requests
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({
            'liked': liked,
            'likes_count': len(article.likes)
        })
    
    return redirect(url_for('articles.view_article', hash_id=hash_id))

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

@bp.route('/share/<string:hash_id>/<platform>')
def share_article(hash_id, platform):
    article = Article.query.filter_by(hash_id=hash_id).first_or_404()
    
    # Track share analytics
    analytics = Analytics(
        article_id=article.id,
        event_type=f'share_{platform}',
        user_id=current_user.id if current_user.is_authenticated else None,
        ip_address=request.remote_addr
    )
    db.session.add(analytics)
    db.session.commit()
    
    article_url = url_for('articles.view_article', hash_id=hash_id, _external=True)
    
    share_urls = {
        'twitter': f"https://twitter.com/intent/tweet?text={article.title}&url={article_url}",
        'facebook': f"https://www.facebook.com/sharer/sharer.php?u={article_url}",
        'linkedin': f"https://www.linkedin.com/sharing/share-offsite/?url={article_url}",
        'whatsapp': f"https://wa.me/?text={article.title} {article_url}"
    }
    
    if platform in share_urls:
        return redirect(share_urls[platform])
    
    return redirect(url_for('articles.view_article', hash_id=hash_id))

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
    """Display paginated list of articles with search and filtering"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    category_id = request.args.get('category', '', type=str)
    sort_by = request.args.get('sort', 'newest')
    
    # Build the query
    query = Article.query.filter_by(status='approved')
    
    # Apply search filter
    if search:
        query = query.filter(
            Article.title.contains(search) | 
            Article.content.contains(search) |
            Article.tags.contains(search)
        )
    
    # Apply category filter
    if category_id:
        try:
            category_id = int(category_id)
            query = query.filter_by(category_id=category_id)
        except ValueError:
            pass
    
    # Apply sorting
    if sort_by == 'oldest':
        query = query.order_by(Article.created_at.asc())
    elif sort_by == 'popular':
        # Sort by view count (most viewed first)
        # This is a simplified approach - in production, you might want to cache view counts
        query = query.order_by(Article.created_at.desc())  # Fallback to newest for now
    else:  # newest (default)
        query = query.order_by(Article.created_at.desc())
    
    # Paginate results
    per_page = 5  # Articles per page
    pagination = query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    articles = pagination.items
    
    # Get categories for filter dropdown
    categories = Category.query.all()
    
    return render_template(
        'articles.html',
        articles=articles,
        pagination=pagination,
        categories=categories,
        search=search,
        selected_category=category_id,
        sort_by=sort_by
    )

@bp.route('/about')
def about_us():
    """About Us page showing team members, college, and internship information"""
    try:
        # Team members data (images: circular, medium size, centralized)
        team_members = [
            {
                'name': 'Shuvranshu Sekhar Sahoo',
                'role': 'Lead & Backend Developer',
                'bio': 'Computer Science student passionate about web development and news technology. Leads the technical development of Youth Times.',
                'image': 'https://avatars.githubusercontent.com/u/70892515?v=4',
                'skills': ['Python', 'Flask', 'REST APIs', 'Database Design', 'Backend Architecture', 'Linux', 'Git']
            },
            {
                'name': 'Dibyansu Sekhar Khilar',
                'role': 'Frontend Developer',
                'bio': 'Creative designer focused on user experience and responsive web design. Ensures Youth Times looks great on all devices.',
                'image': 'https://avatars.githubusercontent.com/u/197041376?v=4',
                'skills': ['Python', 'HTML5', 'CSS3', 'JavaScript', 'Bootstrap', 'Tailwind CSS', 'Responsive Design', 'Figma']
            },
            {
                'name': 'Sai Pratik Mishra',
                'role': 'Tester & Quality Assurance',
                'bio': 'Ensures the platform is robust and bug-free through rigorous testing and automation.',
                'image': 'https://avatars.githubusercontent.com/u/218381271?v=4',
                'skills': ['Python', 'Manual Testing', 'Automated Testing', 'Selenium', 'Bug Tracking', 'Test Case Design', 'Quality Assurance']
            },
            {
                'name': 'Snehal Kumar Moharana',
                'role': 'Security & Safe Browsing Specialist',
                'bio': 'Focuses on web security, safe browsing, and protecting user data.',
                'image': 'https://avatars.githubusercontent.com/u/219381177?v=4',
                'skills': ['Python', 'Web Security', 'OWASP', 'Safe Browsing', 'Vulnerability Assessment', 'Incident Response']
            },
            {
                'name': 'Subhankar Mohapatra',
                'role': 'UI/UX & Graphic Designer',
                'bio': 'Designs user interfaces and graphics for a seamless and attractive user experience.',
                'image': 'https://avatars.githubusercontent.com/u/205486409?v=4',
                'skills': ['Python', 'UI Design', 'UX Research', 'Adobe XD', 'Photoshop', 'Illustrator', 'Wireframing', 'Prototyping']
            },
            {
                'name': 'Omm Prakash Sahoo',
                'role': 'Content Manager & User Research Specialist',
                'bio': 'Manages content strategy and conducts user research to improve engagement.',
                'image': 'https://avatars.githubusercontent.com/u/219381460?v=4',
                'skills': ['Python', 'Content Strategy', 'Copywriting', 'User Research', 'SEO', 'Analytics', 'Social Media Management']
            }
        ]

        # College information (image: circular, medium size, centralized)
        college_info = {
            'name': 'Nilachal Polytechnic',
            'location': 'Bhubaneswar, Odisha, India',
            'description': 'A premier technical institution known for excellence in engineering and computer science education.',
            'established': '1985',
            'specialties': ['Computer Science', 'Electronics', 'Mechanical Engineering', 'Civil Engineering'],
            'website': 'https://www.nilachalpolytechnic.ac.in/',
            'image': 'https://avatars.githubusercontent.com/u/186801699?v=4'
        }

        # Internship information (image: circular, medium size, centralized)
        internship_info = {
            'company': 'OKCL (Odisha Knowledge Corporation Limited)',
            'program': 'Python With AI (Internship)',
            'duration': '1 Month',
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
            'website': 'https://okcl.odisha.gov.in',
            'image': 'https://okcl.org//user/themes/images/okcl%20logo.png'
        }

        # Render the About Us page with all context
        return render_template(
            'about_us.html',
            team_members=team_members,
            college_info=college_info,
            internship_info=internship_info
        )
    except Exception as e:
        current_app.logger.error(f"Error in about_us route: {str(e)}")
        flash('Error loading About Us page. Please try again later.', 'error')
        return redirect(url_for('articles.home'))

@bp.route('/user/<string:username>')
def user_profile(username):
    """Public user profile page"""
    user = User.query.filter_by(username=username).first_or_404()
    
    # Get user's published articles
    user_articles = Article.query.filter_by(
        author_id=user.id, 
        status='approved'
    ).order_by(Article.created_at.desc()).limit(10).all()
    
    # Get user stats
    total_articles = Article.query.filter_by(author_id=user.id, status='approved').count()
    total_likes = db.session.query(db.func.count(Like.id)).join(Article).filter(
        Article.author_id == user.id,
        Article.status == 'approved'
    ).scalar() or 0
    
    return render_template('user_profile.html', 
                         profile_user=user, 
                         user_articles=user_articles,
                         total_articles=total_articles,
                         total_likes=total_likes)
