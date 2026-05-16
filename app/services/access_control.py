"""
Access Control Service for Africa SPA System

Handles grace period management and role-based access control
based on subscription payment status.
"""

import logging
from datetime import datetime, timedelta
from flask import current_app
from app.models import Salon, Worker, db

logger = logging.getLogger(__name__)

class AccessControlService:
    """Manages access control based on subscription status and grace periods"""
    
    def __init__(self):
        self.grace_period_days = 7  # 7-day grace period
        self.system_lockdown_roles = ['salonist']  # Roles locked after grace period
        self.limited_access_roles = ['accountant']  # Roles with limited access after grace period
        self.bypass_roles = ['superadmin', 'admin']  # Roles that can bypass grace period
    
    def check_subscription_status(self, salon_id: int) -> dict:
        """
        Check subscription status and access permissions
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Dictionary with subscription status and access control info
        """
        try:
            salon = Salon.query.get(salon_id)
            if not salon:
                return {'error': 'Salon not found', 'access_level': 'denied'}
            
            # Get subscription details
            from app.services.subscription_payment import subscription_payment_service
            subscription = subscription_payment_service.get_subscription_status(salon_id)
            
            # Check if subscription is active
            is_active = subscription.get('is_active', False)
            next_billing_date = subscription.get('next_billing_date')
            last_payment_date = subscription.get('last_payment_date')
            
            # Calculate grace period
            grace_period_end = None
            in_grace_period = False
            days_past_due = None
            
            if next_billing_date and not is_active:
                grace_period_end = next_billing_date + timedelta(days=self.grace_period_days)
                now = datetime.utcnow()
                
                if now <= grace_period_end:
                    in_grace_period = True
                    days_past_due = (now - next_billing_date).days
                else:
                    days_past_due = (now - next_billing_date).days
            
            # Determine access level
            access_level = self._determine_access_level(
                is_active, in_grace_period, days_past_due
            )
            
            return {
                'salon_id': salon_id,
                'salon_name': salon.name,
                'is_active': is_active,
                'next_billing_date': next_billing_date,
                'last_payment_date': last_payment_date,
                'grace_period_end': grace_period_end,
                'in_grace_period': in_grace_period,
                'days_past_due': days_past_due,
                'access_level': access_level,
                'message': self._get_access_message(access_level, days_past_due)
            }
            
        except Exception as e:
            logger.error(f"Error checking subscription status: {str(e)}")
            # For development, allow access if subscription check fails
            return {
                'access_level': 'full',
                'message': 'Subscription check bypassed for development'
            }
    
    def _determine_access_level(self, is_active: bool, in_grace_period: bool, days_past_due: int) -> str:
        """Determine access level based on subscription status"""
        
        if is_active:
            return 'full'
        elif in_grace_period:
            return 'grace_period'
        elif days_past_due and days_past_due > self.grace_period_days:
            return 'lockdown'
        else:
            return 'denied'
    
    def _get_access_message(self, access_level: str, days_past_due: int) -> str:
        """Get appropriate message for access level"""
        
        messages = {
            'full': 'Full access - subscription active',
            'grace_period': f'Grace period active - {self.grace_period_days - days_past_due} days remaining',
            'lockdown': f'Access restricted - payment overdue by {days_past_due - self.grace_period_days} days',
            'denied': 'Access denied - subscription issue'
        }
        
        return messages.get(access_level, 'Unknown status')
    
    def check_user_access(self, user) -> dict:
        """
        Check if user can access the system
        
        Args:
            user: Worker object
            
        Returns:
            Dictionary with access permissions and restrictions
        """
        try:
            # Superadmin always has full access
            if user.role == 'superadmin':
                return {
                    'can_login': True,
                    'access_level': 'full',
                    'redirect_url': None,
                    'restrictions': [],
                    'message': 'System administrator - full access'
                }
            
            # Admin with no salon - redirect to billing or allow setup
            if user.role == 'admin' and not user.salon_id:
                return {
                    'can_login': True,
                    'access_level': 'setup_required',
                    'redirect_url': '/superadmin/create_salon',
                    'restrictions': ['setup_required'],
                    'message': 'Create salon to continue'
                }
            
            # For development, allow access if no salon_id
            if not user.salon_id:
                return {
                    'can_login': True,
                    'access_level': 'full',
                    'redirect_url': None,
                    'restrictions': [],
                    'message': 'Development access - no salon required'
                }
            
            # Check subscription status for tenant users
            if user.salon_id and user.role in ['admin', 'accountant', 'salonist']:
                subscription_status = self.check_subscription_status(user.salon_id)
                access_level = subscription_status.get('access_level', 'denied')
                
                # Determine access based on role and subscription status
                access_result = self._check_role_access(user.role, access_level, subscription_status)
                
                return access_result
            
            # Default to full access for other roles in development
            return {
                'can_login': True,
                'access_level': 'full',
                'redirect_url': None,
                'restrictions': [],
                'message': 'Full access - development mode'
            }
            
        except Exception as e:
            logger.error(f"Error checking user access: {str(e)}")
            # For development, allow access on error
            return {
                'can_login': True,
                'access_level': 'full',
                'redirect_url': None,
                'restrictions': [],
                'message': 'Development access - error bypassed'
            }
    
    def _check_role_access(self, role: str, access_level: str, subscription_status: dict) -> dict:
        """Check access based on role and subscription status"""
        
        days_past_due = subscription_status.get('days_overdue') or subscription_status.get('days_past_due') or 0
        
        # Full access - all roles work normally
        if access_level == 'full':
            return {
                'can_login': True,
                'access_level': 'full',
                'redirect_url': None,
                'restrictions': [],
                'message': 'Full access - subscription active'
            }
        
        # Grace period - limited access
        elif access_level == 'grace_period':
            if role == 'admin':
                return {
                    'can_login': True,
                    'access_level': 'grace_period',
                    'redirect_url': '/subscription/billing',
                    'restrictions': ['billing_required'],
                    'message': f'Grace period - {self.grace_period_days - days_past_due} days remaining'
                }
            elif role == 'accountant':
                return {
                    'can_login': True,
                    'access_level': 'limited',
                    'redirect_url': '/service_orders',
                    'restrictions': ['service_orders_only', 'no_services', 'no_inventory'],
                    'message': f'Grace period - service orders only ({self.grace_period_days - days_past_due} days remaining)'
                }
            elif role == 'salonist':
                return {
                    'can_login': True,
                    'access_level': 'limited',
                    'redirect_url': '/service_orders',
                    'restrictions': ['service_orders_only', 'no_services'],
                    'message': f'Grace period - limited access ({self.grace_period_days - days_past_due} days remaining)'
                }
        
        # Lockdown - strict access control
        elif access_level == 'lockdown':
            if role == 'admin':
                return {
                    'can_login': True,
                    'access_level': 'billing_only',
                    'redirect_url': '/subscription/billing',
                    'restrictions': ['billing_only'],
                    'message': f'Payment overdue by {days_past_due - self.grace_period_days} days - billing only'
                }
            elif role == 'accountant':
                return {
                    'can_login': True,
                    'access_level': 'payment_only',
                    'redirect_url': '/service_orders',
                    'restrictions': ['service_orders_only', 'payment_processing_only', 'no_services', 'no_inventory'],
                    'message': f'Payment overdue - service orders and payments only'
                }
            elif role == 'salonist':
                return {
                    'can_login': False,
                    'access_level': 'locked',
                    'redirect_url': None,
                    'restrictions': ['all'],
                    'message': f'Payment overdue - access locked ({days_past_due - self.grace_period_days} days)'
                }
        
        # Default denial
        return {
            'can_login': False,
            'access_level': 'denied',
            'redirect_url': None,
            'restrictions': ['all'],
            'message': 'Access denied - subscription issue'
        }
    
    def can_access_route(self, user, route_path: str) -> bool:
        """
        Check if user can access a specific route
        
        Args:
            user: Worker object
            route_path: Route path to check
            
        Returns:
            Boolean indicating access permission
        """
        try:
            # Get user access permissions
            access = self.check_user_access(user)
            
            if not access.get('can_login', False):
                return False
            
            restrictions = access.get('restrictions', [])
            
            # Check route permissions based on restrictions
            if 'all' in restrictions:
                return False
            
            if 'billing_only' in restrictions:
                return route_path.startswith('/subscription/billing')
            
            if 'service_orders_only' in restrictions:
                return route_path.startswith('/service_orders')
            
            if 'payment_processing_only' in restrictions:
                return route_path.startswith('/service_orders') and 'payment' in route_path
            
            if 'no_services' in restrictions:
                return not any(route_path.startswith(path) for path in ['/services', '/appointments'])
            
            if 'no_inventory' in restrictions:
                return not any(route_path.startswith(path) for path in ['/stock', '/inventory', '/products'])
            
            # Full access
            return True
            
        except Exception as e:
            logger.error(f"Error checking route access: {str(e)}")
            return False
    
    def get_access_redirect(self, user) -> str:
        """
        Get appropriate redirect URL for user based on access level
        
        Args:
            user: Worker object
            
        Returns:
            Redirect URL
        """
        try:
            access = self.check_user_access(user)
            return access.get('redirect_url', '/dashboard')
            
        except Exception as e:
            logger.error(f"Error getting redirect: {str(e)}")
            return '/dashboard'

# Global instance
access_control_service = AccessControlService()
