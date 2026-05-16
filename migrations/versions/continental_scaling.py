"""
Continental Scaling Migration
Adds multi-currency, multi-region support for pan-African expansion
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers
revision = 'continental_scaling_001'
down_revision = None  # Set to your latest revision
branch_labels = None
depends_on = None

def upgrade():
    """Add continental scaling fields to salons table"""
    
    # Add continental fields to salons table
    op.add_column('salons', sa.Column('country', sa.String(2), default='KE', nullable=False))
    op.add_column('salons', sa.Column('region', sa.String(20), default='east_africa', nullable=False))
    op.add_column('salons', sa.Column('data_residency_location', sa.String(50), default='KE', nullable=False))
    
    # Add indexes for performance
    op.create_index('idx_salons_region', 'salons', ['region'])
    op.create_index('idx_salons_country', 'salons', ['country'])
    op.create_index('idx_salons_data_residency', 'salons', ['data_residency_location'])
    
    # Update existing salons to default region (East Africa)
    op.execute("""
        UPDATE salons 
        SET region = 'east_africa', country = 'KE', data_residency_location = 'KE' 
        WHERE region IS NULL OR country IS NULL
    """)
    
    # Create continental pricing lookup table (optional)
    op.create_table('continental_pricing',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('plan', sa.String(20), nullable=False),
        sa.Column('region', sa.String(20), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('price_local', sa.Float, nullable=False),
        sa.Column('price_kes', sa.Float, nullable=False),
        sa.Column('max_branches', sa.Integer, nullable=False),
        sa.Column('max_staff', sa.Integer, nullable=False),
        sa.Column('max_clients', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow),
        sa.UniqueConstraint('plan', 'region', name='uq_plan_region')
    )
    
    # Populate continental pricing
    pricing_data = [
        # Basic Plan
        ('basic', 'east_africa', 'KES', 5000.0, 5000.0, 5, 25, 1000),
        ('basic', 'west_africa', 'NGN', 20000.0, 5000.0, 5, 25, 1000),
        ('basic', 'southern_africa', 'ZAR', 800.0, 5000.0, 5, 25, 1000),
        ('basic', 'north_africa', 'EGP', 1500.0, 5000.0, 5, 25, 1000),
        ('basic', 'central_africa', 'XAF', 4600.0, 5000.0, 5, 25, 1000),
        
        # Professional Plan
        ('professional', 'east_africa', 'KES', 15000.0, 15000.0, 20, 100, 5000),
        ('professional', 'west_africa', 'NGN', 60000.0, 15000.0, 20, 100, 5000),
        ('professional', 'southern_africa', 'ZAR', 2400.0, 15000.0, 20, 100, 5000),
        ('professional', 'north_africa', 'EGP', 4500.0, 15000.0, 20, 100, 5000),
        ('professional', 'central_africa', 'XAF', 13800.0, 15000.0, 20, 100, 5000),
        
        # Enterprise Plan
        ('enterprise', 'east_africa', 'KES', 50000.0, 50000.0, 100, 500, 25000),
        ('enterprise', 'west_africa', 'NGN', 200000.0, 50000.0, 100, 500, 25000),
        ('enterprise', 'southern_africa', 'ZAR', 8000.0, 50000.0, 100, 500, 25000),
        ('enterprise', 'north_africa', 'EGP', 15000.0, 50000.0, 100, 500, 25000),
        ('enterprise', 'central_africa', 'XAF', 46000.0, 50000.0, 100, 500, 25000),
        
        # Continental Plan
        ('continental', 'east_africa', 'KES', 200000.0, 200000.0, 500, 2500, 100000),
        ('continental', 'west_africa', 'NGN', 800000.0, 200000.0, 500, 2500, 100000),
        ('continental', 'southern_africa', 'ZAR', 32000.0, 200000.0, 500, 2500, 100000),
        ('continental', 'north_africa', 'EGP', 60000.0, 200000.0, 500, 2500, 100000),
        ('continental', 'central_africa', 'XAF', 184000.0, 200000.0, 500, 2500, 100000),
    ]
    
    for plan, region, currency, price_local, price_kes, max_branches, max_staff, max_clients in pricing_data:
        op.execute(f"""
            INSERT INTO continental_pricing 
            (plan, region, currency, price_local, price_kes, max_branches, max_staff, max_clients)
            VALUES ('{plan}', '{region}', '{currency}', {price_local}, {price_kes}, {max_branches}, {max_staff}, {max_clients})
        """)

def downgrade():
    """Remove continental scaling fields"""
    
    # Drop continental pricing table
    op.drop_table('continental_pricing')
    
    # Drop indexes
    op.drop_index('idx_salons_region', 'salons')
    op.drop_index('idx_salons_country', 'salons')
    op.drop_index('idx_salons_data_residency', 'salons')
    
    # Drop columns
    op.drop_column('salons', 'data_residency_location')
    op.drop_column('salons', 'region')
    op.drop_column('salons', 'country')
