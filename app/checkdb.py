from app import app, db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('product_transactions')]
    
    required = ['invoice_id', 'worker_id', 'department']
    missing = [col for col in required if col not in columns]
    
    if missing:
# DEBUG:         print(f"❌ MISSING COLUMNS: {missing}")
    else:
# DEBUG:         print("✅ Database is in sync with models!")