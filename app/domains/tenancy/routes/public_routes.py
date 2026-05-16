from flask import render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
from app.models import Worker, Salon, Branch, ContactConfig
from app import db
from app.main import main_bp
import secrets
import uuid
import os

@main_bp.route('/index')
def index():
    # This is public. Anyone can see the index.html content.
    return render_template('main/index.html')


@main_bp.route('/about')
def about():
    contact_info = ContactConfig.get_active_config()
    return render_template('main/about.html', contact_info=contact_info)


@main_bp.route('/services')
def services():
    return render_template('main/services.html')


@main_bp.route('/gallery')
def gallery():
    return render_template('main/gallery.html')


@main_bp.route('/contact')
def contact():
    contact_info = ContactConfig.get_active_config()
    return render_template('main/contact.html', contact_info=contact_info)


@main_bp.route('/trial')
def trial():
    return render_template('main/trial.html')


@main_bp.route('/check-username-public')
def check_username_public():
    """Public API endpoint to check username availability for trial signup"""
    username = request.args.get('username', '').strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'message': 'Username must be at least 3 characters'})
    
    existing_user = Worker.query.filter_by(username=username).first()
    if existing_user:
        # Generate suggestions for trial users
        suggestions = []
        base_suggestions = [
            f"{username}_{datetime.utcnow().strftime('%Y')}",
            f"{username}_trial",
            f"{username}_spa",
        ]
        
        for suggestion in base_suggestions[:5]:
            if not Worker.query.filter_by(username=suggestion).first():
                suggestions.append(suggestion)
                if len(suggestions) >= 3:
                    break
        
        return jsonify({
            'available': False, 
            'message': f'Username "{username}" is already taken',
            'suggestions': suggestions
        })
    else:
        return jsonify({'available': True, 'message': 'Username is available'})




@main_bp.route('/create-google-pay-order', methods=['POST'])
def create_google_pay_order():
    """Create Google Pay order for trial setup"""
    try:
        data = request.get_json()
        
        # Generate unique order ID
        order_id = f"GOOGLE_PAY_{uuid.uuid4().hex[:12].upper()}"
        
        # Create order response
        order_response = {
            'orderId': order_id,
            'amount': '30.00',
            'currency': 'USD',
            'description': 'Africa SPA System - 14-Day Trial Setup',
            'status': 'created'
        }
        
        return jsonify(order_response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@main_bp.route('/payment-success')
def payment_success():
    """Handle Stripe payment success"""
    return render_template('main/payment_success.html')

@main_bp.route('/payment-cancelled')
def payment_cancelled():
    """Handle Stripe payment cancellation"""
    return render_template('main/payment_cancelled.html')

@main_bp.route('/process-trial', methods=['POST'])
def process_trial():
    """Process trial signup with payment and salon creation"""
    try:
        # Get form data
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['salon_name', 'business_type', 'country', 'branch_count', 
                          'owner_name', 'email', 'phone', 'username', 'password']
        
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field.replace("_", " ").title()} is required'})
        
        # Check if username already exists
        existing_user = Worker.query.filter_by(username=data['username']).first()
        if existing_user:
            return jsonify({'success': False, 'message': 'Username already exists'})
        
        # Check if email already exists
        existing_email = Worker.query.filter_by(email=data['email']).first()
        if existing_email:
            return jsonify({'success': False, 'message': 'Email already registered'})
        
        # Process payment with Google Pay
        payment_result = process_payment(data['email'], data['salon_name'], 30.00, data.get('google_pay_order_id'))
        
        if not payment_result['success']:
            return jsonify({'success': False, 'message': 'Payment failed: ' + payment_result['message']})
        
        # Create salon
        salon = create_salon(data, payment_result['transaction_id'])
        
        # Create owner account
        owner = create_owner_account(data, salon)
        
        # Send login credentials email
        send_credentials_email(data['email'], data['username'], data['password'], salon.name)
        
        return jsonify({
            'success': True, 
            'message': 'Trial setup successful! Login credentials sent to your email.',
            'redirect_url': '/login'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'})


def process_payment(email, salon_name, amount, payment_id=None):
    """Process payment using Google Pay"""
    try:
        # Simulate Google Pay processing (in production, integrate with actual Google Pay API)
        transaction_id = f"GOOGLE_PAY_{uuid.uuid4().hex[:12].upper()}"
        
        # Log payment for records
        payment_data = {
            'email': email,
            'salon_name': salon_name,
            'amount': amount,
            'currency': 'USD',
            'transaction_id': transaction_id,
            'status': 'success'
        }
        
        print(f"Google Pay payment processed: {payment_data}")
        
        return {
            'success': True,
            'transaction_id': transaction_id,
            'message': 'Payment successful'
        }
        
    except Exception as e:
        print(f"Google Pay error: {str(e)}")
        return {
            'success': False,
            'message': f'Payment processing error: {str(e)}'
        }


def create_salon(data, transaction_id):
    """Create salon and initial branch"""
    try:
        # Create salon
        salon = Salon(
            name=data['salon_name'],
            business_type=data['business_type'],
            country=data['country'],
            email=data['email'],
            phone=data['phone'],
            is_active=True,
            trial_ends_at=datetime.utcnow() + datetime.timedelta(days=14),
            subscription_status='trial',
            payment_transaction_id=transaction_id
        )
        
        db.session.add(salon)
        db.session.flush()  # Get the salon ID
        
        # Create initial branch
        branch = Branch(
            name=f"{data['salon_name']} - Main Branch",
            code='MAIN',
            salon_id=salon.id,
            address=data.get('address', ''),
            phone=data['phone'],
            email=data['email'],
            is_active=True
        )
        
        db.session.add(branch)
        db.session.commit()
        
        return salon
        
    except Exception as e:
        db.session.rollback()
        raise e


def create_owner_account(data, salon):
    """Create owner/worker account"""
    try:
        # Generate secure password if not provided
        password = data['password'] if data['password'] else secrets.token_urlsafe(12)
        
        owner = Worker(
            username=data['username'],
            email=data['email'],
            password_hash=password,  # This should be hashed properly
            first_name=data['owner_name'].split()[0],
            last_name=' '.join(data['owner_name'].split()[1:]) if len(data['owner_name'].split()) > 1 else '',
            phone=data['phone'],
            role='owner',  # or 'salon_admin' depending on your role system
            salon_id=salon.id,
            branch_id=salon.branches[0].id if salon.branches else None,
            is_active=True
        )
        
        db.session.add(owner)
        db.session.commit()
        
        return owner
        
    except Exception as e:
        db.session.rollback()
        raise e


def send_credentials_email(email, username, password, salon_name):
    """Send login credentials to user email"""
    try:
        # This is a mock implementation - integrate with actual email service
        # You could use Flask-Mail, SendGrid, AWS SES, etc.
        
        email_content = f"""
        Subject: Welcome to Africa SPA System - Your Login Credentials
        
        Dear User,
        
        Welcome to Africa SPA System! Your salon "{salon_name}" has been successfully created.
        
        Login Details:
        - URL: https://africspa.com/login
        - Username: {username}
        - Password: {password}
        
        Your 14-day trial has begun. You can access all features during this period.
        
        For support, email: trial@africspa.com
        
        Best regards,
        Africa SPA System Team
        """
        
        # Mock email sending - replace with actual email service
        print(f"Email sent to {email}:")
        print(email_content)
        
        return True
        
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False
