import sqlite3
from config import Config
from src.utils.database import get_db_connection
from src.utils.encryption import crypto

def _bool_to_int(value):
    if isinstance(value, str):
        value = value.lower() in {'1', 'true', 'yes', 'on'}
    return 1 if value else 0

def create_juniper_device(
    name,
    ip_address,
    username,
    password,
    description=None,
    api_port=None,
    api_use_ssl=None,
    api_verify_ssl=None,
    gnmi_port=None,
    gnmi_use_ssl=None,
    gnmi_verify_ssl=None
):
    """Membuat device Juniper baru dengan password terenkripsi"""
    conn = get_db_connection()
    
    try:
        encrypted_password = crypto.encrypt(password)

        api_port = api_port if api_port is not None else Config.API_DEFAULT_PORT
        api_use_ssl = _bool_to_int(api_use_ssl if api_use_ssl is not None else Config.API_DEFAULT_USE_SSL)
        api_verify_ssl = _bool_to_int(api_verify_ssl if api_verify_ssl is not None else Config.API_DEFAULT_VERIFY_SSL)
        gnmi_port = gnmi_port if gnmi_port is not None else Config.GNMI_DEFAULT_PORT
        gnmi_use_ssl = _bool_to_int(gnmi_use_ssl if gnmi_use_ssl is not None else Config.GNMI_DEFAULT_USE_SSL)
        gnmi_verify_ssl = _bool_to_int(gnmi_verify_ssl if gnmi_verify_ssl is not None else Config.GNMI_DEFAULT_VERIFY_SSL)

        conn.execute('''
            INSERT INTO juniper_devices 
            (name, ip_address, api_port, username, password, description, api_use_ssl, api_verify_ssl, gnmi_port, gnmi_use_ssl, gnmi_verify_ssl) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, ip_address, api_port, username, encrypted_password, description, api_use_ssl, api_verify_ssl, gnmi_port, gnmi_use_ssl, gnmi_verify_ssl))
        
        conn.commit()
        return True, "Device berhasil ditambahkan"
    except sqlite3.IntegrityError:
        return False, "Nama device sudah digunakan"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def get_all_juniper_devices():
    """Mendapatkan semua devices Juniper"""
    conn = get_db_connection()
    devices = conn.execute('''
        SELECT id, name, ip_address, api_port, username, description, created_at, api_use_ssl, api_verify_ssl, gnmi_port, gnmi_use_ssl, gnmi_verify_ssl
        FROM juniper_devices 
        ORDER BY name
    ''').fetchall()
    conn.close()
    return [dict(device) for device in devices]

def get_juniper_device(device_id):
    """Mendapatkan device Juniper berdasarkan ID"""
    conn = get_db_connection()
    device = conn.execute('''
        SELECT * FROM juniper_devices WHERE id = ?
    ''', (device_id,)).fetchone()
    conn.close()
    
    if device:
        return dict(device)
    return None

def get_juniper_device_password(device_id):
    """Mendapatkan dan decrypt password device"""
    conn = get_db_connection()
    device = conn.execute('''
        SELECT password FROM juniper_devices WHERE id = ?
    ''', (device_id,)).fetchone()
    conn.close()
    
    if device:
        decrypted_password = crypto.decrypt(device['password'])
        if decrypted_password:
            return decrypted_password
    return None

def update_juniper_device(
    device_id,
    name,
    ip_address,
    username,
    password,
    description=None,
    api_port=None,
    api_use_ssl=None,
    api_verify_ssl=None,
    gnmi_port=None,
    gnmi_use_ssl=None,
    gnmi_verify_ssl=None
):
    """Update device Juniper"""
    conn = get_db_connection()
    
    try:
        encrypted_password = crypto.encrypt(password)

        api_port = api_port if api_port is not None else Config.API_DEFAULT_PORT
        api_use_ssl = _bool_to_int(api_use_ssl if api_use_ssl is not None else Config.API_DEFAULT_USE_SSL)
        api_verify_ssl = _bool_to_int(api_verify_ssl if api_verify_ssl is not None else Config.API_DEFAULT_VERIFY_SSL)
        gnmi_port = gnmi_port if gnmi_port is not None else Config.GNMI_DEFAULT_PORT
        gnmi_use_ssl = _bool_to_int(gnmi_use_ssl if gnmi_use_ssl is not None else Config.GNMI_DEFAULT_USE_SSL)
        gnmi_verify_ssl = _bool_to_int(gnmi_verify_ssl if gnmi_verify_ssl is not None else Config.GNMI_DEFAULT_VERIFY_SSL)

        conn.execute('''
            UPDATE juniper_devices 
            SET name=?, ip_address=?, api_port=?, username=?, password=?, description=?, api_use_ssl=?, api_verify_ssl=?, gnmi_port=?, gnmi_use_ssl=?, gnmi_verify_ssl=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (name, ip_address, api_port, username, encrypted_password, description, api_use_ssl, api_verify_ssl, gnmi_port, gnmi_use_ssl, gnmi_verify_ssl, device_id))
        
        conn.commit()
        return True, "Device berhasil diupdate"
    except sqlite3.IntegrityError:
        return False, "Nama device sudah digunakan"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def delete_juniper_device(device_id):
    """HARD DELETE - Hapus permanent dari database"""
    conn = get_db_connection()
    
    try:
        conn.execute('DELETE FROM juniper_devices WHERE id=?', (device_id,))
        conn.commit()
        return True, "Device berhasil dihapus permanent"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def get_juniper_devices_count():
    """Mendapatkan jumlah devices"""
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) as count FROM juniper_devices').fetchone()
    conn.close()
    return count['count'] if count else 0
