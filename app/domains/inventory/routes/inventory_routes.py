"""
Inventory domain routes.

Handles product management, stock control, supplier invoices, and inventory transactions.

Currently served by:
- admin_bp: product_costs, stock_control
- accountant_bp: inventory, edit_product, delete_product, shop, process_direct_sale

These routes will be migrated here incrementally.
"""
from flask import Blueprint

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')
