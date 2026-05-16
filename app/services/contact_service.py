"""
Contact Service for retrieving system contact information
"""

from app.models import ContactConfig

class ContactService:
    """Service for managing contact information"""
    
    @staticmethod
    def get_active_config():
        """Get the currently active contact configuration"""
        config = ContactConfig.get_active_config()
        
        # Return default values if no config exists
        if not config:
            return {
                'company_name': 'Africa SPA System',
                'support_email': 'support@africspa.com',
                'billing_email': 'billing@africspa.com',
                'sales_email': 'sales@africspa.com',
                'technical_email': 'tech@africspa.com',
                'support_phone': '+254-700-000-000',
                'sales_phone': '+254-723-456-789',
                'whatsapp_number': '+254-712-345-678',
                'address_line1': '',
                'address_line2': '',
                'city': '',
                'country': '',
                'postal_code': '',
                'website_url': 'https://africspa.com',
                'facebook_url': '',
                'twitter_url': '',
                'instagram_url': '',
                'linkedin_url': '',
                'business_hours': 'Mon-Fri: 8:00 AM - 6:00 PM\nSat: 9:00 AM - 4:00 PM\nSun: Closed'
            }
        
        return {
            'company_name': config.company_name or 'Africa SPA System',
            'support_email': config.support_email or 'support@africspa.com',
            'billing_email': config.billing_email or 'billing@africspa.com',
            'sales_email': config.sales_email or 'sales@africspa.com',
            'technical_email': config.technical_email or 'tech@africspa.com',
            'support_phone': config.support_phone or '+254-700-000-000',
            'sales_phone': config.sales_phone or '+254-723-456-789',
            'whatsapp_number': config.whatsapp_number or '+254-712-345-678',
            'address_line1': config.address_line1 or '',
            'address_line2': config.address_line2 or '',
            'city': config.city or '',
            'country': config.country or '',
            'postal_code': config.postal_code or '',
            'website_url': config.website_url or 'https://africspa.com',
            'facebook_url': config.facebook_url or '',
            'twitter_url': config.twitter_url or '',
            'instagram_url': config.instagram_url or '',
            'linkedin_url': config.linkedin_url or '',
            'business_hours': config.business_hours or 'Mon-Fri: 8:00 AM - 6:00 PM\nSat: 9:00 AM - 4:00 PM\nSun: Closed'
        }
