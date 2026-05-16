"""
Chat Service for handling messaging between users and superadmin
"""

import logging
from app.models import Message, db
from datetime import datetime
from typing import List, Dict, Optional

class ChatService:
    """Service for managing chat messages and conversations"""
    
    @staticmethod
    def send_message(sender_id: int, recipient_id: int, content: str, 
                    message_type: str = 'text', priority: str = 'normal',
                    sender_name: str = None, sender_email: str = None,
                    sender_role: str = 'user', recipient_name: str = None, 
                    recipient_role: str = 'user', session_id: str = None) -> Message:
        """Send a message from one user to another"""
        
        message = Message(
            content=content,
            message_type=message_type,
            priority=priority,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_role=sender_role,
            sender_email=sender_email,
            recipient_id=recipient_id,
            recipient_name=recipient_name,
            recipient_role=recipient_role,
            session_id=session_id
        )
        
        try:
            db.session.add(message)
            db.session.commit()
            return message
        except Exception as e:
            db.session.rollback()
            logging.error(f"Database error in send_message: {str(e)}")
            raise e
    
    @staticmethod
    def get_conversation(user_id: int, limit: int = 50) -> List[Message]:
        """Get conversation for a user (both sent and received messages)"""
        return Message.get_conversation(user_id, limit)
    
    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """Get unread message count for a user"""
        return Message.get_unread_count(user_id)
    
    @staticmethod
    def mark_as_read(message_id: int) -> bool:
        """Mark a message as read"""
        message = Message.query.get(message_id)
        if message and not message.is_read:
            message.is_read = True
            message.read_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    @staticmethod
    def get_unread_messages(user_id: int, limit: int = 20) -> List[Message]:
        """Get unread messages for a user"""
        return Message.query.filter_by(
            recipient_id=user_id, 
            is_read=False
        ).order_by(Message.created_at.desc()).limit(limit).all()
    
    @staticmethod
    def send_admin_message(content: str, priority: str = 'normal') -> Message:
        """Send a message from superadmin to all admins"""
        from app.models import Worker
        
        # Get all admin users
        admin_users = Worker.query.filter_by(role='admin').all()
        messages = []
        
        for admin in admin_users:
            message = ChatService.send_message(
                sender_id=1,  # Assuming superadmin has ID 1
                recipient_id=admin.id,
                content=content,
                priority=priority,
                sender_name='Super Admin',
                recipient_name=admin.full_name,
                recipient_role='admin'
            )
            messages.append(message)
        
        return messages
    
    @staticmethod
    def get_message_stats(user_id: int) -> Dict:
        """Get messaging statistics for a user"""
        total_received = Message.query.filter_by(recipient_id=user_id).count()
        total_sent = Message.query.filter_by(sender_id=user_id).count()
        unread_count = Message.get_unread_count(user_id)
        
        return {
            'total_received': total_received,
            'total_sent': total_sent,
            'unread_count': unread_count,
            'read_count': total_received - unread_count
        }
