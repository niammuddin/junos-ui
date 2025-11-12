import sqlite3
from src.utils.database import get_db_connection
from src.utils.validators import is_username_valid, is_password_strong
from werkzeug.security import generate_password_hash, check_password_hash

def create_user(username, password, email=None):
    """Membuat user baru dengan validasi"""
    # Validasi input
    username_valid, username_msg = is_username_valid(username)
    if not username_valid:
        return False, username_msg
    
    password_strong, password_msg = is_password_strong(password)
    if not password_strong:
        return False, password_msg
    
    conn = get_db_connection()
    
    try:
        password_hash = generate_password_hash(password)
        conn.execute(
            'INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)',
            (username, password_hash, email)
        )
        conn.commit()
        return True, "User berhasil dibuat"
    except sqlite3.IntegrityError:
        return False, "Username sudah digunakan"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def verify_user(username, password):
    """Verifikasi username dan password untuk login"""
    conn = get_db_connection()
    
    user = conn.execute(
        'SELECT * FROM users WHERE username = ? AND is_active = 1', 
        (username,)
    ).fetchone()
    
    if user:
        if user['failed_login_attempts'] >= 5:
            conn.close()
            return None, "Akun terkunci. Terlalu banyak percobaan gagal."
        
        if check_password_hash(user['password_hash'], password):
            # Reset failed attempts on successful login
            conn.execute(
                'UPDATE users SET failed_login_attempts = 0, last_login = CURRENT_TIMESTAMP WHERE id = ?',
                (user['id'],)
            )
            conn.commit()
            user_data = {
                'id': user['id'],
                'username': user['username'],
                'email': user['email']
            }
            conn.close()
            return user_data, None
        else:
            # Increment failed attempts
            conn.execute(
                'UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE id = ?',
                (user['id'],)
            )
            conn.commit()
            conn.close()
            return None, "Username atau password salah"
    
    conn.close()
    return None, "User tidak ditemukan"

def get_user_by_id(user_id):
    """Mendapatkan user berdasarkan ID"""
    conn = get_db_connection()
    user = conn.execute(
        'SELECT id, username, email FROM users WHERE id = ? AND is_active = 1', 
        (user_id,)
    ).fetchone()
    conn.close()
    
    if user:
        return {
            'id': user['id'],
            'username': user['username'],
            'email': user['email']
        }
    return None

def get_all_users():
    """Mendapatkan semua user (untuk admin)"""
    conn = get_db_connection()
    users = conn.execute(
        'SELECT id, username, email, created_at, last_login FROM users WHERE is_active = 1'
    ).fetchall()
    conn.close()
    return [dict(user) for user in users]

def update_user_password(user_id, new_password):
    """Update password user"""
    password_strong, password_msg = is_password_strong(new_password)
    if not password_strong:
        return False, password_msg
    
    conn = get_db_connection()
    
    try:
        password_hash = generate_password_hash(new_password)
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (password_hash, user_id)
        )
        conn.commit()
        return True, "Password berhasil diupdate"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def delete_user(user_id):
    """Soft delete user"""
    conn = get_db_connection()
    
    try:
        conn.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))
        conn.commit()
        return True, "User berhasil dihapus"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()