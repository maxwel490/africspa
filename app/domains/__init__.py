"""
Africa SPA System - Domain-Driven Architecture

This package organizes the application into business domains:

1. authentication - User authentication, OAuth, worker management
2. tenancy       - Multi-tenant salon and branch management
3. scheduling    - Services, appointments, and service orders
4. inventory     - Products, suppliers, and stock management
5. finance       - Revenue, expenses, commissions, reconciliation
6. billing       - Subscriptions, payments, pricing configuration
7. crm           - Client management, chat, support tickets
8. analytics     - Reporting, statistics, system configuration

Each domain contains:
- models/      - SQLAlchemy model definitions
- routes/      - Flask blueprint route handlers
- services/    - Business logic and service classes
- validators/  - Input validation rules
- events/      - Domain event definitions

Shared utilities are in domains/shared/.
"""

DOMAINS = [
    'authentication',
    'tenancy',
    'scheduling',
    'inventory',
    'finance',
    'billing',
    'crm',
    'analytics',
]
