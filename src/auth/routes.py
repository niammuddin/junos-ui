from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from src.models.user import verify_user
from src.auth.security import User, limiter

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()[:50]
        password = request.form.get('password', '').strip()[:100]
        
        if not username or not password:
            flash('Username dan password harus diisi!', 'danger')
        else:
            user_data, error = verify_user(username, password)
            if user_data:
                user = User(user_data)
                login_user(user)
                flash('Login berhasil! Selamat datang!', 'success')
                
                # Security check untuk prevent open redirects
                next_page = request.args.get('next')
                if next_page and not next_page.startswith('/'):
                    next_page = None
                return redirect(next_page or url_for('auth.dashboard'))
            else:
                flash(error or 'Login gagal!', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout!', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    from src.models.device import get_juniper_devices_count
    from src.utils.database import get_database_stats
    
    stats = get_database_stats()
    devices_count = get_juniper_devices_count()
    
    return render_template('dashboard.html', 
                         user=current_user, 
                         stats=stats,
                         devices_count=devices_count)

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@auth_bp.route('/admin/users')
@login_required
def admin_users():
    from src.models.user import get_all_users
    users = get_all_users()
    return render_template('admin_users.html', users=users)

@auth_bp.route('/api/health')
def api_health():
    return jsonify({
        'status': 'healthy',
        'service': 'Juniper Login System',
        'version': '1.0.0'
    })

@auth_bp.route('/api/stats')
@login_required
def api_stats():
    from src.utils.database import get_database_stats
    stats = get_database_stats()
    return jsonify(stats)