"""
Scheduling domain routes.

Handles services, appointments, service orders, and service rectification.

Currently served by:
- admin_bp: manage_services, service_orders_analysis
- accountant_bp: record_services, service_orders, new_service_order,
                 edit_service_order, delete_service_order, service_rectification
- salonist_bp: dashboard (work view), work_history

These routes will be migrated here incrementally.
"""
from flask import Blueprint

scheduling_bp = Blueprint('scheduling', __name__, url_prefix='/scheduling')
