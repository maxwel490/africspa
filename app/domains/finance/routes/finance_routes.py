"""
Finance domain routes.

Handles finance reports, expenses/overheads, reconciliation, and staff management.

Currently served by:
- admin_bp: dashboard, finance_report, manage_overheads, staff_management,
            save_reconciliation, backbar_groups, add/edit/delete_backbar_group
- accountant_bp: weekly_commissions, settlements, back_bar_management

These routes will be migrated here incrementally to avoid breaking
template references and url_for() calls.
"""
from flask import Blueprint

finance_bp = Blueprint('finance', __name__, url_prefix='/finance')
