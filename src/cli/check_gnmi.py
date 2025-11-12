import argparse
import getpass
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config import Config
from src.juniper.gnmi_client import JuniperGNMIClient
from src.juniper.gnmi.gnmi_pb2 import CapabilityRequest
from src.models.device import get_juniper_device, get_juniper_device_password


def run_check(args):
    verify_flag = None

    if args.device_id is not None:
        device = get_juniper_device(args.device_id)
        if not device:
            print(f"⚠️  Device dengan ID {args.device_id} tidak ditemukan di database.")
            sys.exit(1)

        # Override parameter koneksi dengan data dari database
        args.host = device.get('ip_address') or args.host
        args.username = device.get('username') or args.username
        db_password = get_juniper_device_password(args.device_id)
        if db_password:
            args.password = db_password

        # Gunakan konfigurasi gNMI yang tersimpan jika tersedia
        if device.get('gnmi_port') and not getattr(args, '_cli_port_provided', False):
            args.port = int(device['gnmi_port'])
        if device.get('gnmi_use_ssl') is not None and args.tls is None:
            args.tls = bool(device['gnmi_use_ssl'])
        if verify_flag is None:
            verify_flag = device.get('gnmi_verify_ssl')

        if args.host is None:
            print("⚠️  Device tidak memiliki IP address tersimpan. Lengkapi data device terlebih dahulu.")
            sys.exit(1)

    if args.tls is None:
        args.tls = False

    if verify_flag is None and args.tls:
        verify_flag = True

    client = JuniperGNMIClient(
        ip_address=args.host,
        port=args.port,
        username=args.username or '',
        password=args.password or '',
        use_tls=args.tls,
    )

    verify_text = 'n/a'
    if verify_flag is not None:
        verify_text = 'ya' if bool(verify_flag) else 'tidak'

    if args.tls and verify_flag is not None and not bool(verify_flag):
        print("⚠️  Peringatan: Mode TLS dengan skip verify belum sepenuhnya didukung oleh tool ini.")

    print(
        f"🔌 Menghubungkan ke gNMI {args.host}:{args.port} "
        f"(TLS={'ON' if args.tls else 'OFF'}, verify={verify_text}) ...",
        end=' ',
        flush=True
    )
    if not client.connect():
        print("GAGAL")
        print(client.last_error or 'Koneksi ditolak')
        sys.exit(1)
    print("OK")

    stub = client.stub
    metadata = client._metadata()
    try:
        print("ℹ️  Mengambil Capabilities...")
        response = stub.Capabilities(CapabilityRequest(), metadata=metadata)
        print("   gNMI version:", getattr(response, 'gNMI_version', 'unknown'))
        if response.supported_models:
            first_model = response.supported_models[0]
            print(
                "   Model pertama:",
                f"{first_model.name} {first_model.version} ({first_model.organization})",
            )
    except Exception as exc:
        print("⚠️  Capabilities gagal:", exc)

    try:
        if args.interface:
            print(
                f"🔁 Uji subscription singkat untuk interface {args.interface} "
                f"(interval {args.interval}s)..."
            )
            req = client._create_gnmi_subscription(
                args.interface, args.interval * 1000
            )

            def request_iterator():
                yield req

            responses = stub.Subscribe(request_iterator(), metadata=metadata)
            for idx, notif in enumerate(responses):
                print(f"   Notifikasi #{idx+1} diterima")
                updates = []
                if hasattr(notif, 'update') and notif.update.update:
                    updates = list(notif.update.update)
                for upd in updates:
                    path_elems = '/'.join(elem.name for elem in upd.path.elem)
                    print(f"      path: {path_elems}")
                    val = upd.val
                    if val.HasField('json_val'):
                        print("        json_val:", val.json_val[:120], '...')
                    elif val.HasField('json_ietf_val'):
                        print("        json_ietf_val:", val.json_ietf_val[:120], '...')
                    elif val.HasField('int_val'):
                        print("        int_val:", val.int_val)
                    elif val.HasField('uint_val'):
                        print("        uint_val:", val.uint_val)
                    elif val.HasField('double_val'):
                        print("        double_val:", val.double_val)
                    elif val.HasField('float_val'):
                        print("        float_val:", val.float_val)
                    elif val.HasField('string_val'):
                        print("        string_val:", val.string_val[:120], '...')
                if idx >= 2:
                    break
            print("   Subscription berhasil menerima data.")
    except Exception as exc:
        print("⚠️  Subscribe gagal:", exc)


def main():
    parser = argparse.ArgumentParser(description='Diagnostik koneksi gNMI Juniper')
    parser.add_argument('host', nargs='?', help='Alamat IP / hostname perangkat Juniper')
    parser.add_argument('--port', type=int, help='Port gNMI (default: konfigurasi atau 9339)')
    parser.add_argument('-u', '--username', help='Username gNMI')
    parser.add_argument('-p', '--password', help='Password gNMI (jika kosong akan diminta)')
    parser.add_argument('--tls', dest='tls', action='store_true', help='Gunakan TLS channel')
    parser.add_argument('--no-tls', dest='tls', action='store_false', help='Paksa koneksi tanpa TLS')
    parser.set_defaults(tls=None)
    parser.add_argument('--interface', help='Interface spesifik untuk uji subscribe')
    parser.add_argument(
        '--interval',
        type=int,
        default=10,
        help='Interval subscribe (detik) ketika menguji interface. Default 10 detik',
    )
    parser.add_argument(
        '--device-id',
        type=int,
        help='ID device Juniper di database (override host/username/password)',
    )

    args = parser.parse_args()

    # Tandai port yang diberikan via CLI sebelum override
    args._cli_port_provided = args.port is not None

    if args.device_id is None and args.host is None:
        parser.error('Harus menyediakan host atau --device-id')

    if args.port is None:
        args.port = Config.GNMI_DEFAULT_PORT

    if (args.username or args.device_id is None) and args.password is None:
        args.password = getpass.getpass('Password gNMI: ')

    run_check(args)


if __name__ == '__main__':
    main()
