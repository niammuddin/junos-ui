import re
from werkzeug.security import generate_password_hash, check_password_hash

def is_password_strong(password):
    """Validasi kekuatan password"""
    if len(password) < 8:
        return False, "Password minimal 8 karakter"
    if not re.search(r"[A-Z]", password):
        return False, "Password harus mengandung huruf kapital"
    if not re.search(r"[a-z]", password):
        return False, "Password harus mengandung huruf kecil"
    if not re.search(r"[0-9]", password):
        return False, "Password harus mengandung angka"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password harus mengandung karakter khusus"
    return True, "Password kuat"

def is_username_valid(username):
    """Validasi username"""
    if len(username) < 3:
        return False, "Username minimal 3 karakter"
    if len(username) > 20:
        return False, "Username maksimal 20 karakter"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username hanya boleh mengandung huruf, angka, dan underscore"
    return True, "Username valid"