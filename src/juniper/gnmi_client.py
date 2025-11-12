import grpc
import json
import time
import threading
import logging
from typing import Dict, Optional, Callable


# Try to import gNMI protobufs
try:
    from .gnmi.gnmi_pb2 import (
        Path,
        SubscribeRequest,
        Subscription,
        SubscriptionList,
        SubscriptionMode,
    )
    from .gnmi.gnmi_pb2_grpc import gNMIStub
    HAS_GNMI = True
except ImportError as exc:  # pragma: no cover - guarded at runtime
    HAS_GNMI = False
    _GNMI_IMPORT_ERROR = exc


METRIC_MAP = {
    'in_octets': 'in_octets',
    'out_octets': 'out_octets',
    'in_pkts': 'in_pkts',
    'out_pkts': 'out_pkts',
    'in_errors': 'in_errors',
    'out_errors': 'out_errors',
    'if_in_octets': 'in_octets',
    'if_out_octets': 'out_octets',
    'if_in_pkts': 'in_pkts',
    'if_out_pkts': 'out_pkts',
    'if_in_errors': 'in_errors',
    'if_out_errors': 'out_errors',
}


class JuniperGNMIClient:
    def __init__(
        self,
        ip_address: str,
        port: int = 9339,
        username: str = "",
        password: str = "",
        use_tls: bool = False,
    ):
        self.ip_address = ip_address
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.channel = None
        self.stub = None
        self.is_connected = False
        self.is_streaming = False
        self.current_traffic_data = {}
        self.callbacks = []
        self.raw_counters: Dict[str, Dict[str, float]] = {}
        self.prev_snapshots: Dict[str, Dict[str, float]] = {}
        self.last_update_time = time.time()
        self.stream_thread: Optional[threading.Thread] = None
        self.interface_filter: Optional[str] = None
        self.sample_interval_ms: int = 10000
        self.last_error: Optional[str] = None
        self.logger = logging.getLogger(f"JuniperGNMIClient[{ip_address}:{port}]")

    def connect(self) -> bool:
        """Establish gNMI connection to Juniper device"""
        if not HAS_GNMI:
            raise RuntimeError(
                "gNMI protobuf definitions tidak ditemukan. Pastikan file gnmi/gnmi_pb2.py "
                "dan gnmi/gnmi_pb2_grpc.py sudah tersedia."
            )

        try:
            target = f"{self.ip_address}:{self.port}"
            if self.use_tls:
                credentials = grpc.ssl_channel_credentials()
                self.channel = grpc.secure_channel(target, credentials)
            else:
                self.channel = grpc.insecure_channel(target)
            
            try:
                grpc.channel_ready_future(self.channel).result(timeout=10)
                self.stub = gNMIStub(self.channel)
                self.is_connected = True
                self.last_error = None
                self.logger.info("gNMI connected")
                return True
            except grpc.FutureTimeoutError:
                self.last_error = (
                    f"Timeout menghubungi {self.ip_address}:{self.port}. Pastikan gRPC service aktif."
                )
                return False
                
        except Exception as e:
            self.last_error = f"Kesalahan koneksi gNMI: {e}"
            self.logger.error("gNMI connection error", exc_info=True)
            return False

    def disconnect(self):
        """Close gNMI connection"""
        self.stop_interface_monitoring()
        self.is_streaming = False
        if self.channel:
            self.channel.close()
        self.is_connected = False
        self.logger.info("gNMI disconnected")

    def start_interface_monitoring(
        self,
        interface_filter: Optional[str] = None,
        sample_interval_ms: int = 10000,
    ) -> bool:
        """Start monitoring interface traffic via gNMI"""
        if self.is_streaming:
            self.stop_interface_monitoring()

        if not self.is_connected and not self.connect():
            return False

        try:
            self.interface_filter = interface_filter
            self.sample_interval_ms = max(sample_interval_ms, 1000)
            self.is_streaming = True

            # Start streaming dalam thread terpisah
            self.stream_thread = threading.Thread(
                target=self._start_streaming,
                args=(self.interface_filter, self.sample_interval_ms),
                daemon=True
            )
            self.stream_thread.start()
            self.logger.info(
                "gNMI streaming started%s",
                f" filter={interface_filter}" if interface_filter else "",
            )

            return True

        except Exception as e:
            self.last_error = f"gNMI monitoring error: {e}"
            self.logger.error("Unable to start gNMI monitoring", exc_info=True)
            return False

    def stop_interface_monitoring(self):
        """Stop active streaming thread if present"""
        self.is_streaming = False
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1)
        self.stream_thread = None

    def _start_streaming(self, interface_filter: Optional[str], sample_interval: int):
        """Start streaming - menggunakan gNMI real atau simulation"""
        if self.stub is None:
            return
        self._start_gnmi_streaming(interface_filter, sample_interval)

    def _create_gnmi_subscription(
        self,
        interface_filter: Optional[str] = None,
        sample_interval_ms: int = 10000,
    ):
        """Create gNMI subscription request untuk Juniper MX"""
        subscriptions = []
        interval_ns = max(sample_interval_ms, 1000) * 1_000_000

        def _add_path(path_components):
            path = Path()
            for component in path_components:
                if isinstance(component, tuple):
                    name, keys = component
                    elem = path.elem.add()
                    elem.name = name
                    for k, v in keys.items():
                        elem.key[k] = v
                else:
                    path.elem.add(name=component)
            return path

        key = {}
        if interface_filter and interface_filter != "all":
            key = {"name": interface_filter}

        interface_path = _add_path(
            [
                "interfaces",
                ("interface", key),
                "state",
                "counters",
            ]
        )

        subinterface_path = _add_path(
            [
                "interfaces",
                ("interface", key),
                "subinterfaces",
                "subinterface",
                "state",
                "counters",
            ]
        )

        subscriptions.append(
            Subscription(
                path=interface_path,
                mode=SubscriptionMode.SAMPLE,
                sample_interval=interval_ns,
            )
        )
        subscriptions.append(
            Subscription(
                path=subinterface_path,
                mode=SubscriptionMode.SAMPLE,
                sample_interval=interval_ns * 2,
            )
        )

        return SubscribeRequest(
            subscribe=SubscriptionList(
                subscription=subscriptions,
                mode=SubscriptionList.STREAM,
                encoding=0,  # JSON encoding
            )
        )

    def _start_gnmi_streaming(self, interface_filter: Optional[str], sample_interval: int):
        """Real gNMI streaming implementation"""
        try:
            subscription_request = self._create_gnmi_subscription(
                interface_filter, sample_interval
            )

            metadata = self._metadata()

            def request_iterator():
                yield subscription_request

            responses = self.stub.Subscribe(
                request_iterator(),
                metadata=metadata,
            )
            
            for response in responses:
                if not self.is_streaming:
                    break
                self._process_gnmi_response(response)
                
        except Exception as e:
            if getattr(self, 'last_error', None) is None:
                self.last_error = f"gNMI streaming error: {e}"
            self.logger.info("gNMI streaming dihentikan: %s", e)

    def _process_gnmi_response(self, response):
        """Process gNMI response dan update traffic data"""
        try:
            if not hasattr(response, 'update') or not response.HasField('update'):
                return

            notification = response.update
            current_time = time.time()
            touched_interfaces = set()

            prefix = notification.prefix if hasattr(notification, 'prefix') else None
            if prefix and getattr(prefix, 'elem', None):
                prefix_path = '/'.join(f"{elem.name}[{','.join(f'{k}={v}' for k,v in elem.key.items())}]" if elem.key else elem.name for elem in prefix.elem)
                self.logger.debug("Notification prefix: %s", prefix_path)

            for update in notification.update:
                interface_name, metric_key = self._extract_interface_metric(prefix, update.path)
                if not interface_name or not metric_key:
                    self.logger.debug(
                        "Skip update path due to missing interface/metric: %s",
                        '/'.join(elem.name for elem in update.path.elem)
                        if getattr(update.path, 'elem', None)
                        else 'unknown',
                    )
                    continue

                value = self._parse_typed_value(update.val)
                if value is None:
                    self.logger.debug(
                        "Skip update metric %s no value (%s)", metric_key, update.val
                    )
                    continue

                normalized_key = METRIC_MAP.get(metric_key)
                if not normalized_key:
                    self.logger.debug("Metric %s tidak dipetakan", metric_key)
                    continue

                interface_counters = self.raw_counters.setdefault(interface_name, {})
                interface_counters[normalized_key] = float(value)
                touched_interfaces.add(interface_name)

            if touched_interfaces:
                self._calculate_rates(touched_interfaces, current_time)
                self._notify_callbacks()
                for iface in touched_interfaces:
                    self.logger.debug(
                        "Updated counters for %s: in_rate=%.2f kbps out_rate=%.2f kbps",
                        iface,
                        self.current_traffic_data.get(iface, {}).get('in_rate', 0) / 1000,
                        self.current_traffic_data.get(iface, {}).get('out_rate', 0) / 1000,
                    )
        except Exception as e:
            # Reraise untuk penanganan di level atas bila diperlukan
            raise

    def get_current_traffic_data(self) -> Dict:
        """Get current traffic data"""
        return self.current_traffic_data.copy()
    
    def add_callback(self, callback: Callable):
        """Add callback for real-time data updates"""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable):
        """Remove callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def _metadata(self):
        return (
            ('username', self.username or ''),
            ('password', self.password or ''),
        )

    def _extract_interface_metric(self, prefix, path) -> tuple[Optional[str], Optional[str]]:
        interface_name = None
        unit = None
        metric = None

        elems = []
        if prefix is not None and getattr(prefix, 'elem', None):
            elems.extend(list(prefix.elem))
        if path is not None and getattr(path, 'elem', None):
            elems.extend(list(path.elem))

        for index, elem in enumerate(elems):
            if elem.name == "interface" and elem.key:
                interface_name = elem.key.get("name") or elem.key.get("if-name")
            elif elem.name == "subinterface" and elem.key:
                unit = elem.key.get("index") or elem.key.get("if-index")

            if index == len(elems) - 1:
                metric = elem.name.replace('-', '_')

        if interface_name and unit:
            interface_name = f"{interface_name}.{unit}"

        return interface_name, metric

    def _parse_typed_value(self, value):
        if value is None:
            return None

        if value.HasField('int_val'):
            return value.int_val
        if value.HasField('uint_val'):
            return value.uint_val
        if value.HasField('float_val'):
            return value.float_val
        if value.HasField('double_val'):
            return value.double_val
        if hasattr(value, 'HasField') and 'sint_val' in value.DESCRIPTOR.fields_by_name:
            if value.HasField('sint_val'):
                return value.sint_val
        if value.HasField('bool_val'):
            return int(value.bool_val)
        if value.HasField('string_val'):
            try:
                return float(value.string_val)
            except ValueError:
                return None
        if value.HasField('ascii_val'):
            try:
                return float(value.ascii_val.decode())
            except Exception:
                return None
        if value.HasField('json_val'):
            try:
                parsed = json.loads(value.json_val.decode())
                if isinstance(parsed, (int, float)):
                    return parsed
            except Exception:
                return None
        return None

    def _calculate_rates(self, interfaces: set[str], current_time: float):
        for iface in interfaces:
            counters = self.raw_counters.get(iface, {})
            if not counters:
                continue

            previous = self.prev_snapshots.get(iface)
            if previous:
                time_diff = current_time - previous['timestamp']
                if time_diff <= 0:
                    continue

                # Lewati delta pertama setelah streaming dimulai agar tidak ada spike awal
                if not previous.get('primed'):
                    self.current_traffic_data.setdefault(
                        iface,
                        {
                            'in_rate': 0,
                            'out_rate': 0,
                            'in_pps': 0,
                            'out_pps': 0,
                            'in_errors_rate': 0,
                            'out_errors_rate': 0,
                            'timestamp': current_time,
                            'counters': counters.copy(),
                        },
                    )
                    previous['primed'] = True
                    previous['timestamp'] = current_time
                    previous['values'] = counters.copy()
                    self.prev_snapshots[iface] = previous
                    continue

                delta_in_octets = max(counters.get('in_octets', 0) - previous['values'].get('in_octets', 0), 0)
                delta_out_octets = max(counters.get('out_octets', 0) - previous['values'].get('out_octets', 0), 0)
                delta_in_pkts = max(counters.get('in_pkts', 0) - previous['values'].get('in_pkts', 0), 0)
                delta_out_pkts = max(counters.get('out_pkts', 0) - previous['values'].get('out_pkts', 0), 0)
                delta_in_err = max(counters.get('in_errors', 0) - previous['values'].get('in_errors', 0), 0)
                delta_out_err = max(counters.get('out_errors', 0) - previous['values'].get('out_errors', 0), 0)

                self.current_traffic_data[iface] = {
                    'in_rate': (delta_in_octets / time_diff) * 8,
                    'out_rate': (delta_out_octets / time_diff) * 8,
                    'in_pps': delta_in_pkts / time_diff,
                    'out_pps': delta_out_pkts / time_diff,
                    'in_errors_rate': delta_in_err / time_diff,
                    'out_errors_rate': delta_out_err / time_diff,
                    'timestamp': current_time,
                    'counters': counters.copy(),
                }
            else:
                # Pertama kali menerima data, simpan sebagai baseline dengan nilai meter nol
                self.current_traffic_data.setdefault(
                    iface,
                    {
                        'in_rate': 0,
                        'out_rate': 0,
                        'in_pps': 0,
                        'out_pps': 0,
                        'in_errors_rate': 0,
                        'out_errors_rate': 0,
                        'timestamp': current_time,
                        'counters': counters.copy(),
                    },
                )

            primed_flag = previous.get('primed', False) if previous else False
            self.prev_snapshots[iface] = {
                'timestamp': current_time,
                'values': counters.copy(),
                'primed': primed_flag,
            }

        self.last_update_time = current_time

    def _notify_callbacks(self):
        if not self.callbacks:
            return
        snapshot = self.get_current_traffic_data()
        for callback in list(self.callbacks):
            try:
                callback(snapshot)
            except Exception:
                continue

# Global client management
_gnmi_clients: Dict[str, JuniperGNMIClient] = {}

def get_gnmi_client(
    device_id: str,
    ip_address: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool = False,
) -> JuniperGNMIClient:
    """Get or create gNMI client for device"""
    if device_id not in _gnmi_clients:
        _gnmi_clients[device_id] = JuniperGNMIClient(
            ip_address, port, username, password, use_tls
        )
    return _gnmi_clients[device_id]

def start_gnmi_monitoring(
    device_id: str,
    ip_address: str,
    port: int,
    username: str,
    password: str,
    interface_filter: Optional[str] = None,
    sample_interval_ms: Optional[int] = None,
    use_tls: bool = False,
) -> tuple[bool, str]:
    """Start gNMI monitoring for device"""
    try:
        client = get_gnmi_client(
            device_id, ip_address, port, username, password, use_tls
        )
        connected = client.is_connected or client.connect()
        if not connected:
            return False, client.last_error or "Tidak dapat terhubung ke gNMI"

        interval = sample_interval_ms if sample_interval_ms else 10000
        if client.start_interface_monitoring(interface_filter, interval):
            return True, f"gNMI monitoring started for {ip_address}"
        return False, client.last_error or "Failed to start gNMI monitoring"
    except RuntimeError as err:
        if not HAS_GNMI:
            return False, (
                "gNMI protobuf belum tersedia. Jalankan `python -m grpc_tools.protoc` "
                "untuk menghasilkan gnmi/gnmi_pb2.py dan gnmi/gnmi_pb2_grpc.py."
            )
        return False, str(err)
    except Exception as e:
        return False, f"gNMI Error: {str(e)}"

def stop_gnmi_monitoring(device_id: str) -> tuple[bool, str]:
    """Stop gNMI monitoring for device"""
    if device_id in _gnmi_clients:
        client = _gnmi_clients[device_id]
        client.stop_interface_monitoring()
        client.disconnect()
        del _gnmi_clients[device_id]
        return True, "gNMI monitoring stopped"
    return False, "No active monitoring"

def get_gnmi_traffic_data(device_id: str) -> Dict:
    """Get current traffic data from gNMI client"""
    client = _gnmi_clients.get(device_id)
    if not client:
        return {}
    return client.get_current_traffic_data()
