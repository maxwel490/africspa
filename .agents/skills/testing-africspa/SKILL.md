---
name: testing-africspa
description: Test the africspa Flask app's domain model structure and runtime behavior. Use when verifying model changes, domain restructuring, or cross-domain imports.
---

# Testing africspa Domain Models

## Prerequisites
- Python 3.12+ with Flask, SQLAlchemy, flask-login installed
- Repository cloned at `/home/ubuntu/repos/africspa`

## Quick Setup
```bash
cd /home/ubuntu/repos/africspa
export DATABASE_URL="sqlite:///test.db"
```

No MySQL needed for testing — SQLite works via the `DATABASE_URL` env var override.

## Structural Parity Tests
The test script at `/home/ubuntu/test_feature_branch.py` runs 92 tests checking:
- App startup without errors
- Blueprint registration parity (10 blueprints)
- SQLAlchemy table registration (26 tables)
- Model class import compatibility from `app.models`
- Column parity for all 26 models
- Relationship parity for all 26 models
- Foreign key parity for all 26 models
- Utility function availability
- Domain model direct imports from `app.domains.*/models`

## Runtime Method Tests
Beyond schema parity, test cross-domain method execution:
- `Salon.get_subscription_price()` — imports `PricingConfig` from billing domain
- `Salon.get_regional_pricing_info()` — imports `ContinentalSubscriptionManager` from `app.continental_scaling`
- `Worker.get_last_recorded_work_time()` — imports `Appointment` from scheduling domain

These use lazy imports inside method bodies to avoid circular imports.

## Dev Server Verification
```bash
DATABASE_URL="sqlite:///test.db" python3 run.py
```
Expect:
- `GET /` → 302 redirect
- `GET /auth/login` → 200

## Known Issues
- `app/continental_scaling.py` might have syntax errors (IndentationError on line 348-349) — this is a pre-existing issue, not caused by domain restructuring
- SQLAlchemy warnings about overlapping relationships (`Client.client_appointments` / `Service.service_appointments`) are cosmetic and pre-existing

## Model Field Name Reference
Some model fields differ from what you might expect:
- `Client`: use `full_name` (not `name`), requires `branch` field
- `Service`: use `base_price` (not `price`), `commission_front`/`commission_back` (not `commission_type`/`commission_value`)
- `Product`: use `unit_price` (not `selling_price`), `stock_quantity` (not `quantity`), `min_stock_level` (not `min_quantity`), requires `sku`
- `SystemConfig`: use `config_type` (not `value_type`)

## Domain-to-Model Mapping
| Domain | Models |
|--------|--------|
| tenancy | Salon, Branch |
| authentication | Worker, load_user |
| crm | Client, Message, SupportTicket |
| scheduling | Service, Appointment, RectificationLog, ServiceOrder, ServiceOrderItem, DepartmentCategoryConfig |
| inventory | Product, Supplier, SupplierInvoice, ProductTransaction |
| finance | Expense, BackbarGroup, StaffDeduction, MonthlyReconciliation |
| billing | BillingRecord, PricingConfig, PricingHistory, PaymentConfig, ContactConfig |
| analytics | SystemConfig |
