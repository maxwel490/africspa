#!/usr/bin/env python3
"""
Database migration script to add payment_config column to salons table
Run this script to update the database schema for the tenant payment configuration feature.
"""

import sqlite3
import sys
import os

def add_payment_config_column():
    """Add payment_config column to salons table"""
    
    # Database path
    db_path = os.path.join(os.path.dirname(__file__), 'africspa_local.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(salons)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'payment_config' in columns:
            print("payment_config column already exists in salons table")
            conn.close()
            return True
        
        # Add the payment_config column
        print("Adding payment_config column to salons table...")
        cursor.execute("ALTER TABLE salons ADD COLUMN payment_config TEXT")
        
        # Also add has_backbar column if it doesn't exist
        if 'has_backbar' not in columns:
            print("Adding has_backbar column to salons table...")
            cursor.execute("ALTER TABLE salons ADD COLUMN has_backbar BOOLEAN DEFAULT 1")
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("✅ Database migration completed successfully!")
        print("Added columns:")
        print("  - payment_config (TEXT) - for storing tenant payment configuration")
        if 'has_backbar' not in columns:
            print("  - has_backbar (BOOLEAN) - for enabling/disabling backbar deductions")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Running database migration for payment configuration...")
    success = add_payment_config_column()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("You can now restart the application.")
        sys.exit(0)
    else:
        print("\n💥 Migration failed!")
        print("Please check the error messages above and try again.")
        sys.exit(1)
