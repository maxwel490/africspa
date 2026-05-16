from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import Salon, Worker, Branch, Client, Appointment, ServiceOrder, db, Message, SupportTicket
from app.services.chat_service import ChatService
from app.decorators import roles_required
from sqlalchemy import func
from datetime import datetime, timedelta
from . import superadmin_bp

@superadmin_bp.route('/')
@login_required
@roles_required('superadmin')
def dashboard():
    """System Owner Dashboard - Platform overview and tenant management"""
    
    # Tenant Statistics (Salons)
    total_salons = Salon.query.count()
    active_salons = Salon.query.filter_by(is_active=True).count()
    inactive_salons = total_salons - active_salons
    
    # Get tenant owner summaries with branch counts
    tenant_summaries = []
    salons = Salon.query.order_by(Salon.created_at.desc()).all()
    
    for salon in salons:
        # Count branches for this tenant only
        branch_count = Branch.query.filter_by(salon_id=salon.id).count()
        
        # Count workers for this tenant only
        worker_count = Worker.query.filter_by(salon_id=salon.id).count()
        
        tenant_summary = {
            'id': salon.id,
            'name': salon.name,
            'slug': salon.slug,
            'email': salon.email,
            'phone': salon.phone,
                        'is_active': salon.is_active,
            'created_at': salon.created_at,
            'branch_count': branch_count,
            'worker_count': worker_count,
            'max_branches': salon.max_branches,
            'max_staff': salon.max_staff
        }
        tenant_summaries.append(tenant_summary)
    
    # Continental Stats
    total_branches = sum(tenant['branch_count'] for tenant in tenant_summaries)
    total_workers = sum(tenant['worker_count'] for tenant in tenant_summaries)
    
    # Regional distribution (if country data available)
    regions = {}
    for salon in salons:
        country = getattr(salon, 'country', 'KE')  # Default to Kenya if not set
        regions[country] = regions.get(country, 0) + 1
    
    return render_template('superadmin/dashboard.html',
                       total_salons=total_salons,
                       active_salons=active_salons,
                       inactive_salons=inactive_salons,
                       total_branches=total_branches,
                       total_workers=total_workers,
                       tenant_summaries=tenant_summaries,
                       regions=regions)

@superadmin_bp.route('/salons')
@login_required
@roles_required('superadmin')
def manage_salons():
    """Manage all salons in the system"""
    
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = Salon.query
    
    if search:
        query = query.filter(Salon.name.ilike(f'%{search}%'))
    
    salons = query.order_by(Salon.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('superadmin/salons.html', salons=salons, search=search)

@superadmin_bp.route('/salons/create', methods=['GET', 'POST'])
@login_required
@roles_required('superadmin')
def create_salon():
    """Create a new salon (tenant) with admin user"""
    
    if request.method == 'POST':
        # Salon data
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        country = request.form.get('country', 'KE')  # Default to Kenya
        
        # Set reasonable defaults for tenant limits
        max_branches = 50  # Default to 50 branches (generous for tenant)
        max_staff = 200   # Default to 200 staff members (generous for tenant)
        
        # Admin user data
        admin_full_name = request.form.get('admin_full_name', '').strip()
        admin_email = request.form.get('admin_email', '').strip()
        admin_username = request.form.get('admin_username', '').strip()
        admin_phone = request.form.get('admin_phone', '').strip()
        admin_password = request.form.get('admin_password', '')
        admin_address = request.form.get('admin_address', '').strip()
        
        # Validation
        if not name or not slug or not email:
            flash('Name, slug, and email are required', 'danger')
            return redirect(url_for('superadmin.create_salon'))
        
        if not admin_full_name or not admin_email or not admin_username or not admin_password:
            flash('All admin fields are required', 'danger')
            return redirect(url_for('superadmin.create_salon'))
        
        # Check if slug already exists
        if Salon.query.filter_by(slug=slug).first():
            flash('Slug already exists. Please choose a different one.', 'danger')
            return redirect(url_for('superadmin.create_salon'))
        
        # Check if salon email already exists
        if Salon.query.filter_by(email=email).first():
            flash('Salon email already exists. Please use a different email.', 'danger')
            return redirect(url_for('superadmin.create_salon'))
        
        # Check if admin username already exists
        if Worker.query.filter_by(username=admin_username).first():
            flash('Admin username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('superadmin.create_salon'))
        
        # Check if admin email already exists
        if Worker.query.filter_by(email=admin_email).first():
            flash('Admin email already exists. Please use a different email.', 'danger')
            return redirect(url_for('superadmin.create_salon'))
        
        try:
            # Create new salon first
            salon = Salon(
                name=name,
                slug=slug,
                email=email,
                phone=phone,
                address=address,
                country=country,
                max_branches=max_branches,
                max_staff=max_staff,
                is_active=True
            )
            
            db.session.add(salon)
            db.session.flush()  # Get the salon ID without committing
            
            # Create admin user for the salon (tenant owner - not tied to specific branch)
            admin_user = Worker(
                username=admin_username,
                email=admin_email,
                full_name=admin_full_name,
                phone=admin_phone,
                address=request.form.get('admin_address', '').strip(),
                role='admin',
                branch=None,  # Admin is salon owner, not tied to specific branch
                salon_id=salon.id,
                is_active=True
            )
            
            try:
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
            except ValueError as e:
                db.session.rollback()
                flash(f'Invalid password: {str(e)}', 'danger')
                return redirect(url_for('superadmin.create_salon'))
            
            db.session.commit()
            
            flash(f'Tenant salon "{name}" and tenant owner "{admin_full_name}" created successfully!', 'success')
            flash(f'Tenant owner login: {admin_username} / (password you set)', 'info')
            flash(f'Tenant owner will need to create their own branches after login', 'info')
            return redirect(url_for('superadmin.manage_salons'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating tenant salon and owner: {str(e)}', 'danger')
            return redirect(url_for('superadmin.create_salon'))
    
    return render_template('superadmin/create_salon.html')

@superadmin_bp.route('/salons/<int:salon_id>')
@login_required
@roles_required('superadmin')
def view_salon(salon_id):
    """View detailed salon information"""
    salon = Salon.query.get_or_404(salon_id)
    
    # Get salon statistics
    workers_count = Worker.query.filter_by(salon_id=salon.id).count()
    branches_count = Branch.query.filter_by(salon_id=salon.id).count()
    clients_count = Client.query.filter_by(salon_id=salon.id).count()
    appointments_count = Appointment.query.filter_by(salon_id=salon.id).count()
    
    # Get recent activity
    recent_appointments = Appointment.query.filter_by(salon_id=salon.id)\
        .order_by(Appointment.appointment_time.desc()).limit(10).all()
    
    return render_template('superadmin/salon_detail.html',
                       salon=salon,
                       workers_count=workers_count,
                       branches_count=branches_count,
                       clients_count=clients_count,
                       appointments_count=appointments_count,
                       recent_appointments=recent_appointments)

@superadmin_bp.route('/salons/<int:salon_id>/toggle')
@login_required
@roles_required('superadmin')
def toggle_salon(salon_id):
    """Activate/deactivate salon"""
    salon = Salon.query.get_or_404(salon_id)
    salon.is_active = not salon.is_active
    db.session.commit()
    
    status = "activated" if salon.is_active else "deactivated"
    flash(f"Salon '{salon.name}' {status} successfully", "success")
    
    return redirect(url_for('superadmin.manage_salons'))

@superadmin_bp.route('/analytics')
@login_required
@roles_required('superadmin')
def analytics():
    """System-wide analytics"""
    
    # Time range filters
    days = request.args.get('days', 30, type=int)
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Salon growth over time
    salon_growth = db.session.query(
        func.date(Salon.created_at).label('date'),
        func.count(Salon.id).label('count')
    ).filter(Salon.created_at >= start_date)\
     .group_by(func.date(Salon.created_at))\
     .order_by(func.date(Salon.created_at)).all()
    
    # Regional distribution
    regional_stats = db.session.query(
        func.coalesce(Salon.country, 'KE'),
        func.count(Salon.id).label('count')
    ).group_by(func.coalesce(Salon.country, 'KE')).all()
    
    # Top performing salons
    top_salons = db.session.query(
        Salon.name,
        func.count(Appointment.id).label('appointments')
    ).join(Appointment, Salon.id == Appointment.salon_id)\
     .group_by(Salon.id, Salon.name)\
     .order_by(func.count(Appointment.id).desc())\
     .limit(10).all()
    
    return render_template('superadmin/analytics.html',
                       salon_growth=salon_growth,
                       regional_stats=regional_stats,
                       top_salons=top_salons,
                       days=days)

@superadmin_bp.route('/api/stats')
@login_required
@roles_required('superadmin')
def api_stats():
    """API endpoint for real-time statistics"""
    
    stats = {
        'total_salons': Salon.query.count(),
        'active_salons': Salon.query.filter_by(is_active=True).count(),
        'total_workers': Worker.query.count(),
        'total_branches': Branch.query.count(),
        'total_clients': Client.query.count(),
        'total_appointments': Appointment.query.count(),
        'continental_revenue': calculate_continental_revenue()
    }
    
    return jsonify(stats)

def calculate_continental_revenue():
    """Calculate total monthly continental revenue ($30 per branch per month)"""
    total_branches = Branch.query.count()
    # $30 USD per branch per month
    return total_branches * 30

@superadmin_bp.route('/settings')
@login_required
@roles_required('superadmin')
def settings():
    """Superadmin settings page"""
    return render_template('superadmin/settings.html')


@superadmin_bp.route('/payment-settings', methods=['GET', 'POST'])
@login_required
@roles_required('superadmin')
def payment_settings():
    """Payment settings page for configuring API keys"""
    from app.models import PaymentConfig

    payment_config = PaymentConfig.get_active_config()

    if not payment_config:
        # Create default config
        payment_config = PaymentConfig(
            google_pay_merchant_name='Africa SPA System',
            google_pay_environment='TEST',
            paypal_environment='sandbox',
            default_currency='USD',
            enable_test_mode=True
        )
        db.session.add(payment_config)
        db.session.commit()

    if request.method == 'POST':
        # Update Google Pay settings
        payment_config.google_pay_merchant_id = request.form.get('google_pay_merchant_id', '')
        payment_config.google_pay_merchant_name = request.form.get('google_pay_merchant_name', 'Africa SPA System')
        payment_config.google_pay_environment = request.form.get('google_pay_environment', 'TEST')

        # Update Stripe settings
        payment_config.stripe_publishable_key = request.form.get('stripe_publishable_key', '')
        if request.form.get('stripe_secret_key'):
            payment_config.stripe_secret_key = request.form.get('stripe_secret_key')
        if request.form.get('stripe_webhook_secret'):
            payment_config.stripe_webhook_secret = request.form.get('stripe_webhook_secret')

        # Update PayPal settings
        payment_config.paypal_client_id = request.form.get('paypal_client_id', '')
        if request.form.get('paypal_client_secret'):
            payment_config.paypal_client_secret = request.form.get('paypal_client_secret')
        payment_config.paypal_environment = request.form.get('paypal_environment', 'sandbox')

        # Update Flutterwave settings
        payment_config.flutterwave_public_key = request.form.get('flutterwave_public_key', '')
        if request.form.get('flutterwave_secret_key'):
            payment_config.flutterwave_secret_key = request.form.get('flutterwave_secret_key')
        payment_config.flutterwave_encryption_key = request.form.get('flutterwave_encryption_key', '')

        # Update M-Pesa settings
        payment_config.mpesa_consumer_key = request.form.get('mpesa_consumer_key', '')
        if request.form.get('mpesa_consumer_secret'):
            payment_config.mpesa_consumer_secret = request.form.get('mpesa_consumer_secret')
        payment_config.mpesa_shortcode = request.form.get('mpesa_shortcode', '')
        if request.form.get('mpesa_passkey'):
            payment_config.mpesa_passkey = request.form.get('mpesa_passkey')

        # Update general settings
        payment_config.default_currency = request.form.get('default_currency', 'USD')
        payment_config.enable_test_mode = request.form.get('enable_test_mode') == 'on'
        payment_config.updated_by = current_user.id

        db.session.commit()
        flash('Payment settings updated successfully!', 'success')
        return redirect(url_for('superadmin.payment_settings'))

    return render_template('superadmin/payment_settings.html', payment_config=payment_config)


@superadmin_bp.route('/contact-settings', methods=['GET', 'POST'])
@login_required
@roles_required('superadmin')
def contact_settings():
    """Contact settings page for configuring emails, phone numbers, and address"""
    from app.models import ContactConfig

    contact_config = ContactConfig.get_active_config()

    if not contact_config:
        # Create default config
        contact_config = ContactConfig(
            company_name='Africa SPA System',
            support_email='support@africspa.com',
            billing_email='billing@africspa.com',
            sales_email='sales@africspa.com',
            technical_email='tech@africspa.com',
            website_url='https://africspa.com',
            business_hours='Mon-Fri: 8:00 AM - 6:00 PM\nSat: 9:00 AM - 4:00 PM\nSun: Closed'
        )
        db.session.add(contact_config)
        db.session.commit()

    if request.method == 'POST':
        # Email addresses
        contact_config.support_email = request.form.get('support_email', 'support@africspa.com')
        contact_config.billing_email = request.form.get('billing_email', 'billing@africspa.com')
        contact_config.sales_email = request.form.get('sales_email', 'sales@africspa.com')
        contact_config.technical_email = request.form.get('technical_email', 'tech@africspa.com')

        # Phone numbers
        contact_config.support_phone = request.form.get('support_phone', '')
        contact_config.sales_phone = request.form.get('sales_phone', '')
        contact_config.whatsapp_number = request.form.get('whatsapp_number', '')

        # Address
        contact_config.company_name = request.form.get('company_name', 'Africa SPA System')
        contact_config.address_line1 = request.form.get('address_line1', '')
        contact_config.address_line2 = request.form.get('address_line2', '')
        contact_config.city = request.form.get('city', '')
        contact_config.country = request.form.get('country', '')
        contact_config.postal_code = request.form.get('postal_code', '')

        # Social media
        contact_config.website_url = request.form.get('website_url', 'https://africspa.com')
        contact_config.facebook_url = request.form.get('facebook_url', '')
        contact_config.twitter_url = request.form.get('twitter_url', '')
        contact_config.instagram_url = request.form.get('instagram_url', '')
        contact_config.linkedin_url = request.form.get('linkedin_url', '')

        # Business hours
        contact_config.business_hours = request.form.get('business_hours', '')

        contact_config.updated_by = current_user.id
        db.session.commit()
        flash('Contact settings updated successfully!', 'success')
        return redirect(url_for('superadmin.contact_settings'))

    return render_template('superadmin/contact_settings.html', contact_config=contact_config)


@superadmin_bp.route('/chat')
@login_required
@roles_required('superadmin')
def chat_dashboard():
    """Superadmin chat dashboard to view and respond to messages"""
    # Get all messages grouped by session
    messages = db.session.query(Message).order_by(Message.created_at.desc()).limit(200).all()
    
    # Get unread count (messages from outsiders that are unread)
    unread_count = db.session.query(Message).filter(
        Message.sender_role == 'outsider',
        Message.is_read == False
    ).count()
    
    # Group messages by session/conversation
    conversations = {}
    for msg in messages:
        key = msg.session_id or f"direct_{msg.sender_id or 'unknown'}"
        if key not in conversations:
            conversations[key] = []
        # Convert Message object to dictionary for JSON serialization
        conversations[key].append({
            'id': msg.id,
            'content': msg.content,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'sender_role': msg.sender_role,
            'recipient_id': msg.recipient_id,
            'recipient_name': msg.recipient_name,
            'recipient_role': msg.recipient_role,
            'session_id': msg.session_id,
            'is_read': msg.is_read,
            'created_at': msg.created_at.isoformat()
        })
    
    # Sort messages within each conversation chronologically (oldest first, newest last)
    for key in conversations:
        conversations[key].sort(key=lambda x: x['created_at'])
    
    # Sort conversations by latest message
    sorted_conversations = dict(sorted(
        conversations.items(),
        key=lambda x: datetime.fromisoformat(x[1][-1]['created_at']) if x[1] else datetime.min,
        reverse=True
    ))
    
    return render_template('superadmin/chat_dashboard.html', 
                        conversations=sorted_conversations,
                        messages=messages,
                        unread_count=unread_count)

@superadmin_bp.route('/chat/data')
@login_required
@roles_required('superadmin')
def chat_data():
    """Return conversation data as JSON for efficient refresh"""
    # Get all messages grouped by session
    messages = db.session.query(Message).order_by(Message.created_at.desc()).limit(200).all()
    
    # Get unread count (messages from outsiders that are unread)
    unread_count = db.session.query(Message).filter(
        Message.sender_role == 'outsider',
        Message.is_read == False
    ).count()
    
    # Group messages by session/conversation
    conversations = {}
    for msg in messages:
        key = msg.session_id or f"direct_{msg.sender_id or 'unknown'}"
        if key not in conversations:
            conversations[key] = []
        # Convert Message object to dictionary for JSON serialization
        conversations[key].append({
            'id': msg.id,
            'content': msg.content,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'sender_role': msg.sender_role,
            'recipient_id': msg.recipient_id,
            'recipient_name': msg.recipient_name,
            'recipient_role': msg.recipient_role,
            'session_id': msg.session_id,
            'is_read': msg.is_read,
            'created_at': msg.created_at.isoformat()
        })
    
    # Sort messages within each conversation chronologically (oldest first, newest last)
    for key in conversations:
        conversations[key].sort(key=lambda x: x['created_at'])
    
    # Sort conversations by latest message
    sorted_conversations = dict(sorted(
        conversations.items(),
        key=lambda x: datetime.fromisoformat(x[1][-1]['created_at']) if x[1] else datetime.min,
        reverse=True
    ))
    
    return jsonify({
        'conversations': sorted_conversations,
        'unread_count': unread_count
    })


@superadmin_bp.route('/chat/send', methods=['POST'])
@login_required
@roles_required('superadmin')
def send_chat_reply():
    """Send a reply from superadmin"""
    data = request.get_json()
    
    recipient_id = data.get('recipient_id')
    content = data.get('message', '').strip()
    session_id = data.get('session_id')
    
    if not recipient_id or not content:
        return jsonify({'success': False, 'error': 'Recipient and message are required'})
    
    try:
        # Get recipient info
        if recipient_id.startswith('session_'):
            # This is a public user, send to session
            recipient_name = 'Public User'
            recipient_role = 'outsider'
            recipient_id = None
        else:
            # This is a registered user
            recipient = Worker.query.get(int(recipient_id))
            if not recipient:
                return jsonify({'success': False, 'error': 'Recipient not found'})
            recipient_name = recipient.full_name
            recipient_role = recipient.role
        
        message = ChatService.send_message(
            sender_id=current_user.id,
            recipient_id=recipient_id,
            content=content,
            sender_name=current_user.full_name,
            sender_role='superadmin',
            recipient_name=recipient_name,
            recipient_role=recipient_role,
            session_id=session_id
        )
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.isoformat(),
                'sender_name': message.sender_name
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@superadmin_bp.route('/chat/mark-read/<int:message_id>', methods=['POST'])
@login_required
@roles_required('superadmin')
def mark_message_read(message_id):
    """Mark a specific message as read"""
    message = Message.query.get_or_404(message_id)
    message.is_read = True
    message.read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})

@superadmin_bp.route('/chat/mark-all-read', methods=['POST'])
@login_required
@roles_required('superadmin')
def mark_all_read():
    """Mark all messages as read"""
    try:
        messages = Message.query.filter(
            Message.recipient_id == current_user.id,
            Message.is_read == False
        ).all()
        
        for msg in messages:
            msg.is_read = True
            msg.read_at = datetime.utcnow()
        
        db.session.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
