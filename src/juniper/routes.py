import time
import types
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from src.models.device import (
    create_juniper_device, get_all_juniper_devices, get_juniper_device,
    update_juniper_device, delete_juniper_device, get_juniper_device_password
)
from src.juniper.api import (
    test_juniper_connection, 
    get_juniper_bgp_summary, 
    get_juniper_system_info,
    get_juniper_bgp_neighbor_detail,
    get_juniper_policy_options,
    get_juniper_static_routes,
    get_juniper_interfaces,
    start_grpc_traffic_monitoring,
    stop_grpc_traffic_monitoring,
    get_interfaces_for_monitoring,
    get_live_traffic_data
)
from config import Config

juniper_bp = Blueprint('juniper', __name__)


def _parse_checkbox(value, default=False):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        value = value[-1]
    if isinstance(value, str):
        return value.lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _checkbox_value(field_name, default=False):
    values = request.form.getlist(field_name)
    if not values:
        return default
    return _parse_checkbox(values[-1], default=default)


def _rest_connection_kwargs(port, use_ssl, verify_ssl):
    """Normalise REST connection flags for Juniper API calls."""
    resolved_port = port if port is not None else Config.API_DEFAULT_PORT
    use_ssl_flag = bool(use_ssl)
    verify_ssl_flag = bool(verify_ssl)
    rest_insecure = not verify_ssl_flag if use_ssl_flag else True
    return {
        'port': resolved_port,
        'use_ssl': use_ssl_flag,
        'rest_insecure': rest_insecure
    }

@juniper_bp.route('/devices')
@login_required
def devices():
    devices = get_all_juniper_devices()
    return render_template('juniper/devices.html', devices=devices)

@juniper_bp.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name', '').strip()
            ip_address = request.form.get('ip_address', '').strip()
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            description = request.form.get('description', '').strip()
            
            api_port = _safe_int(request.form.get('api_port'), Config.API_DEFAULT_PORT)
            api_use_ssl = _checkbox_value('api_use_ssl')
            api_verify_ssl = _checkbox_value('api_verify_ssl')
            
            gnmi_port = _safe_int(request.form.get('gnmi_port'), Config.GNMI_DEFAULT_PORT)
            gnmi_use_ssl = _checkbox_value('gnmi_use_ssl')
            gnmi_verify_ssl = _checkbox_value('gnmi_verify_ssl')
            
            if not all([name, ip_address, username, password]):
                flash('Nama, IP, Username, dan Password wajib diisi!', 'danger')
            else:
                success, message = create_juniper_device(
                    name=name,
                    ip_address=ip_address,
                    username=username,
                    password=password,
                    description=description,
                    api_port=api_port,
                    api_use_ssl=api_use_ssl,
                    api_verify_ssl=api_verify_ssl,
                    gnmi_port=gnmi_port,
                    gnmi_use_ssl=gnmi_use_ssl,
                    gnmi_verify_ssl=gnmi_verify_ssl
                )
                
                if success:
                    flash(f'✅ Device {name} berhasil ditambahkan!', 'success')
                else:
                    flash(f'❌ Error: {message}', 'danger')
                    
        elif action == 'test':
            ip_address = request.form.get('ip_address', '').strip()
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            api_port = _safe_int(request.form.get('api_port'), Config.API_DEFAULT_PORT)
            api_use_ssl = _checkbox_value('api_use_ssl')
            api_verify_ssl = _checkbox_value('api_verify_ssl')
            
            if not all([ip_address, username, password]):
                flash('IP Address, Username, dan Password wajib diisi!', 'danger')
            else:
                rest_args = _rest_connection_kwargs(api_port, api_use_ssl, api_verify_ssl)
                success, result = test_juniper_connection(
                    ip_address=ip_address,
                    username=username,
                    password=password,
                    **rest_args
                )
                if success:
                    flash('✅ Koneksi berhasil! Device dapat diakses.', 'success')
                else:
                    flash(f'❌ Koneksi gagal: {result}', 'danger')
        
        return redirect(url_for('juniper.config'))
    
    devices = get_all_juniper_devices()
    defaults = types.SimpleNamespace(
        api_default_port=Config.API_DEFAULT_PORT,
        api_use_ssl=Config.API_DEFAULT_USE_SSL,
        api_verify_ssl=Config.API_DEFAULT_VERIFY_SSL,
        gnmi_default_port=Config.GNMI_DEFAULT_PORT,
        gnmi_use_ssl=Config.GNMI_DEFAULT_USE_SSL,
        gnmi_verify_ssl=Config.GNMI_DEFAULT_VERIFY_SSL
    )
    return render_template('juniper/config.html', devices=devices, defaults=defaults)

@juniper_bp.route('/device/<int:device_id>')
@login_required
def device_status(device_id):
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    password = get_juniper_device_password(device_id)

    rest_args = _rest_connection_kwargs(
        device.get('api_port'),
        device.get('api_use_ssl'),
        device.get('api_verify_ssl')
    )

    sys_success, sys_overview = get_juniper_system_info(
        ip_address=device['ip_address'],
        username=device['username'],
        password=password,
        **rest_args
    )

    sys_data = None
    re_data = None
    sys_error = None
    re_error = None

    if sys_success and isinstance(sys_overview, dict):
        sys_data = sys_overview.get('system')
        re_data = sys_overview.get('route_engine')

        if isinstance(sys_data, dict) and 'error' in sys_data:
            sys_error = sys_data['error']
            sys_data = None

        if isinstance(re_data, dict) and 'error' in re_data:
            re_error = re_data['error']
            re_data = None
    else:
        # Jika koneksi awal gagal, tampilkan pesan informatif untuk kedua bagian.
        error_message = (
            f"Gagal terhubung ke device {device['name']} ({device['ip_address']}). "
            "Pastikan device dapat dijangkau dan kredensial sudah benar."
        )
        sys_error = error_message
        re_error = error_message

    return render_template(
        'juniper/status.html',
        device=device,
        sys_data=sys_data,
        re_data=re_data,
        sys_error=sys_error,
        re_error=re_error
    )


@juniper_bp.route('/device/<int:device_id>/bgp')
@login_required
def device_bgp_summary(device_id):
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))

    password = get_juniper_device_password(device_id)

    rest_args = _rest_connection_kwargs(
        device.get('api_port'),
        device.get('api_use_ssl'),
        device.get('api_verify_ssl')
    )

    bgp_success, bgp_data = get_juniper_bgp_summary(
        ip_address=device['ip_address'],
        username=device['username'],
        password=password,
        **rest_args
    )

    return render_template(
        'juniper/bgp_summary.html',
        device=device,
        bgp_data=bgp_data if bgp_success else None,
        bgp_error=None if bgp_success else bgp_data
    )

@juniper_bp.route('/device/<int:device_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_device(device_id):
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        ip_address = request.form.get('ip_address', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        description = request.form.get('description', '').strip()
        
        api_port = _safe_int(request.form.get('api_port'), device.get('api_port'))
        api_use_ssl = _checkbox_value('api_use_ssl', default=device.get('api_use_ssl'))
        api_verify_ssl = _checkbox_value('api_verify_ssl', default=device.get('api_verify_ssl'))
        
        gnmi_port = _safe_int(request.form.get('gnmi_port'), device.get('gnmi_port'))
        gnmi_use_ssl = _checkbox_value('gnmi_use_ssl', default=device.get('gnmi_use_ssl'))
        gnmi_verify_ssl = _checkbox_value('gnmi_verify_ssl', default=device.get('gnmi_verify_ssl'))
        
        if not all([name, ip_address, username]):
            flash('Nama, IP Address, dan Username wajib diisi!', 'danger')
        else:
            # Jika password tidak diisi, gunakan password lama
            if not password:
                password = get_juniper_device_password(device_id)

            success, message = update_juniper_device(
                device_id=device_id,
                name=name,
                ip_address=ip_address,
                username=username,
                password=password,
                description=description,
                api_port=api_port,
                api_use_ssl=api_use_ssl,
                api_verify_ssl=api_verify_ssl,
                gnmi_port=gnmi_port,
                gnmi_use_ssl=gnmi_use_ssl,
                gnmi_verify_ssl=gnmi_verify_ssl
            )
            
            if success:
                flash('✅ Device berhasil diupdate!', 'success')
                return redirect(url_for('juniper.devices'))
            else:
                flash(f'❌ Error: {message}', 'danger')

        # Jika update gagal, isi kembali form dengan data yang baru diinput
        device.update({
            'name': name,
            'ip_address': ip_address,
            'username': username,
            'description': description,
            'api_port': api_port,
            'api_use_ssl': api_use_ssl,
            'api_verify_ssl': api_verify_ssl,
            'gnmi_port': gnmi_port,
            'gnmi_use_ssl': gnmi_use_ssl,
            'gnmi_verify_ssl': gnmi_verify_ssl
        })
    
    return render_template('juniper/edit.html', device=device)

@juniper_bp.route('/device/<int:device_id>/delete', methods=['POST'])
@login_required
def delete_device(device_id):
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    success, message = delete_juniper_device(device_id)
    if success:
        flash('✅ Device berhasil dihapus permanent!', 'success')
    else:
        flash(f'❌ Error: {message}', 'danger')
    
    return redirect(url_for('juniper.devices'))

@juniper_bp.route('/api/test', methods=['POST'])
@login_required
def api_test():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'})
        
        ip_address = data.get('ip_address', '').strip()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        api_port = _safe_int(data.get('api_port'), Config.API_DEFAULT_PORT)
        api_use_ssl = _parse_checkbox(data.get('api_use_ssl'))
        api_verify_ssl = _parse_checkbox(data.get('api_verify_ssl'))
        
        if not all([ip_address, username, password]):
            return jsonify({'success': False, 'message': 'IP, Username, dan Password wajib diisi'})
        
        rest_args = _rest_connection_kwargs(api_port, api_use_ssl, api_verify_ssl)
        success, result = test_juniper_connection(
            ip_address=ip_address,
            username=username,
            password=password,
            **rest_args
        )
        
        return jsonify({
            'success': success,
            'message': result if success else f"Error: {result}"
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})

@juniper_bp.route('/api/bgp-summary/<int:device_id>')
@login_required
def api_bgp_summary(device_id):
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        password = get_juniper_device_password(device_id)
        rest_args = _rest_connection_kwargs(
            device.get('api_port'),
            device.get('api_use_ssl'),
            device.get('api_verify_ssl')
        )
        success, result = get_juniper_bgp_summary(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            **rest_args
        )
        
        return jsonify({
            'success': success,
            'data': result if success else None,
            'message': None if success else result
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})
 
@juniper_bp.route('/device/<int:device_id>/bgp-neighbor/<neighbor_address>')
@login_required
def bgp_neighbor_detail(device_id, neighbor_address):
    """Halaman detail BGP neighbor"""
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    password = get_juniper_device_password(device_id)

    rest_args = _rest_connection_kwargs(
        device.get('api_port'),
        device.get('api_use_ssl'),
        device.get('api_verify_ssl')
    )

    success, neighbor_data = get_juniper_bgp_neighbor_detail(
        ip_address=device['ip_address'],
        username=device['username'],
        password=password,
        neighbor_address=neighbor_address,
        **rest_args
    )
    
    if not success:
        flash(f'❌ Gagal mengambil detail neighbor: {neighbor_data}', 'danger')
        return redirect(url_for('juniper.device_status', device_id=device_id))
    
    return render_template('juniper/bgp_neighbor_detail.html', 
                         device=device,
                         neighbor_address=neighbor_address,
                         neighbor_data=neighbor_data)


@juniper_bp.route('/api/refresh-peer/<int:device_id>/<neighbor_address>')
@login_required
def api_refresh_peer(device_id, neighbor_address):
    """API untuk refresh BGP peer secara real-time"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        password = get_juniper_device_password(device_id)

        rest_args = _rest_connection_kwargs(
            device.get('api_port'),
            device.get('api_use_ssl'),
            device.get('api_verify_ssl')
        )

        success, result = get_juniper_bgp_summary(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            **rest_args
        )
        
        if success:
            for peer in result.get('peers', []):
                if peer.get('peer_address') == neighbor_address:
                    return jsonify({'success': True, 'data': peer})
            
            return jsonify({'success': False, 'message': 'Peer not found'})
        else:
            return jsonify({'success': False, 'message': result})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})
    

@juniper_bp.route('/device/<int:device_id>/policy-options')
@login_required
def policy_options(device_id):
    """Halaman Policy Options (Prefix List, Policy Statement, Community)"""
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    password = get_juniper_device_password(device_id)
    
    rest_args = _rest_connection_kwargs(
        device.get('api_port'),
        device.get('api_use_ssl'),
        device.get('api_verify_ssl')
    )

    success, policy_data = get_juniper_policy_options(
        ip_address=device['ip_address'],
        username=device['username'],
        password=password,
        **rest_args
    )
    
    if not success:
        flash(f'❌ Gagal mengambil policy options: {policy_data}', 'danger')
        return redirect(url_for('juniper.device_status', device_id=device_id))
    
    return render_template('juniper/policy_options.html', 
                         device=device,
                         policy_data=policy_data)

@juniper_bp.route('/api/policy-options/<int:device_id>')
@login_required
def api_policy_options(device_id):
    """API untuk mendapatkan policy options"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        password = get_juniper_device_password(device_id)
        rest_args = _rest_connection_kwargs(
            device.get('api_port'),
            device.get('api_use_ssl'),
            device.get('api_verify_ssl')
        )
        success, result = get_juniper_policy_options(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            **rest_args
        )
        
        return jsonify({
            'success': success,
            'data': result if success else None,
            'message': None if success else result
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})
    

# STATIC ROUTE
@juniper_bp.route('/device/<int:device_id>/static-routes')
@login_required
def static_routes(device_id):
    """Halaman Static Routes"""
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    password = get_juniper_device_password(device_id)
    
    rest_args = _rest_connection_kwargs(
        device.get('api_port'),
        device.get('api_use_ssl'),
        device.get('api_verify_ssl')
    )

    success, routes_data = get_juniper_static_routes(
        ip_address=device['ip_address'],
        username=device['username'],
        password=password,
        **rest_args
    )
    
    if not success:
        flash(f'❌ Gagal mengambil static routes: {routes_data}', 'danger')
        return redirect(url_for('juniper.device_status', device_id=device_id))
    
    return render_template('juniper/static_routes.html', 
                         device=device,
                         routes_data=routes_data)

@juniper_bp.route('/api/static-routes/<int:device_id>')
@login_required
def api_static_routes(device_id):
    """API untuk mendapatkan static routes"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        password = get_juniper_device_password(device_id)
        rest_args = _rest_connection_kwargs(
            device.get('api_port'),
            device.get('api_use_ssl'),
            device.get('api_verify_ssl')
        )
        success, result = get_juniper_static_routes(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            **rest_args
        )
        
        return jsonify({
            'success': success,
            'data': result if success else None,
            'message': None if success else result
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})
    

# INTERFACES
@juniper_bp.route('/device/<int:device_id>/interfaces')
@login_required
def interfaces(device_id):
    """Halaman Interfaces Configuration"""
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    password = get_juniper_device_password(device_id)
    
    rest_args = _rest_connection_kwargs(
        device.get('api_port'),
        device.get('api_use_ssl'),
        device.get('api_verify_ssl')
    )

    success, interfaces_data = get_juniper_interfaces(
        ip_address=device['ip_address'],
        username=device['username'],
        password=password,
        **rest_args
    )
    
    if not success:
        flash(f'❌ Gagal mengambil interfaces: {interfaces_data}', 'danger')
        return redirect(url_for('juniper.device_status', device_id=device_id))
    
    return render_template('juniper/interfaces.html', 
                         device=device,
                         interfaces_data=interfaces_data)

@juniper_bp.route('/api/interfaces/<int:device_id>')
@login_required
def api_interfaces(device_id):
    """API untuk mendapatkan interfaces configuration"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        password = get_juniper_device_password(device_id)
        rest_args = _rest_connection_kwargs(
            device.get('api_port'),
            device.get('api_use_ssl'),
            device.get('api_verify_ssl')
        )
        success, result = get_juniper_interfaces(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            **rest_args
        )
        
        return jsonify({
            'success': success,
            'data': result if success else None,
            'message': None if success else result
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})
    



# TRAFFIC MONITORING
@juniper_bp.route('/device/<int:device_id>/traffic')
@login_required
def interface_traffic(device_id):
    """Halaman Monitoring Live Traffic"""
    device = get_juniper_device(device_id)
    if not device:
        flash('Device tidak ditemukan!', 'danger')
        return redirect(url_for('juniper.devices'))
    
    return render_template('juniper/interface_traffic.html', 
                         device=device)


@juniper_bp.route('/api/traffic/<int:device_id>/interfaces')
@login_required
def api_traffic_interfaces(device_id):
    """API untuk mendapatkan list interfaces untuk monitoring"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        password = get_juniper_device_password(device_id)
        
        rest_args = _rest_connection_kwargs(
            device.get('api_port'),
            device.get('api_use_ssl'),
            device.get('api_verify_ssl')
        )

        success, interfaces = get_interfaces_for_monitoring(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            **rest_args
        )
        
        if success:
            return jsonify({
                'success': True,
                'interfaces': interfaces
            })
        else:
            return jsonify({'success': False, 'message': interfaces})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})

@juniper_bp.route('/api/traffic/<int:device_id>/start', methods=['POST'])
@login_required
def api_traffic_start(device_id):
    """API untuk mulai monitoring traffic"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})

        payload = request.get_json(silent=True) or {}
        interface_filter = payload.get('interface', 'all')
        interval_seconds = payload.get('interval_seconds', 10)

        try:
            interval_seconds = max(int(interval_seconds), 1)
        except (TypeError, ValueError):
            interval_seconds = 10

        password = get_juniper_device_password(device_id)

        success, result = start_grpc_traffic_monitoring(
            ip_address=device['ip_address'],
            username=device['username'],
            password=password,
            interface_filter=interface_filter,
            sample_interval_ms=interval_seconds * 1000,
            gnmi_port=device['gnmi_port'],
            gnmi_use_ssl=device['gnmi_use_ssl'],
            gnmi_verify_ssl=device['gnmi_verify_ssl']
        )

        return jsonify({'success': success, 'message': result})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})


@juniper_bp.route('/api/traffic/<int:device_id>/stop', methods=['POST'])
@login_required
def api_traffic_stop(device_id):
    """API untuk menghentikan monitoring traffic"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})

        success, message = stop_grpc_traffic_monitoring(
            ip_address=device['ip_address'], 
            gnmi_port=device['gnmi_port'], 
            gnmi_use_ssl=device['gnmi_use_ssl'],
            gnmi_verify_ssl=device['gnmi_verify_ssl']
        )
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})

@juniper_bp.route('/api/traffic/<int:device_id>/update')
@login_required
def api_traffic_update(device_id):
    """API untuk mendapatkan update traffic data dari GRPC"""
    try:
        device = get_juniper_device(device_id)
        if not device:
            return jsonify({'success': False, 'message': 'Device not found'})
        
        interface_filter = request.args.get('interface', 'all')
        password = get_juniper_device_password(device_id)
        
        success, traffic_data = get_live_traffic_data(
            ip_address=device['ip_address'], 
            username=device['username'], 
            password=password,
            gnmi_port=device['gnmi_port'],
            gnmi_use_ssl=device['gnmi_use_ssl'],
            gnmi_verify_ssl=device['gnmi_verify_ssl']
        )
        
        if success:
            # Filter data jika interface spesifik dipilih
            if interface_filter != 'all':
                filtered_traffic = {}
                for iface, data in traffic_data.items():
                    if interface_filter in iface:
                        filtered_traffic[iface] = data
                traffic_data = filtered_traffic
            
            return jsonify({
                'success': True,
                'traffic': traffic_data,
                'timestamp': time.time()
            })
        else:
            return jsonify({'success': False, 'message': traffic_data})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
