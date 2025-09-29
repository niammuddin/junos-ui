import sqlite3
import os
import datetime
import shutil
from config import Config

def get_db_connection():
    """Create database connection"""
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db_connection()
    
    # Users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            failed_login_attempts INTEGER DEFAULT 0,
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Juniper devices table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS juniper_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            ip_address TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            description TEXT,
            api_port INTEGER DEFAULT 3000,
            api_use_ssl BOOLEAN DEFAULT 0,
            api_verify_ssl BOOLEAN DEFAULT 0,
            gnmi_port INTEGER DEFAULT 9339,
            gnmi_use_ssl BOOLEAN DEFAULT 0,
            gnmi_verify_ssl BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Ensure new columns exist (for older database versions)
    # Ambil daftar kolom yang ada
    columns = conn.execute("PRAGMA table_info(juniper_devices)").fetchall()
    existing = {col["name"] for col in columns}

    # --- API port
    if "api_port" not in existing:
        conn.execute("ALTER TABLE juniper_devices ADD COLUMN api_port INTEGER")
        if "port" in existing:
            conn.execute("UPDATE juniper_devices SET api_port = port WHERE api_port IS NULL")
        else:
            conn.execute(
                "UPDATE juniper_devices SET api_port = COALESCE(api_port, ?)",
                (Config.API_DEFAULT_PORT,),
            )

    # --- API use SSL
    if "api_use_ssl" not in existing:
        conn.execute("ALTER TABLE juniper_devices ADD COLUMN api_use_ssl BOOLEAN DEFAULT 0")
    if "rest_use_ssl" in existing:
        conn.execute(
            "UPDATE juniper_devices SET api_use_ssl = rest_use_ssl WHERE rest_use_ssl IS NOT NULL"
        )

    # --- API verify SSL
    if "api_verify_ssl" not in existing:
        conn.execute("ALTER TABLE juniper_devices ADD COLUMN api_verify_ssl BOOLEAN DEFAULT 0")
    if "rest_insecure" in existing:
        conn.execute(
            """
            UPDATE juniper_devices
            SET api_verify_ssl = CASE
                WHEN rest_insecure IS NULL THEN api_verify_ssl
                ELSE (1 - rest_insecure)
            END
            """
        )

    # --- gNMI port
    if "gnmi_port" not in existing:
        conn.execute("ALTER TABLE juniper_devices ADD COLUMN gnmi_port INTEGER")
        conn.execute(
            "UPDATE juniper_devices SET gnmi_port = COALESCE(gnmi_port, ?)",
            (Config.GNMI_DEFAULT_PORT,),
        )

    # --- gNMI use SSL
    if "gnmi_use_ssl" not in existing:
        conn.execute("ALTER TABLE juniper_devices ADD COLUMN gnmi_use_ssl BOOLEAN DEFAULT 0")
    if "gnmi_insecure" in existing:
        conn.execute(
            """
            UPDATE juniper_devices
            SET gnmi_use_ssl = CASE
                WHEN gnmi_insecure IS NULL THEN gnmi_use_ssl
                ELSE (1 - gnmi_insecure)
            END
            """
        )

    # --- gNMI verify SSL
    if "gnmi_verify_ssl" not in existing:
        conn.execute("ALTER TABLE juniper_devices ADD COLUMN gnmi_verify_ssl BOOLEAN DEFAULT 0")


    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

def get_database_stats():
    """Mendapatkan statistik database"""
    conn = get_db_connection()
    
    stats = {}
    
    # User stats
    user_count = conn.execute('SELECT COUNT(*) as count FROM users WHERE is_active=1').fetchone()
    stats['active_users'] = user_count['count'] if user_count else 0
    
    # Device stats
    device_count = conn.execute('SELECT COUNT(*) as count FROM juniper_devices').fetchone()
    stats['active_devices'] = device_count['count'] if device_count else 0
    
    # Total records
    total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()
    stats['total_users'] = total_users['count'] if total_users else 0
    
    total_devices = conn.execute('SELECT COUNT(*) as count FROM juniper_devices').fetchone()
    stats['total_devices'] = total_devices['count'] if total_devices else 0
    
    conn.close()
    return stats

def backup_database():
    """Backup database ke file"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"users_backup_{timestamp}.db"
        shutil.copy2(Config.DATABASE_PATH, backup_file)
        return True, f"Backup berhasil: {backup_file}"
    except Exception as e:
        return False, f"Backup gagal: {str(e)}"
