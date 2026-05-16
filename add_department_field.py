#!/usr/bin/env python3
"""
Database migration script to add department field to products table
"""

import sqlite3
import os
from datetime import datetime

def add_department_field():
    """Add department field to existing products table"""
    
    # Database file path
    db_path = os.path.join(os.path.dirname(__file__), 'africspa_local.db')
    
    if not os.path.exists(db_path):
        print("❌ Database file not found. Please run the application first to create the database.")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if department column already exists
        cursor.execute("PRAGMA table_info(products)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'department' in columns:
            print("✅ Department field already exists in products table")
            conn.close()
            return True
        
        print("🔧 Adding department field to products table...")
        
        # Add department column
        cursor.execute("""
            ALTER TABLE products 
            ADD COLUMN department VARCHAR(50) DEFAULT 'Hair'
        """)
        
        # Create index on department field
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_products_department 
            ON products(department)
        """)
        
        # Update existing products to have department based on category
        cursor.execute("""
            UPDATE products 
            SET department = CASE 
                WHEN category LIKE '%Hair%' OR category LIKE '%hair%' THEN 'Hair'
                WHEN category LIKE '%Wash%' OR category LIKE '%wash%' THEN 'Wash'
                WHEN category LIKE '%Makeup%' OR category LIKE '%makeup%' THEN 'Makeup'
                WHEN category LIKE '%Nail%' OR category LIKE '%nail%' THEN 'Nails'
                ELSE 'Hair'
            END
            WHERE department IS NULL OR department = ''
        """)
        
        # Commit changes
        conn.commit()
        
        # Verify the migration
        cursor.execute("SELECT COUNT(*) FROM products")
        total_products = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM products WHERE department IS NOT NULL")
        products_with_department = cursor.fetchone()[0]
        
        print(f"✅ Migration completed successfully!")
        print(f"   Total products: {total_products}")
        print(f"   Products with department: {products_with_department}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        return False

def verify_migration():
    """Verify the migration was successful"""
    
    db_path = os.path.join(os.path.dirname(__file__), 'africspa_local.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check table structure
        cursor.execute("PRAGMA table_info(products)")
        columns = cursor.fetchall()
        
        print("\n📋 Products table structure:")
        for column in columns:
            print(f"   - {column[1]} ({column[2]})")
        
        # Check department values
        cursor.execute("SELECT department, COUNT(*) FROM products GROUP BY department")
        dept_counts = cursor.fetchall()
        
        print(f"\n📊 Department distribution:")
        for dept, count in dept_counts:
            print(f"   - {dept}: {count} products")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Verification failed: {str(e)}")

if __name__ == "__main__":
    print("🚀 Starting database migration...")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    if add_department_field():
        verify_migration()
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
    
    print("=" * 50)
