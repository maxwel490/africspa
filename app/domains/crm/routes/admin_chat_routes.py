"""CRM routes: admin chat and messaging (admin_bp)."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import Worker, Message, db
from app.decorators import roles_required
from app.services.chat_service import ChatService
from app.admin import admin_bp
from datetime import datetime
import logging


@admin_bp.route('/chat-support')
@login_required
@roles_required('admin')
def chat_support():
    """Tenant admin chat support interface"""
    # Get messages for this admin
    messages = db.session.query(Message).filter(
        (Message.recipient_id == current_user.id) | (Message.sender_id == current_user.id)
    ).order_by(Message.created_at.desc()).limit(50).all()
    
    # Get unread count
    unread_count = db.session.query(Message).filter(
        Message.recipient_id == current_user.id,
        Message.is_read == False
    ).count()
    
    # Group messages by conversation
    conversations = {}
    for msg in messages:
        key = msg.session_id or f"direct_{msg.sender_id if msg.sender_id != current_user.id else msg.recipient_id}"
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
    
    return render_template('admin/chat_support.html', 
                        conversations=conversations,
                        messages=messages,
                        unread_count=unread_count)

@admin_bp.route('/chat/send', methods=['POST'])
@login_required
@roles_required('admin')
def admin_send_chat_message():
    """Send message from admin to superadmin"""
    try:
        data = request.get_json()
        
        recipient_id = data.get('recipient_id')
        content = data.get('message', '').strip()
        session_id = data.get('session_id', '')
        
        if not content:
            return jsonify({'success': False, 'error': 'Message is required'})
        
        # Get superadmin user
        superadmin = Worker.query.filter_by(role='superadmin').first()
        if not superadmin:
            return jsonify({'success': False, 'error': 'Superadmin not available'})
        
        # Create message from admin to superadmin
        message = ChatService.send_message(
            sender_id=current_user.id,
            recipient_id=superadmin.id,
            content=content,
            sender_name=current_user.full_name,
            recipient_name=superadmin.full_name,
            recipient_role='superadmin',
            session_id=session_id
        )
        
        # Store additional info
        message.sender_role = 'admin'
        message.session_id = session_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'sender_name': message.sender_name
            }
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/chat/mark-read', methods=['POST'])
@login_required
@roles_required('admin')
def mark_chat_read():
    """Mark messages as read for admin"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if session_id:
            # Mark messages in this session as read
            messages = Message.query.filter(
                Message.session_id == session_id,
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


@admin_bp.route('/chat')
@login_required
@roles_required('admin')
def chat():
    """Chat interface for admin users to contact superadmin"""
    # Get conversation for current user
    messages = ChatService.get_conversation(current_user.id, limit=50)
    unread_count = ChatService.get_unread_count(current_user.id)
    
    # Mark messages as read
    for message in messages:
        if message.recipient_id == current_user.id and not message.is_read:
            ChatService.mark_as_read(message.id)
    
    return render_template('admin/chat.html', 
                        messages=messages, 
                        unread_count=unread_count)


@admin_bp.route('/chat/send', methods=['POST'])
@login_required
@roles_required('admin')
def send_chat_message():
    """Send a message to superadmin"""
    try:
        # Get JSON data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No JSON data received'})
        
        content = data.get('message', '').strip()
        session_id = data.get('session_id')
        
        if not content:
            return jsonify({'success': False, 'error': 'Message cannot be empty'})
        
        # Get superadmin user (assuming first superadmin)
        superadmin = Worker.query.filter_by(role='superadmin').first()
        
        if not superadmin:
            return jsonify({'success': False, 'error': 'Superadmin not found in system. Please create a superadmin account first.'})
        
        # Validate superadmin has valid ID for foreign key constraint
        if not superadmin.id:
            return jsonify({'success': False, 'error': 'Superadmin account has invalid ID'})
        
        # Import ChatService to avoid circular imports
        from app.services.chat_service import ChatService
        
        try:
            message = ChatService.send_message(
                sender_id=current_user.id,
                recipient_id=superadmin.id,
                content=content,
                sender_name=current_user.full_name,
                sender_email=current_user.email,
                sender_role='admin',
                recipient_name=superadmin.full_name,
                recipient_role='superadmin',
                session_id=session_id
            )
        except Exception as db_error:
            import logging
            logging.error(f"Database error in ChatService.send_message: {str(db_error)}", exc_info=True)
            
            # Handle specific database errors
            error_msg = str(db_error)
            if "IntegrityError" in error_msg or "foreign key constraint" in error_msg.lower():
                return jsonify({'success': False, 'error': 'Database constraint error: Invalid user reference or missing required data'})
            elif "1080" in error_msg:
                return jsonify({'success': False, 'error': 'Foreign key constraint violation: Superadmin user may not exist or be invalid'})
            else:
                return jsonify({'success': False, 'error': f'Database error: {str(db_error)}'})
        
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
        import logging
        logging.error(f"Error in admin chat send: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'})
