"""
CONTINENTAL SCALING MODULE
Pan-African multi-currency, multi-region subscription management
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import json
from dataclasses import dataclass

@dataclass
class RegionalConfig:
    """Configuration for African regions"""
    name: str
    countries: List[str]
    currency: str
    base_multiplier: float
    timezone: str
    
# AFRICAN REGIONAL CONFIGURATION
AFRICAN_REGIONS = {
    'east_africa': RegionalConfig(
        name='East Africa',
        countries=['KE', 'UG', 'TZ', 'RW', 'BI', 'SS', 'SO'],
        currency='KES',
        base_multiplier=1.0,
        timezone='Africa/Nairobi'
    ),
    'west_africa': RegionalConfig(
        name='West Africa', 
        countries=['NG', 'GH', 'CI', 'SN', 'ML', 'BF', 'NE', 'BJ', 'TG', 'SL', 'LR', 'GN'],
        currency='NGN',
        base_multiplier=4.0,  # NGN conversion rate
        timezone='Africa/Lagos'
    ),
    'southern_africa': RegionalConfig(
        name='Southern Africa',
        countries=['ZA', 'ZW', 'ZM', 'MW', 'BW', 'NA', 'SZ', 'LS', 'AO', 'MZ'],
        currency='ZAR', 
        base_multiplier=0.16,  # ZAR conversion rate
        timezone='Africa/Johannesburg'
    ),
    'north_africa': RegionalConfig(
        name='North Africa',
        countries=['EG', 'MA', 'TN', 'DZ', 'LY', 'SD', 'EH'],
        currency='EGP',
        base_multiplier=0.3,  # EGP conversion rate
        timezone='Africa/Cairo'
    ),
    'central_africa': RegionalConfig(
        name='Central Africa',
        countries=['CD', 'CM', 'GA', 'CG', 'CF', 'TD', 'AO', 'ST', 'GQ', 'RW'],
        currency='XAF',
        base_multiplier=0.92,  # XAF conversion rate
        timezone='Africa/Kinshasa'
    )
}

# CONTINENTAL SUBSCRIPTION PLANS
CONTINENTAL_PLANS = {
    'standard': {
        'name': 'Standard',
        'price_per_branch_usd': 30,
        'max_branches': None,  # Unlimited branches
        'max_staff': None,     # Unlimited workers
        'max_clients': None,   # Unlimited clients
        'features': ['appointments', 'advanced_reporting', 'inventory', 'api_access', 'custom_branding', 'multi_currency'],
        'description': '$30 USD per branch, unlimited workers and clients'
    },
    'enterprise': {
        'name': 'Enterprise',
        'price_per_branch_usd': 25,   # Discount for volume
        'min_branches': 50,          # Minimum 50 branches
        'max_branches': None,        # Unlimited branches
        'max_staff': None,           # Unlimited workers
        'max_clients': None,         # Unlimited clients
        'features': ['appointments', 'advanced_reporting', 'inventory', 'api_access', 'custom_branding', 'multi_currency', 'multi_region', 'priority_support', 'dedicated_account_manager'],
        'description': '$25 USD per branch for 50+ branches, unlimited everything'
    }
}

class ContinentalSubscriptionManager:
    """Manages pan-African subscription logic"""
    
    @staticmethod
    def get_region_from_country(country_code: str) -> Optional[str]:
        """Get African region from country code"""
        for region, config in AFRICAN_REGIONS.items():
            if country_code.upper() in config.countries:
                return region
        return None
    
    @staticmethod
    def calculate_regional_price(plan: str, region: str, branch_count: int = 1) -> Dict:
        """Calculate subscription price for specific region and branch count"""
        if plan not in CONTINENTAL_PLANS:
            raise ValueError(f"Invalid plan: {plan}")
        
        if region not in AFRICAN_REGIONS:
            raise ValueError(f"Invalid region: {region}")
        
        plan_config = CONTINENTAL_PLANS[plan]
        region_config = AFRICAN_REGIONS[region]
        
        # Validate enterprise plan requirements
        if plan == 'enterprise' and branch_count < plan_config.get('min_branches', 50):
            raise ValueError(f"Enterprise plan requires minimum {plan_config['min_branches']} branches")
        
        # Calculate USD price (per-branch pricing)
        price_per_branch_usd = plan_config['price_per_branch_usd']
        total_price_usd = price_per_branch_usd * branch_count
        
        # Convert to local currency
        usd_to_local_rate = CurrencyConverter.EXCHANGE_RATES.get(region_config.currency, 1.0)
        total_price_local = total_price_usd * usd_to_local_rate
        
        return {
            'plan': plan_config['name'],
            'region': region_config.name,
            'currency': region_config.currency,
            'branch_count': branch_count,
            'price_per_branch_usd': price_per_branch_usd,
            'total_price_usd': total_price_usd,
            'price_local': total_price_local,
            'max_branches': plan_config['max_branches'],
            'max_staff': plan_config['max_staff'], 
            'max_clients': plan_config['max_clients'],
            'features': plan_config['features'],
            'timezone': region_config.timezone,
            'description': plan_config['description']
        }
    
    @staticmethod
    def get_all_regional_plans() -> Dict:
        """Get all plans across all regions"""
        all_plans = {}
        
        for plan_key in CONTINENTAL_PLANS:
            all_plans[plan_key] = {}
            for region_key in AFRICAN_REGIONS:
                all_plans[plan_key][region_key] = ContinentalSubscriptionManager.calculate_regional_price(
                    plan_key, region_key
                )
        
        return all_plans
    
    @staticmethod
    def upgrade_salon_limits(salon, plan: str):
        """Upgrade salon to continental plan limits"""
        if plan not in CONTINENTAL_PLANS:
            raise ValueError(f"Invalid plan: {plan}")
        
        plan_config = CONTINENTAL_PLANS[plan]
        
        # No subscription plan - all salons get same features
        # Set to None for unlimited
        salon.max_branches = plan_config['max_branches']
        salon.max_staff = plan_config['max_staff']
        salon.max_clients = plan_config['max_clients']
        
        # Enable all features for new pricing model
        salon.feature_appointments = True
        salon.feature_inventory = True
        salon.feature_reporting = True
        salon.feature_api_access = 'api_access' in plan_config['features']
        salon.feature_custom_branding = 'custom_branding' in plan_config['features']
        salon.feature_multi_currency = 'multi_currency' in plan_config['features']
        salon.feature_multi_region = 'multi_region' in plan_config['features']
        
        return salon
    
    @staticmethod
    def calculate_salon_monthly_cost(salon) -> Dict:
        """Calculate monthly cost for a specific salon"""
        branch_count = len([b for b in salon.branches if b.is_active])
        region = salon.region or 'east_africa'
        # No plan - standard pricing for all
        
        try:
            pricing = ContinentalSubscriptionManager.calculate_regional_price(
                'standard', region, branch_count
            )
            
            return {
                'salon_name': salon.name,
                'branch_count': branch_count,
                'plan': pricing['plan'],
                'currency': pricing['currency'],
                'price_per_branch_usd': pricing['price_per_branch_usd'],
                'total_price_usd': pricing['total_price_usd'],
                'total_price_local': pricing['price_local'],
                'unlimited_workers_clients': True
            }
        except Exception as e:
            return {
                'salon_name': salon.name,
                'error': str(e),
                'fallback_price': branch_count * 30  # $30 per branch fallback
            }

class CurrencyConverter:
    """Multi-currency support for pan-African operations"""
    
    # Exchange rates relative to USD (base currency)
    EXCHANGE_RATES = {
        'USD': 1.0,      # US Dollar (base)
        'KES': 120.0,    # Kenyan Shilling
        'NGN': 780.0,    # Nigerian Naira  
        'ZAR': 19.0,     # South African Rand
        'EGP': 31.0,     # Egyptian Pound
        'XAF': 605.0,    # Central African Franc
        'GHS': 12.0,     # Ghanaian Cedi
        'EUR': 0.92      # Euro
    }
    
    @staticmethod
    def convert_amount(amount_usd: float, target_currency: str) -> float:
        """Convert USD amount to target currency"""
        if target_currency not in CurrencyConverter.EXCHANGE_RATES:
            raise ValueError(f"Unsupported currency: {target_currency}")
        
        return amount_usd * CurrencyConverter.EXCHANGE_RATES[target_currency]
    
    @staticmethod
    def format_currency(amount: float, currency: str) -> str:
        """Format amount with currency symbol"""
        symbols = {
            'KES': 'KES', 'NGN': '₦', 'ZAR': 'R', 'EGP': 'E£',
            'XAF': 'FCFA', 'GHS': 'GH₵', 'USD': '$', 'EUR': '€'
        }
        
        symbol = symbols.get(currency, currency)
        return f"{symbol} {amount:,.2f}"

class GeographicPartitioner:
    """Data partitioning strategy for continental scale"""
    
    @staticmethod
    def get_database_shard(country_code: str) -> str:
        """Get database shard for country"""
        region = ContinentalSubscriptionManager.get_region_from_country(country_code)
        return f"africspa_{region}" if region else "africspa_default"
    
    @staticmethod
    def get_cache_key_prefix(salon_id: int, region: str) -> str:
        """Get region-specific cache key prefix"""
        return f"{region}:salon:{salon_id}"
    
    @staticmethod
    def get_tenant_isolation_query(salon_id: int, country_code: str) -> Dict:
        """Get tenant isolation parameters for queries"""
        shard = GeographicPartitioner.get_database_shard(country_code)
        region = ContinentalSubscriptionManager.get_region_from_country(country_code)
        
        return {
            'salon_id': salon_id,
            'shard': shard,
            'region': region,
            'cache_prefix': GeographicPartitioner.get_cache_key_prefix(salon_id, region)
        }

# CONTINENTAL COMPLIANCE FRAMEWORK
COMPLIANCE_REQUIREMENTS = {
    'GDPR': {  # European data protection
        'countries': [],
        'requirements': ['data_portability', 'right_to_be_forgotten', 'consent_management'],
        'data_residency': 'EU'
    },
    'POPIA': {  # South Africa
        'countries': ['ZA'],
        'requirements': ['data_processing_reasons', 'consent_records', 'security_measures'],
        'data_residency': 'ZA'
    },
    'DATA_PROTECTION_ACT': {  # Kenya
        'countries': ['KE'],
        'requirements': ['data_processing_officer', 'consent_management', 'breach_notifications'],
        'data_residency': 'KE'
    }
}

class ComplianceManager:
    """Manages regional compliance requirements"""
    
    @staticmethod
    def get_compliance_for_country(country_code: str) -> List[str]:
        """Get applicable compliance frameworks for country"""
        applicable = []
        
        for framework, config in COMPLIANCE_REQUIREMENTS.items():
            if country_code in config['countries']:
                applicable.append(framework)
        
        return applicable
    
    @staticmethod
    def is_data_residency_compliant(salon_country: str, data_location: str) -> bool:
        """Check if data storage complies with residency requirements"""
        for framework, config in COMPLIANCE_REQUIREMENTS.items():
            if salon_country in config['countries']:
                return data_location == config['data_residency']
        return True  # No specific requirements

# SCALING UTILITIES
def estimate_continental_resources(target_salons: int) -> Dict:
    """Estimate resource requirements for continental scale"""
    
    # Conservative estimates
    avg_branches_per_salon = 5
    avg_staff_per_branch = 10
    avg_clients_per_salon = 500
    
    total_branches = target_salons * avg_branches_per_salon
    total_staff = total_branches * avg_staff_per_branch
    total_clients = target_salons * avg_clients_per_salon
    
    # Database sizing (rough estimates)
    db_size_gb = (target_salons * 0.1) + (total_clients * 0.001) + (total_staff * 0.0005)
    
    # Infrastructure requirements
    return {
        'target_salons': target_salons,
        'estimated_branches': total_branches,
        'estimated_staff': total_staff,
        'estimated_clients': total_clients,
        'database_size_gb': db_size_gb,
        'recommended_db_pool_size': min(100, max(20, target_salons // 50)),
        'recommended_cache_memory_gb': min(32, max(4, target_salons // 250)),
        'monthly_revenue_estimate': target_salons * 15000,  # Average plan price
        'cdn_regions_required': len(set(
            ContinentalSubscriptionManager.get_region_from_country(country)
            for country in ['KE', 'NG', 'ZA', 'EG', 'GH']  # Major markets
        ))
    }

if __name__ == "__main__":
    # Demo continental pricing
# DEBUG:     print("=== CONTINENTAL SUBSCRIPTION PRICING ===")
    
    for plan in ['standard', 'professional', 'enterprise']:
# DEBUG:         print(f"\n{plan.upper()} PLAN:")
        for region in ['east_africa', 'west_africa', 'southern_africa']:
            pricing = ContinentalSubscriptionManager.calculate_regional_price(plan, region)
# DEBUG:             print(f"  {pricing['region']}: {pricing['currency']} {pricing['price_local']:,.2f}")
    
    # Demo resource estimation
# DEBUG:     print("\n=== RESOURCE ESTIMATION FOR 10,000 SALONS ===")
    resources = estimate_continental_resources(10000)
    for key, value in resources.items():
# DEBUG:         print(f"{key}: {value}")
