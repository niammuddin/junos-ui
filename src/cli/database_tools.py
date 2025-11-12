import sqlite3
import sys
import os

# Tambahkan path root project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.utils.database import get_db_connection, backup_database

def update_database():
    """Update database schema untuk menambah kolom baru"""
    conn = get_db_connection()
    
    new_columns = [
        'failed_login_attempts',
        'last_login', 
        'is_active'
    ]
    
    for column in new_columns:
        try:
            if column == 'failed_login_attempts':
                conn.execute(f'ALTER TABLE users ADD COLUMN {column} INTEGER DEFAULT 0')
            elif column == 'is_active':
                conn.execute(f'ALTER TABLE users ADD COLUMN {column} BOOLEAN DEFAULT 1')
            else:
                conn.execute(f'ALTER TABLE users ADD COLUMN {column} TIMESTAMP')
            print(f"✅ Kolom {column} berhasil ditambahkan")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"ℹ️  Kolom {column} sudah ada")
            else:
                print(f"❌ Error: {e}")

    device_columns = {
        'api_port': 'INTEGER',
        'api_use_ssl': 'BOOLEAN DEFAULT 0',
        'api_verify_ssl': 'BOOLEAN DEFAULT 0',
        'gnmi_port': 'INTEGER',
        'gnmi_use_ssl': 'BOOLEAN DEFAULT 0',
        'gnmi_verify_ssl': 'BOOLEAN DEFAULT 0'
    }

    for column, definition in device_columns.items():
        try:
            conn.execute(f'ALTER TABLE juniper_devices ADD COLUMN {column} {definition}')
            print(f"✅ Kolom {column} (juniper_devices) berhasil ditambahkan")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"ℹ️  Kolom {column} pada juniper_devices sudah ada")
            else:
                print(f"❌ Error menambah kolom {column} pada juniper_devices: {e}")
    
    conn.commit()
    conn.close()
    print("✅ Update database selesai!")

def show_stats():
    """Tampilkan statistik database"""
    from src.utils.database import get_database_stats
    stats = get_database_stats()
    print("=== Database Stats ===")
    for key, value in stats.items():
        print(f"{key}: {value}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == 'update':
            update_database()
        elif sys.argv[1] == 'backup':
            success, message = backup_database()
            print(message)
        elif sys.argv[1] == 'stats':
            show_stats()
    else:
        print("Usage: python database_tools.py [update|backup|stats]")
