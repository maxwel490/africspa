"""
Public chat routes for outsiders to contact superadmin
"""

from flask import Blueprint, render_template, request, jsonify
from app.services.chat_service import ChatService
from app.models import Worker, Message, db
from datetime import datetime

public_chat_bp = Blueprint('public_chat', __name__)

@public_chat_bp.route('/support')
def support_chat():
    """Public support chat page"""
    return render_template('main/support_chat.html')

@public_chat_bp.route('/send', methods=['POST'])
def send_message():
    """Send message from public user to superadmin"""
    try:
        data = request.get_json()
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        message = data.get('message', '').strip()
        session_id = data.get('session_id', '')
        
        if not name or not email or not message:
            return jsonify({'success': False, 'error': 'Name, email, and message are required'})
        
        # Get superadmin user
        superadmin = Worker.query.filter_by(role='superadmin').first()
        
        if not superadmin:
            return jsonify({'success': False, 'error': 'Support system unavailable'})
        
        # Create message with all fields including session_id and sender_role
        chat_message = Message(
            content=message,
            message_type='text',
            priority='normal',
            sender_id=None,  # Public user has no Worker ID
            sender_name=name,
            sender_email=email,
            sender_role='outsider',  # Set outsider role
            recipient_id=superadmin.id,
            recipient_name=superadmin.full_name,
            recipient_role='superadmin',
            session_id=session_id  # Store session ID for tracking
        )
        
        db.session.add(chat_message)
        db.session.commit()
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@public_chat_bp.route('/check/<session_id>')
def check_messages(session_id):
    """Check for new messages in a session"""
    try:
        # Get messages for this session that are from superadmin
        messages = db.session.query(Message).filter(
            Message.session_id == session_id,
            Message.sender_role == 'superadmin',
            Message.is_read == False
        ).order_by(Message.created_at.desc()).all()
        
        # Mark as read
        for msg in messages:
            msg.is_read = True
            msg.read_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'messages': [{
                'content': msg.content,
                'sender_name': msg.sender_name,
                'created_at': msg.created_at.isoformat()
            } for msg in messages]
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
