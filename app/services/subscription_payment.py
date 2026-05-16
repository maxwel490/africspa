"""
Subscription Payment Service for Africa SPA System

Handles Google Pay payments for tenant subscriptions across African markets.
Simplified implementation for $30 USD per branch per month billing.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from flask import current_app
from app.models import Salon, db

logger = logging.getLogger(__name__)

class SubscriptionPaymentService:
    """Subscription payment processing service"""
    
    def __init__(self):
        self.merchant_name = "Africa SPA System"
        self._pricing_config = None
        
        # Supported currencies for African markets
        self.supported_currencies = {
            'KE': 'KES',  # Kenya
            'NG': 'NGN',  # Nigeria
            'ZA': 'ZAR',  # South Africa
            'EG': 'EGP',  # Egypt
            'GH': 'GHS',  # Ghana
            'CM': 'XAF',  # Cameroon
            'CI': 'XOF',  # Ivory Coast
            'TZ': 'TZS',  # Tanzania
            'UG': 'UGX',  # Uganda
            'US': 'USD',  # United States (fallback)
        }
    
    def get_pricing_config(self):
        """Get current pricing configuration from database"""
        if self._pricing_config is None:
            from app.models import PricingConfig
            self._pricing_config = PricingConfig.get_active_config()
            if not self._pricing_config:
                # Fallback to default pricing if no config exists
                self._pricing_config = type('DefaultPricing', (), {
                    'price_per_branch_usd': 30.0,
                    'currency': 'USD'
                })()
        return self._pricing_config
    
    @property
    def subscription_price(self):
        """Get current subscription price per branch"""
        return self.get_pricing_config().price_per_branch_usd
    
    def calculate_monthly_subscription(self, salon_id: int) -> Dict:
        """
        Calculate monthly subscription cost for a salon
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Dictionary with subscription details
        """
        try:
            salon = Salon.query.get(salon_id)
            if not salon:
                raise Exception("Salon not found")
            
            # Count active branches
            active_branches = len([branch for branch in salon.branches if branch.is_active])
            
            # Calculate total monthly cost
            monthly_cost = active_branches * self.subscription_price
            
            # Get salon's currency
            currency = self.supported_currencies.get(salon.country, 'USD')
            
            # Billing status based on branches
            billing_status = 'active' if active_branches > 0 else 'no_branches'
            
            return {
                'salon_id': salon_id,
                'salon_name': salon.name,
                'active_branches': active_branches,
                'price_per_branch': self.subscription_price,
                'monthly_cost': monthly_cost,
                'currency': 'USD',  # Always charge in USD
                'local_currency': currency,
                'country': salon.country,
                'billing_status': billing_status,
                'message': 'Create your first branch to start billing' if active_branches == 0 else f'Billing active for {active_branches} branch(es)'
            }
            
        except Exception as e:
            logger.error(f"Error calculating subscription: {str(e)}")
            raise Exception(f"Failed to calculate subscription: {str(e)}")
    
    def get_google_pay_config(self, salon_id: int) -> Dict:
        """
        Generate Google Pay configuration for subscription payment
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Dictionary with Google Pay configuration
        """
        try:
            subscription = self.calculate_monthly_subscription(salon_id)
            
            payment_request = {
                "apiVersion": 2,
                "apiVersionMinor": 0,
                "merchantInfo": {
                    "merchantName": self.merchant_name,
                },
                "allowedPaymentMethods": [
                    {
                        "type": "CARD",
                        "parameters": {
                            "allowedAuthMethods": ["PAN_ONLY", "CRYPTOGRAM_3DS"],
                            "allowedCardNetworks": [
                                "AMEX", "DISCOVER", "JCB", "MASTERCARD", "VISA"
                            ],
                            "billingAddressRequired": True,
                            "billingAddressParameters": {
                                "format": "FULL",
                                "phoneNumberRequired": True
                            }
                        },
                        "tokenizationSpecification": {
                            "type": "PAYMENT_GATEWAY",
                            "parameters": {
                                "gateway": "example",
                                "gatewayMerchantId": "africspa_system"
                            }
                        }
                    }
                ],
                "transactionInfo": {
                    "totalPriceStatus": "FINAL",
                    "totalPrice": str(subscription['monthly_cost']),
                    "currencyCode": "USD",
                    "countryCode": subscription['country']
                }
            }
            
            return {
                'environment': 'TEST',
                'paymentRequest': payment_request,
                'subscription': subscription,
                'supportedCountries': self.supported_currencies
            }
            
        except Exception as e:
            logger.error(f"Error generating Google Pay config: {str(e)}")
            raise Exception(f"Failed to generate payment configuration: {str(e)}")
    
    def process_subscription_payment(self, salon_id: int, payment_token: Dict, 
                                    user_id: int) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Process subscription payment using Google Pay
        
        Args:
            salon_id: Salon ID
            payment_token: Google Pay payment token
            user_id: User ID processing the payment
            
        Returns:
            Tuple of (success, transaction_id, response_data)
        """
        try:
            subscription = self.calculate_monthly_subscription(salon_id)
            salon = Salon.query.get(salon_id)
            
            if not salon:
                return False, None, {"error": "Salon not found"}
            
            # Generate transaction ID
            transaction_id = f"SUB_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{salon_id}"
            
            # Process payment (mock implementation)
            payment_result = self._mock_payment_processing(
                payment_token, 
                subscription['monthly_cost'], 
                transaction_id
            )
            
            if payment_result['success']:
                # Update salon subscription details
                salon.last_payment_date = datetime.utcnow()
                salon.next_billing_date = datetime.utcnow() + timedelta(days=30)
                salon.payment_method = 'google_pay'
                
                # Create tenant-isolated billing record
                from app.models import BillingRecord
                from datetime import date
                
                billing_record = BillingRecord(
                    transaction_id=transaction_id,
                    salon_id=salon_id,
                    amount=subscription['monthly_cost'],
                    currency='USD',
                    branches_count=subscription['active_branches'],
                    payment_method='google_pay',
                    payment_status='completed',
                    payment_date=datetime.utcnow(),
                    billing_period_start=date.today().replace(day=1),  # First day of current month
                    billing_period_end=date.today().replace(day=28),  # End of billing period
                    description=f'Monthly subscription for {subscription["active_branches"]} branch(es)',
                    payment_metadata=payment_result,
                    created_by_id=user_id
                )
                
                db.session.add(billing_record)
                db.session.commit()
                
                return True, transaction_id, {
                    'transaction_id': transaction_id,
                    'amount': subscription['monthly_cost'],
                    'currency': 'USD',
                    'branches_paid': subscription['active_branches'],
                    'next_billing_date': salon.next_billing_date.strftime('%Y-%m-%d'),
                    'payment_details': payment_result
                }
            else:
                return False, None, payment_result
                
        except Exception as e:
            logger.error(f"Error processing subscription payment: {str(e)}")
            db.session.rollback()
            return False, None, {"error": str(e)}
    
    def _mock_payment_processing(self, payment_token: Dict, amount: float, 
                              transaction_id: str) -> Dict:
        """
        Mock payment processing for development/testing
        
        In production, replace with actual Google Pay API integration
        """
        try:
            # Simulate processing time
            import time
            time.sleep(1)
            
            # Mock successful payment
            return {
                'success': True,
                'transaction_id': transaction_id,
                'amount': amount,
                'currency': 'USD',
                'payment_method': {
                    'type': 'CARD',
                    'description': 'Visa •••• 4242',
                    'network': 'VISA'
                },
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'COMPLETED'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'transaction_id': transaction_id
            }
    
    def get_subscription_status(self, salon_id: int) -> Dict:
        """
        Get current subscription status for a salon
        
        Args:
            salon_id: Salon ID
            
        Returns:
            Dictionary with subscription status
        """
        try:
            salon = Salon.query.get(salon_id)
            if not salon:
                raise Exception("Salon not found")
            
            now = datetime.utcnow()
            is_active = True
            grace_period_end = None
            days_in_grace = None
            days_overdue = None
            
            # Check if subscription is expired and calculate grace period
            if salon.next_billing_date and salon.next_billing_date < now:
                is_active = False
                grace_period_end = salon.next_billing_date + timedelta(days=7)  # 7-day grace period
                
                if now <= grace_period_end:
                    # In grace period
                    days_in_grace = (grace_period_end - now).days
                else:
                    # Past grace period
                    days_overdue = (now - grace_period_end).days
            
            # Calculate days until next billing
            days_until_billing = None
            if salon.next_billing_date and salon.next_billing_date > now:
                days_until_billing = (salon.next_billing_date - now).days
            
            # Get subscription details
            subscription = self.calculate_monthly_subscription(salon_id)
            
            # Determine status
            if is_active:
                status = 'active'
            elif days_in_grace is not None and days_in_grace > 0:
                status = 'grace_period'
            elif days_overdue is not None and days_overdue > 0:
                status = 'overdue'
            else:
                status = 'inactive'
            
            return {
                'salon_id': salon_id,
                'is_active': is_active,
                'status': status,
                'last_payment_date': salon.last_payment_date.strftime('%Y-%m-%d') if salon.last_payment_date else None,
                'next_billing_date': salon.next_billing_date.strftime('%Y-%m-%d') if salon.next_billing_date else None,
                'grace_period_end': grace_period_end.strftime('%Y-%m-%d') if grace_period_end else None,
                'days_until_billing': days_until_billing,
                'days_in_grace': days_in_grace,
                'days_overdue': days_overdue,
                'payment_method': salon.payment_method,
                'subscription_details': subscription
            }
            
        except Exception as e:
            logger.error(f"Error getting subscription status: {str(e)}")
            raise Exception(f"Failed to get subscription status: {str(e)}")
    
    def get_billing_history(self, salon_id: int, limit: int = 10) -> list:
        """
        Get billing history for a salon (tenant-isolated)
        
        Args:
            salon_id: Salon ID
            limit: Maximum number of records to return
            
        Returns:
            List of billing records
        """
        try:
            # Verify salon exists
            salon = Salon.query.get(salon_id)
            if not salon:
                raise Exception("Salon not found")
            
            # Get tenant-isolated billing records
            from app.models import BillingRecord
            
            billing_records = BillingRecord.query.filter_by(
                salon_id=salon_id
            ).order_by(BillingRecord.payment_date.desc()).limit(limit).all()
            
            # Convert to dict format for template
            history = []
            for record in billing_records:
                history.append({
                    'transaction_id': record.transaction_id,
                    'date': record.payment_date.strftime('%Y-%m-%d'),
                    'amount': record.amount,
                    'currency': record.currency,
                    'branches': record.branches_count,
                    'status': record.payment_status.title(),
                    'payment_method': record.payment_method.replace('_', ' ').title(),
                    'description': record.description,
                    'billing_period_start': record.billing_period_start.strftime('%Y-%m-%d') if record.billing_period_start else None,
                    'billing_period_end': record.billing_period_end.strftime('%Y-%m-%d') if record.billing_period_end else None
                })
            
            # If no real records exist, create a sample record for demonstration
            if not history and salon.last_payment_date:
                subscription = self.calculate_monthly_subscription(salon_id)
                history.append({
                    'transaction_id': f"SUB_{salon.last_payment_date.strftime('%Y%m%d')}_{salon_id}",
                    'date': salon.last_payment_date.strftime('%Y-%m-%d'),
                    'amount': subscription['monthly_cost'],
                    'currency': 'USD',
                    'branches': subscription['active_branches'],
                    'status': 'Completed',
                    'payment_method': 'Google Pay',
                    'description': f'Monthly subscription for {subscription["active_branches"]} branch(es)'
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting billing history: {str(e)}")
            return []

# Global instance
subscription_payment_service = SubscriptionPaymentService()
