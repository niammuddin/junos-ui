import json
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning

from config import Config

if Config.SUPPRESS_TLS_WARNINGS:
    urllib3.disable_warnings(InsecureRequestWarning)

class JuniperAPI:
    def __init__(self, ip_address, port, username, password, use_ssl=False, verify_ssl=False):
        self.username = username
        self.password = password
        
        scheme = 'https' if use_ssl else 'http'
        self.base_url = f"{scheme}://{ip_address}:{port}"
        self.auth = HTTPBasicAuth(username, password)
        self.verify = verify_ssl if use_ssl else False
        self.headers = {
            'Content-Type': 'application/xml',
            'Accept': 'application/json'
        }
    
    def test_connection(self):
        """Test koneksi ke device Juniper"""
        try:
            response = requests.get(
                f"{self.base_url}/rpc/get-system-information",
                auth=self.auth,
                headers=self.headers,
                timeout=10,
                verify=self.verify
            )
            return response.status_code == 200, response.text
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {str(e)}"
    
    def get_bgp_summary(self):
        """Mendapatkan BGP summary information"""
        try:
            response = requests.post(
                f"{self.base_url}/rpc/get-bgp-summary-information",
                auth=self.auth,
                headers=self.headers,
                data="",
                timeout=15,
                verify=self.verify
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return True, self._parse_bgp_summary(data)
                except json.JSONDecodeError as e:
                    return False, f"JSON decode error: {str(e)}"
            else:
                return False, f"API Error: {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Connection error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    def get_system_information(self):
        """Mendapatkan system information dan route engine information sekaligus"""
        try:
            xml_body = """<rpc>
    <get-route-engine-information/>
    <get-system-information/>
</rpc>"""

            response = requests.post(
                f"{self.base_url}/rpc?stop-on-error=1",
                auth=self.auth,
                headers=self.headers,
                data=xml_body,
                timeout=15,
                verify=self.verify
            )

            if response.status_code == 200:
                json_sections = self._extract_json_sections(response.text)
                if not json_sections:
                    print("[JuniperAPI] No JSON sections found in combined system info response, falling back")
                    return self._fallback_system_information()
                system_raw = None
                route_engine_raw = None

                for section in json_sections:
                    try:
                        parsed = json.loads(section)
                    except json.JSONDecodeError as e:
                        return False, f"JSON decode error: {str(e)}"

                    if 'system-information' in parsed and system_raw is None:
                        system_raw = parsed
                    if 'route-engine-information' in parsed and route_engine_raw is None:
                        route_engine_raw = parsed

                system_parsed = self._parse_system_info(system_raw) if system_raw else None
                route_engine_parsed = self._parse_route_engine_info(route_engine_raw) if route_engine_raw else None

                if system_parsed or route_engine_parsed:
                    return True, {
                        'system': system_parsed,
                        'route_engine': route_engine_parsed
                    }

            print(f"[JuniperAPI] Combined system info request failed with status {response.status_code}, falling back")
            return self._fallback_system_information()

        except requests.exceptions.RequestException as e:
            print(f"[JuniperAPI] Combined system info request error: {e}. Falling back")
            return self._fallback_system_information()
        except Exception as e:
            print(f"[JuniperAPI] Unexpected error combined system info: {e}. Falling back")
            return self._fallback_system_information()
    
    def get_policy_options(self):
        """Mendapatkan policy options configuration dengan XML request"""
        try:
            # XML request body sesuai contoh curl
            xml_body = """<get-configuration>
        <configuration>
            <policy-options/>
        </configuration>
    </get-configuration>"""
            
            response = requests.post(
                f"{self.base_url}/rpc?stop-on-error=1",
                auth=self.auth,
                headers=self.headers,
                data=xml_body,
                timeout=15,
                verify=self.verify
            )
            
            print(f"🔧 POLICY OPTIONS STATUS: {response.status_code}")
            print(f"🔧 RESPONSE TEXT: {response.text[:500]}...")  # Debug pertama 500 karakter
            # print(f"🔧 RESPONSE TEXT: {response.text}")
            
            if response.status_code == 200:
                try:
                    # Bersihkan response dari MIME boundary
                    cleaned_response = self._clean_mime_response(response.text)
                    data = json.loads(cleaned_response)
                    print("🔧 POLICY OPTIONS JSON PARSED SUCCESSFULLY")
                    return True, self._parse_policy_options(data)
                except json.JSONDecodeError as e:
                    print(f"🔧 JSON DECODE ERROR: {e}")
                    # Coba parsing manual jika masih gagal
                    return self._parse_policy_options_manual(response.text)
            else:
                error_msg = f"API Error: {response.status_code} - {response.text}"
                print(f"🔧 {error_msg}")
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Connection error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg

    def _clean_mime_response(self, response_text):
        """Extract the first complete JSON object from a multipart response."""
        if not response_text:
            return response_text

        start = response_text.find('{')
        if start == -1:
            return response_text

        depth = 0
        in_string = False
        escape = False

        for idx in range(start, len(response_text)):
            ch = response_text[idx]

            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    cleaned_json = response_text[start : idx + 1]
                    print(f"🔧 CLEANED JSON: {cleaned_json[:300]}...")
                    return cleaned_json

        # Fallback: return substring from first JSON brace
        cleaned_json = response_text[start:]
        print(f"🔧 CLEANED JSON (fallback): {cleaned_json[:300]}...")
        return cleaned_json

    def _extract_json_sections(self, response_text):
        """Ekstrak setiap bagian JSON dari response multipart"""
        lines = response_text.splitlines()
        boundary = None

        for line in lines:
            line = line.strip()
            if line.startswith('--') and len(line) > 2:
                boundary = line
                break

        if not boundary:
            cleaned = self._clean_mime_response(response_text)
            return [cleaned] if cleaned else []

        parts = response_text.split(boundary)
        sections = []

        for part in parts:
            part = part.strip()
            if not part or part == '--':
                continue

            if '{' not in part:
                continue

            json_part = part[part.index('{'):]
            json_part = json_part.strip()
            if json_part.endswith('--'):
                json_part = json_part[:-2].strip()

            if json_part:
                sections.append(json_part)

        return sections

    def _parse_policy_options_manual(self, response_text):
        """Fallback parsing manual jika JSON parsing gagal"""
        try:
            # Coba ekstrak JSON secara manual
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                return True, self._parse_policy_options(data)
            else:
                return False, "Tidak dapat menemukan JSON dalam response"
        except Exception as e:
            return False, f"Manual parsing error: {str(e)}"

    def _parse_bgp_summary(self, data):
        """Parse BGP summary data - versi sederhana"""
        try:
            # Ekstrak bgp-information
            bgp_info = self._extract_bgp_info(data)
            
            if not bgp_info:
                return {'error': 'BGP information not found'}
            
            # Parse hanya informasi penting
            result = {
                'summary': self._parse_bgp_summary_info(bgp_info),
                'peers': self._parse_bgp_peers_simple(bgp_info),
                'ribs': self._parse_bgp_ribs_simple(bgp_info)
            }
            
            return result
            
        except Exception as e:
            return {'error': f"Parse error: {str(e)}"}
    
    def _extract_bgp_info(self, data):
        """Extract bgp-information"""
        bgp_info = None
        
        if 'bgp-information' in data:
            bgp_info = data['bgp-information']
        elif 'rpc-reply' in data and 'bgp-information' in data['rpc-reply']:
            bgp_info = data['rpc-reply']['bgp-information']
        elif isinstance(data, list) and len(data) > 0:
            for item in data:
                if 'bgp-information' in item:
                    bgp_info = item['bgp-information']
                    break
        
        if isinstance(bgp_info, list) and len(bgp_info) > 0:
            bgp_info = bgp_info[0]
            
        return bgp_info
    
    def _parse_bgp_summary_info(self, bgp_info):
        """Parse summary information yang penting saja"""
        summary = {
            'peer_count': self._get_nested_value(bgp_info, ['peer-count', 0, 'data'], '0'),
            'group_count': self._get_nested_value(bgp_info, ['group-count', 0, 'data'], '0'),
            'down_peer_count': self._get_nested_value(bgp_info, ['down-peer-count', 0, 'data'], '0'),
            'bgp_thread_mode': self._get_nested_value(bgp_info, ['bgp-thread-mode', 0, 'data'], 'N/A')
        }
        
        # Hitung established peers
        peers = bgp_info.get('bgp-peer', [])
        if not isinstance(peers, list):
            peers = [peers] if peers else []
        
        established_count = 0
        for peer in peers:
            if peer and self._get_nested_value(peer, ['peer-state', 0, 'data']) == 'Established':
                established_count += 1
        
        summary['established_peer_count'] = established_count
        return summary
    
    def _parse_bgp_peers_simple(self, bgp_info):
        """Parse peer information yang penting saja"""
        peers = []
        bgp_peers = bgp_info.get('bgp-peer', [])
        
        if not isinstance(bgp_peers, list):
            bgp_peers = [bgp_peers] if bgp_peers else []
        
        for peer in bgp_peers:
            if not peer:
                continue
                
            peer_data = {
                'peer_address': self._get_nested_value(peer, ['peer-address', 0, 'data'], 'N/A'),
                'peer_as': self._get_nested_value(peer, ['peer-as', 0, 'data'], 'N/A'),
                'peer_state': self._get_nested_value(peer, ['peer-state', 0, 'data'], 'N/A'),
                'description': self._get_nested_value(peer, ['description', 0, 'data'], ''),
                'input_messages': self._get_nested_value(peer, ['input-messages', 0, 'data'], '0'),
                'output_messages': self._get_nested_value(peer, ['output-messages', 0, 'data'], '0'),
                'flap_count': self._get_nested_value(peer, ['flap-count', 0, 'data'], '0'),
                'elapsed_time': self._get_nested_value(peer, ['elapsed-time', 0, 'data'], 'N/A'),
            }
            
            # Parse RIBs untuk peer (hanya yang penting)
            peer_ribs = []
            bgp_ribs = peer.get('bgp-rib', [])
            if not isinstance(bgp_ribs, list):
                bgp_ribs = [bgp_ribs] if bgp_ribs else []
            
            for rib in bgp_ribs:
                if not rib:
                    continue
                rib_data = {
                    'name': self._get_nested_value(rib, ['name', 0, 'data'], 'N/A'),
                    'active_prefix_count': self._get_nested_value(rib, ['active-prefix-count', 0, 'data'], '0'),
                    'received_prefix_count': self._get_nested_value(rib, ['received-prefix-count', 0, 'data'], '0'),
                }
                peer_ribs.append(rib_data)
            
            peer_data['ribs'] = peer_ribs
            peers.append(peer_data)
        
        return peers
    
    def _parse_bgp_ribs_simple(self, bgp_info):
        """Parse RIB information yang penting saja"""
        ribs = []
        bgp_ribs = bgp_info.get('bgp-rib', [])
        
        if not isinstance(bgp_ribs, list):
            bgp_ribs = [bgp_ribs] if bgp_ribs else []
        
        for rib in bgp_ribs:
            if not rib:
                continue
                
            rib_data = {
                'name': self._get_nested_value(rib, ['name', 0, 'data'], 'N/A'),
                'total_prefix_count': self._get_nested_value(rib, ['total-prefix-count', 0, 'data'], '0'),
                'active_prefix_count': self._get_nested_value(rib, ['active-prefix-count', 0, 'data'], '0'),
                'received_prefix_count': self._get_nested_value(rib, ['received-prefix-count', 0, 'data'], '0'),
                'accepted_prefix_count': self._get_nested_value(rib, ['accepted-prefix-count', 0, 'data'], '0'),
            }
            ribs.append(rib_data)
        
        return ribs
    
    def _extract_block(self, data, key):
        if isinstance(data, dict):
            if key in data:
                return {key: data[key]}
            for value in data.values():
                result = self._extract_block(value, key)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._extract_block(item, key)
                if result:
                    return result
        return None

    def _parse_system_info(self, data):
        """Parse system information data"""
        try:
            extracted = self._extract_block(data, 'system-information')
            if not extracted:
                return {'error': 'System information structure not found'}

            sys_info = extracted.get('system-information', [])

            if isinstance(sys_info, list) and len(sys_info) > 0:
                sys_info = sys_info[0]
            
            result = {
                'hostname': self._get_nested_value(sys_info, ['host-name', 0, 'data'], 'N/A'),
                'model': self._get_nested_value(sys_info, ['hardware-model', 0, 'data'], 'N/A'),
                'os_version': self._get_nested_value(sys_info, ['os-version', 0, 'data'], 'N/A'),
                'serial_number': self._get_nested_value(sys_info, ['serial-number', 0, 'data'], 'N/A'),
            }
            
            return result
            
        except Exception as e:
            return {'error': f"Parse error: {str(e)}"}
    
    def _parse_policy_options(self, data):
        """Parse policy options data dari configuration"""
        try:
            # Struktur berdasarkan contoh JSON yang diberikan
            config = data.get('configuration', {})
            policy_options = config.get('policy-options', {})
            
            result = {
                'prefix_lists': self._parse_prefix_lists(policy_options.get('prefix-list', [])),
                'policy_statements': self._parse_policy_statements(policy_options.get('policy-statement', [])),
                'communities': self._parse_communities(policy_options.get('community', [])),
                'last_updated': config.get('@', {}).get('junos:changed-localtime', 'N/A')
            }
            
            return result
            
        except Exception as e:
            return {'error': f"Parse error: {str(e)}"}
    
    def _parse_prefix_lists(self, prefix_lists):
        """Parse prefix lists"""
        if not isinstance(prefix_lists, list):
            prefix_lists = [prefix_lists] if prefix_lists else []
        
        result = []
        for pl in prefix_lists:
            if not pl:
                continue
                
            prefix_list = {
                'name': pl.get('name', 'N/A'),
                'prefixes': []
            }
            
            prefix_items = pl.get('prefix-list-item', [])
            if not isinstance(prefix_items, list):
                prefix_items = [prefix_items] if prefix_items else []
            
            for item in prefix_items:
                if item and 'name' in item:
                    prefix_list['prefixes'].append(item['name'])
            
            result.append(prefix_list)
        
        return result
    
    def _parse_policy_statements(self, policy_statements):
        """Parse policy statements"""
        if not isinstance(policy_statements, list):
            policy_statements = [policy_statements] if policy_statements else []
        
        result = []
        for ps in policy_statements:
            if not ps:
                continue
                
            policy = {
                'name': ps.get('name', 'N/A'),
                'terms': [],
                'max_local_preference': None,
                'max_as_path_count': None
            }
            
            terms = ps.get('term', [])
            if not isinstance(terms, list):
                terms = [terms] if terms else []
            
            for term in terms:
                if not term:
                    continue
                    
                term_data = {
                    'name': term.get('name', 'N/A'),
                    'from': self._parse_term_conditions(term.get('from', {})),
                    'then': self._parse_then_actions(term.get('then', {}))
                }
                
                # Handle default then action untuk policy level
                if not term_data['then'] and 'then' in ps:
                    term_data['default_then'] = self._parse_then_actions(ps.get('then', {}))
                
                policy['terms'].append(term_data)
                
                # Track metrics for sorting/filtering di UI
                term_then = term_data.get('then', {})
                lp_value = term_then.get('local_preference')
                if isinstance(lp_value, (int, float)):
                    if policy['max_local_preference'] is None or lp_value > policy['max_local_preference']:
                        policy['max_local_preference'] = lp_value
                
                as_count = term_then.get('as_path_count')
                if isinstance(as_count, int):
                    if policy['max_as_path_count'] is None or as_count > policy['max_as_path_count']:
                        policy['max_as_path_count'] = as_count
            
            result.append(policy)
        
        return result
    
    def _parse_term_conditions(self, from_conditions):
        """Parse 'from' conditions dalam term"""
        conditions = {}
        
        if from_conditions.get('prefix-list'):
            prefix_lists = from_conditions['prefix-list']
            if not isinstance(prefix_lists, list):
                prefix_lists = [prefix_lists]
            conditions['prefix_list'] = [pl.get('name', 'N/A') for pl in prefix_lists if pl]
        
        if from_conditions.get('route-filter'):
            route_filters = from_conditions['route-filter']
            if not isinstance(route_filters, list):
                route_filters = [route_filters]
            conditions['route_filter'] = []
            for rf in route_filters:
                if rf:
                    filter_data = {
                        'address': rf.get('address', 'N/A'),
                        'exact': 'exact' in rf
                    }
                    conditions['route_filter'].append(filter_data)
        
        return conditions
    
    def _parse_then_actions(self, then_actions):
        """Parse 'then' actions"""
        actions = {}
        
        if then_actions.get('accept') is not None:
            actions['accept'] = True
        elif then_actions.get('reject') is not None:
            actions['reject'] = True
        
        lp_data = then_actions.get('local-preference')
        if lp_data is not None:
            lp_value = None
            if isinstance(lp_data, dict):
                lp_value = lp_data.get('local-preference')
            else:
                lp_value = lp_data
            try:
                actions['local_preference'] = int(lp_value)
            except (TypeError, ValueError):
                actions['local_preference'] = lp_value
        
        as_path_data = then_actions.get('as-path-prepend')
        if as_path_data is not None:
            as_path_parts = []
            if isinstance(as_path_data, str):
                as_path_parts = [part for part in as_path_data.split() if part]
            elif isinstance(as_path_data, list):
                for entry in as_path_data:
                    if isinstance(entry, str):
                        as_path_parts.extend([part for part in entry.split() if part])
                    elif entry:
                        as_path_parts.append(str(entry))
            elif isinstance(as_path_data, dict):
                for value in as_path_data.values():
                    if isinstance(value, str):
                        as_path_parts.extend([part for part in value.split() if part])
            else:
                as_path_parts.append(str(as_path_data))
            
            if as_path_parts:
                actions['as_path_prepend'] = ' '.join(as_path_parts)
                actions['as_path_count'] = len(as_path_parts)
        
        if then_actions.get('community'):
            communities = then_actions['community']
            if not isinstance(communities, list):
                communities = [communities]
            for comm in communities:
                if comm and comm.get('add') is not None:
                    actions['community_add'] = comm.get('community-name', 'N/A')
        
        return actions
    
    def _parse_communities(self, communities):
        """Parse community definitions"""
        if not isinstance(communities, list):
            communities = [communities] if communities else []
        
        result = []
        for comm in communities:
            if not comm:
                continue
                
            community = {
                'name': comm.get('name', 'N/A'),
                'members': []
            }
            
            members = comm.get('members', [])
            if isinstance(members, str):
                community['members'] = [members]
            elif isinstance(members, list):
                community['members'] = members
            
            result.append(community)
        
        return result

    def _get_nested_value(self, data, keys, default='N/A'):
        """Helper function to safely get nested values"""
        try:
            current = data
            for key in keys:
                if current is None:
                    return default
                    
                if isinstance(current, list) and isinstance(key, int):
                    if key < len(current):
                        current = current[key]
                    else:
                        return default
                elif isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            
            return current if current is not None else default
        except (KeyError, IndexError, TypeError, AttributeError):
            return default

    def get_bgp_neighbor_detail(self, neighbor_address):
        """Mendapatkan detail informasi BGP neighbor"""
        try:
            print(f"🔧 GETTING BGP NEIGHBOR DETAIL: {neighbor_address}")
            response = requests.get(
                f"{self.base_url}/rpc/get-bgp-neighbor-information?neighbor-address={neighbor_address}",
                auth=self.auth,
                headers=self.headers,
                timeout=15,
                verify=self.verify
            )
            
            print(f"🔧 NEIGHBOR DETAIL STATUS: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"🔧 NEIGHBOR DETAIL JSON PARSED SUCCESSFULLY")
                    return True, self._parse_bgp_neighbor_detail(data)
                except json.JSONDecodeError as e:
                    print(f"🔧 JSON DECODE ERROR: {e}")
                    return False, f"JSON decode error: {str(e)}"
            else:
                error_msg = f"API Error: {response.status_code} - {response.text}"
                print(f"🔧 {error_msg}")
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Connection error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg

    def _parse_bgp_neighbor_detail(self, data):
        """Parse detail informasi BGP neighbor"""
        try:
            print(f"🔧 PARSING BGP NEIGHBOR DETAIL...")
            
            # Ekstrak bgp-information
            bgp_info = self._extract_bgp_info(data)
            
            if not bgp_info:
                return {'error': 'BGP neighbor information not found'}
            
            # Extract peer information
            bgp_peers = bgp_info.get('bgp-peer', [])
            if not isinstance(bgp_peers, list):
                bgp_peers = [bgp_peers] if bgp_peers else []
            
            if not bgp_peers:
                return {'error': 'No peer information found'}
            
            peer = bgp_peers[0]  # Ambil peer pertama
            
            # Parse detail informasi
            result = {
                'basic_info': self._parse_basic_neighbor_info(peer),
                'session_info': self._parse_session_info(peer),
                'statistics': self._parse_neighbor_statistics(peer),
                'options': self._parse_neighbor_options(peer),
                'errors': self._parse_neighbor_errors(peer),
                'ribs': self._parse_neighbor_ribs(peer),
                'bfd_info': self._parse_bfd_info(peer)
            }
            
            print(f"🔧 NEIGHBOR DETAIL PARSING COMPLETED")
            return result
            
        except Exception as e:
            error_msg = f"Parse error: {str(e)}"
            print(f"🔧 {error_msg}")
            import traceback
            print(f"🔧 TRACEBACK: {traceback.format_exc()}")
            return {'error': error_msg}

    def _parse_basic_neighbor_info(self, peer):
        """Parse informasi dasar neighbor"""
        return {
            'peer_address': self._get_nested_value(peer, ['peer-address', 0, 'data'], 'N/A'),
            'peer_as': self._get_nested_value(peer, ['peer-as', 0, 'data'], 'N/A'),
            'local_address': self._get_nested_value(peer, ['local-address', 0, 'data'], 'N/A'),
            'local_as': self._get_nested_value(peer, ['local-as', 0, 'data'], 'N/A'),
            'description': self._get_nested_value(peer, ['description', 0, 'data'], ''),
            'peer_group': self._get_nested_value(peer, ['peer-group', 0, 'data'], 'N/A'),
            'peer_type': self._get_nested_value(peer, ['peer-type', 0, 'data'], 'N/A'),
            'peer_state': self._get_nested_value(peer, ['peer-state', 0, 'data'], 'N/A'),
            'peer_flags': self._get_nested_value(peer, ['peer-flags', 0, 'data'], 'N/A'),
            'local_interface_name': self._get_nested_value(peer, ['local-interface-name', 0, 'data'], 'N/A'),
            'peer_id': self._get_nested_value(peer, ['peer-id', 0, 'data'], 'N/A'),
            'local_id': self._get_nested_value(peer, ['local-id', 0, 'data'], 'N/A')
        }

    def _parse_session_info(self, peer):
        """Parse informasi session"""
        return {
            'last_state': self._get_nested_value(peer, ['last-state', 0, 'data'], 'N/A'),
            'last_event': self._get_nested_value(peer, ['last-event', 0, 'data'], 'N/A'),
            'last_error': self._get_nested_value(peer, ['last-error', 0, 'data'], 'N/A'),
            'flap_count': self._get_nested_value(peer, ['flap-count', 0, 'data'], '0'),
            'last_flap_event': self._get_nested_value(peer, ['last-flap-event', 0, 'data'], 'N/A'),
            'active_holdtime': self._get_nested_value(peer, ['active-holdtime', 0, 'data'], 'N/A'),
            'keepalive_interval': self._get_nested_value(peer, ['keepalive-interval', 0, 'data'], 'N/A'),
            'peer_restart_nlri_configured': self._get_nested_value(peer, ['peer-restart-nlri-configured', 0, 'data'], 'N/A'),
            'peer_restart_nlri_negotiated': self._get_nested_value(peer, ['peer-restart-nlri-negotiated', 0, 'data'], 'N/A')
        }

    def _parse_neighbor_statistics(self, peer):
        """Parse statistics neighbor"""
        return {
            'input_messages': self._get_nested_value(peer, ['input-messages', 0, 'data'], '0'),
            'input_updates': self._get_nested_value(peer, ['input-updates', 0, 'data'], '0'),
            'input_refreshes': self._get_nested_value(peer, ['input-refreshes', 0, 'data'], '0'),
            'input_octets': self._get_nested_value(peer, ['input-octets', 0, 'data'], '0'),
            'output_messages': self._get_nested_value(peer, ['output-messages', 0, 'data'], '0'),
            'output_updates': self._get_nested_value(peer, ['output-updates', 0, 'data'], '0'),
            'output_refreshes': self._get_nested_value(peer, ['output-refreshes', 0, 'data'], '0'),
            'output_octets': self._get_nested_value(peer, ['output-octets', 0, 'data'], '0'),
            'last_received': self._get_nested_value(peer, ['last-received', 0, 'data'], 'N/A'),
            'last_sent': self._get_nested_value(peer, ['last-sent', 0, 'data'], 'N/A'),
            'last_checked': self._get_nested_value(peer, ['last-checked', 0, 'data'], 'N/A')
        }

    def _parse_neighbor_options(self, peer):
        """Parse options neighbor"""
        options_info = peer.get('bgp-option-information', [])
        if not isinstance(options_info, list) or not options_info:
            return {}
        
        options = options_info[0] if options_info else {}
        
        return {
            'export_policy': self._get_nested_value(options, ['export-policy', 0, 'data'], 'N/A'),
            'import_policy': self._get_nested_value(options, ['import-policy', 0, 'data'], 'N/A'),
            'bgp_options': self._get_nested_value(options, ['bgp-options', 0, 'data'], 'N/A'),
            'bgp_options_extended': self._get_nested_value(options, ['bgp-options-extended', 0, 'data'], 'N/A'),
            'holdtime': self._get_nested_value(options, ['holdtime', 0, 'data'], 'N/A'),
            'preference': self._get_nested_value(options, ['preference', 0, 'data'], 'N/A'),
            'local_as': self._get_nested_value(options, ['local-as', 0, 'data'], 'N/A')
        }

    def _parse_neighbor_errors(self, peer):
        """Parse error information"""
        errors = []
        bgp_errors = peer.get('bgp-error', [])
        
        if not isinstance(bgp_errors, list):
            bgp_errors = [bgp_errors] if bgp_errors else []
        
        for error in bgp_errors:
            if not error:
                continue
            error_data = {
                'name': self._get_nested_value(error, ['name', 0, 'data'], 'N/A'),
                'send_count': self._get_nested_value(error, ['send-count', 0, 'data'], '0'),
                'receive_count': self._get_nested_value(error, ['receive-count', 0, 'data'], '0')
            }
            errors.append(error_data)
        
        return errors

    def _parse_neighbor_ribs(self, peer):
        """Parse RIB information untuk neighbor"""
        ribs = []
        bgp_ribs = peer.get('bgp-rib', [])
        
        if not isinstance(bgp_ribs, list):
            bgp_ribs = [bgp_ribs] if bgp_ribs else []
        
        for rib in bgp_ribs:
            if not rib:
                continue
            rib_data = {
                'name': self._get_nested_value(rib, ['name', 0, 'data'], 'N/A'),
                'rib_bit': self._get_nested_value(rib, ['rib-bit', 0, 'data'], 'N/A'),
                'bgp_rib_state': self._get_nested_value(rib, ['bgp-rib-state', 0, 'data'], 'N/A'),
                'send_state': self._get_nested_value(rib, ['send-state', 0, 'data'], 'N/A'),
                'active_prefix_count': self._get_nested_value(rib, ['active-prefix-count', 0, 'data'], '0'),
                'received_prefix_count': self._get_nested_value(rib, ['received-prefix-count', 0, 'data'], '0'),
                'accepted_prefix_count': self._get_nested_value(rib, ['accepted-prefix-count', 0, 'data'], '0'),
                'suppressed_prefix_count': self._get_nested_value(rib, ['suppressed-prefix-count', 0, 'data'], '0'),
                'advertised_prefix_count': self._get_nested_value(rib, ['advertised-prefix-count', 0, 'data'], '0')
            }
            ribs.append(rib_data)
        
        return ribs

    def _parse_bfd_info(self, peer):
        """Parse BFD information"""
        bfd_info = peer.get('bgp-bfd', [])
        if not isinstance(bfd_info, list) or not bfd_info:
            return {}
        
        bfd = bfd_info[0] if bfd_info else {}
        
        return {
            'bfd_configuration_state': self._get_nested_value(bfd, ['bfd-configuration-state', 0, 'data'], 'disabled'),
            'bfd_operational_state': self._get_nested_value(bfd, ['bfd-operational-state', 0, 'data'], 'down')
        }
    
    # STATIC ROUTE
    def get_static_routes(self):
        """Mendapatkan static routes information"""
        try:
            # XML request body untuk static routes
            xml_body = """<get-route-information>
        <brief/>
        <protocol>static</protocol>
    </get-route-information>"""
            
            response = requests.post(
                f"{self.base_url}/rpc?stop-on-error=1",
                auth=self.auth,
                headers=self.headers,
                data=xml_body,
                timeout=15,
                verify=self.verify
            )
            
            print(f"🔧 STATIC ROUTES STATUS: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    # Bersihkan response dari MIME boundary
                    cleaned_response = self._clean_mime_response(response.text)
                    data = json.loads(cleaned_response)
                    print("🔧 STATIC ROUTES JSON PARSED SUCCESSFULLY")
                    return True, self._parse_static_routes(data)
                except json.JSONDecodeError as e:
                    print(f"🔧 JSON DECODE ERROR: {e}")
                    return self._parse_static_routes_manual(response.text)
            else:
                error_msg = f"API Error: {response.status_code} - {response.text}"
                print(f"🔧 {error_msg}")
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Connection error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg

    def _parse_static_routes(self, data):
        """Parse static routes data"""
        try:
            route_info = data.get('route-information', [])
            if not isinstance(route_info, list):
                route_info = [route_info] if route_info else []
            
            result = {
                'route_tables': []
            }
            
            for info in route_info:
                route_tables = info.get('route-table', [])
                if not isinstance(route_tables, list):
                    route_tables = [route_tables] if route_tables else []
                
                for table in route_tables:
                    if not table:
                        continue
                        
                    route_table = {
                        'table_name': self._get_nested_value(table, ['table-name', 0, 'data'], 'N/A'),
                        'destination_count': self._get_nested_value(table, ['destination-count', 0, 'data'], '0'),
                        'total_route_count': self._get_nested_value(table, ['total-route-count', 0, 'data'], '0'),
                        'active_route_count': self._get_nested_value(table, ['active-route-count', 0, 'data'], '0'),
                        'holddown_route_count': self._get_nested_value(table, ['holddown-route-count', 0, 'data'], '0'),
                        'hidden_route_count': self._get_nested_value(table, ['hidden-route-count', 0, 'data'], '0'),
                        'routes': []
                    }
                    
                    # Parse routes
                    routes = table.get('rt', [])
                    if not isinstance(routes, list):
                        routes = [routes] if routes else []
                    
                    for route in routes:
                        if not route:
                            continue
                        
                        route_data = {
                            'destination': self._get_nested_value(route, ['rt-destination', 0, 'data'], 'N/A'),
                            'is_active': self._get_nested_value(route, ['rt-entry', 0, 'active-tag', 0, 'data']) == '*',
                            'protocol': self._get_nested_value(route, ['rt-entry', 0, 'protocol-name', 0, 'data'], 'N/A'),
                            'preference': self._get_nested_value(route, ['rt-entry', 0, 'preference', 0, 'data'], 'N/A'),
                            'age': self._get_nested_value(route, ['rt-entry', 0, 'age', 0, 'data'], 'N/A'),
                            'age_seconds': self._get_nested_value(route, ['rt-entry', 0, 'age', 0, 'attributes', 'junos:seconds'], '0'),
                            'next_hop': self._parse_next_hop(route)
                        }
                        
                        route_table['routes'].append(route_data)
                    
                    result['route_tables'].append(route_table)
            
            return result
            
        except Exception as e:
            return {'error': f"Parse error: {str(e)}"}

    def _parse_route_engine_info(self, data):
        """Parse route engine information"""
        try:
            extracted = self._extract_block(data, 'route-engine-information')
            if not extracted:
                return {}

            re_info = extracted.get('route-engine-information', [])
            if not isinstance(re_info, list):
                re_info = [re_info]
            if not re_info:
                return {}

            route_engines = re_info[0].get('route-engine', [])
            if not isinstance(route_engines, list):
                route_engines = [route_engines]
            if not route_engines:
                return {}

            engine = route_engines[0] or {}

            def _v(path, default='N/A'):
                return self._get_nested_value(engine, path, default)

            temperature_text = _v(['temperature', 0, 'data'], 'N/A')
            temperature_c = self._get_nested_value(engine, ['temperature', 0, 'attributes', 'junos:celsius'], None)

            cpu_user = _v(['cpu-user', 0, 'data'], '0')
            cpu_system = _v(['cpu-system', 0, 'data'], '0')
            cpu_idle = _v(['cpu-idle', 0, 'data'], '0')

            load_one = _v(['load-average-one', 0, 'data'], '0')
            load_five = _v(['load-average-five', 0, 'data'], '0')
            load_fifteen = _v(['load-average-fifteen', 0, 'data'], '0')

            memory_dram = _v(['memory-dram-size', 0, 'data'], '0')
            memory_installed = _v(['memory-installed-size', 0, 'data'], '0')

            return {
                'status': _v(['status', 0, 'data'], 'N/A'),
                'model': _v(['model', 0, 'data'], 'N/A'),
                'temperature': {
                    'text': temperature_text,
                    'celsius': temperature_c
                },
                'cpu': {
                    'user': cpu_user,
                    'system': cpu_system,
                    'idle': cpu_idle,
                    'background': _v(['cpu-background', 0, 'data'], '0'),
                    'interrupt': _v(['cpu-interrupt', 0, 'data'], '0'),
                    'load_average': {
                        'one': load_one,
                        'five': load_five,
                        'fifteen': load_fifteen
                    }
                },
                'memory': {
                    'dram': memory_dram,
                    'installed': memory_installed,
                    'buffer_utilization': _v(['memory-buffer-utilization', 0, 'data'], '0')
                },
                'uptime': {
                    'start_time': _v(['start-time', 0, 'data'], 'N/A'),
                    'seconds_since_boot': self._get_nested_value(engine, ['start-time', 0, 'attributes', 'junos:seconds'], '0'),
                    'up_time': _v(['up-time', 0, 'data'], 'N/A'),
                    'up_time_seconds': self._get_nested_value(engine, ['up-time', 0, 'attributes', 'junos:seconds'], '0'),
                    'last_reboot_reason': _v(['last-reboot-reason', 0, 'data'], 'N/A')
                }
            }
        except Exception as e:
            return {'error': f"Parse error: {str(e)}"}

    def _fallback_system_information(self):
        """Fallback ketika multi-RPC gagal: panggil API terpisah"""
        sys_error = None
        re_error = None

        def _fetch(endpoint: str, parser, label: str):
            try:
                resp = requests.get(
                    f"{self.base_url}{endpoint}",
                    auth=self.auth,
                    headers=self.headers,
                    timeout=10,
                    verify=self.verify
                )
                if resp.status_code == 200:
                    try:
                        return parser(resp.json()), None
                    except json.JSONDecodeError as e:
                        print(f"[JuniperAPI] Fallback {label} JSON decode error: {e}")
                        return None, f"JSON decode error: {str(e)}"
                print(f"[JuniperAPI] Fallback {label} HTTP status {resp.status_code}")
                return None, f"API Error: {resp.status_code}"
            except requests.exceptions.RequestException as e:
                print(f"[JuniperAPI] Fallback {label} connection error: {e}")
                return None, f"Connection error: {str(e)}"
            except Exception as e:
                print(f"[JuniperAPI] Fallback {label} unexpected error: {e}")
                return None, f"Unexpected error: {str(e)}"

        with ThreadPoolExecutor(max_workers=2) as executor:
            system_future = executor.submit(
                _fetch,
                "/rpc/get-system-information",
                self._parse_system_info,
                "system-info"
            )
            route_engine_future = executor.submit(
                _fetch,
                "/rpc/get-route-engine-information",
                self._parse_route_engine_info,
                "route-engine"
            )
            system_data, sys_error = system_future.result()
            route_engine_data, re_error = route_engine_future.result()

        result = {
            'system': system_data if system_data else ({'error': sys_error} if sys_error else None),
            'route_engine': route_engine_data if route_engine_data else ({'error': re_error} if re_error else None)
        }

        if system_data:
            return True, result
        return False, sys_error or 'Failed to retrieve system information'

    def _parse_next_hop(self, route):
        """Parse next hop information"""
        next_hop = {}
        
        rt_entry = route.get('rt-entry', [])
        if not isinstance(rt_entry, list) or not rt_entry:
            return next_hop
        
        entry = rt_entry[0]
        
        # Check for next-hop type (Discard, Reject, etc.)
        nh_type = self._get_nested_value(entry, ['nh-type', 0, 'data'])
        if nh_type and nh_type != 'N/A':
            next_hop['type'] = nh_type
            return next_hop
        
        # Check for regular next-hop (to/via)
        nh = entry.get('nh', [])
        if not isinstance(nh, list) or not nh:
            return next_hop
        
        nh_data = nh[0]
        next_hop['to'] = self._get_nested_value(nh_data, ['to', 0, 'data'], 'N/A')
        next_hop['via'] = self._get_nested_value(nh_data, ['via', 0, 'data'], 'N/A')
        next_hop['selected'] = self._get_nested_value(nh_data, ['selected-next-hop', 0, 'data']) is not None
        
        return next_hop

    def _parse_static_routes_manual(self, response_text):
        """Fallback parsing manual jika JSON parsing gagal"""
        try:
            # Coba ekstrak JSON secara manual
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                return True, self._parse_static_routes(data)
            else:
                return False, "Tidak dapat menemukan JSON dalam response"
        except Exception as e:
            return False, f"Manual parsing error: {str(e)}"

    # INTERFACES
    # Dalam class JuniperAPI, tambahkan method berikut:
    def get_interfaces(self):
        """Mendapatkan interfaces configuration"""
        try:
            # XML request body untuk interfaces
            xml_body = """<get-configuration>
        <configuration>
            <interfaces/>
        </configuration>
    </get-configuration>"""
            
            response = requests.post(
                f"{self.base_url}/rpc?stop-on-error=1",
                auth=self.auth,
                headers=self.headers,
                data=xml_body,
                timeout=15,
                verify=self.verify
            )
            
            print(f"🔧 INTERFACES STATUS: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    # Bersihkan response dari MIME boundary
                    cleaned_response = self._clean_mime_response(response.text)
                    data = json.loads(cleaned_response)
                    print("🔧 INTERFACES JSON PARSED SUCCESSFULLY")
                    return True, self._parse_interfaces(data)
                except json.JSONDecodeError as e:
                    print(f"🔧 JSON DECODE ERROR: {e}")
                    return self._parse_interfaces_manual(response.text)
            else:
                error_msg = f"API Error: {response.status_code} - {response.text}"
                print(f"🔧 {error_msg}")
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Connection error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"🔧 {error_msg}")
            return False, error_msg

    def _parse_interfaces(self, data):
        """Parse interfaces data"""
        try:
            config = data.get('configuration', {})
            interfaces_config = config.get('interfaces', {})
            
            result = {
                'interfaces': [],
                'last_updated': config.get('@', {}).get('junos:changed-localtime', 'N/A')
            }
            
            interfaces = interfaces_config.get('interface', [])
            if not isinstance(interfaces, list):
                interfaces = [interfaces] if interfaces else []
            
            for interface in interfaces:
                if not interface:
                    continue
                    
                interface_data = {
                    'name': interface.get('name', 'N/A'),
                    'description': interface.get('description', ''),
                    'disabled': 'disable' in interface,
                    'vlan_tagging': 'vlan-tagging' in interface,
                    'encapsulation': interface.get('encapsulation', ''),
                    'type': self._determine_interface_type(interface.get('name', '')),
                    'units': self._parse_interface_units(interface.get('unit', [])),
                    'options': self._parse_interface_options(interface)
                }
                
                result['interfaces'].append(interface_data)
            
            return result
            
        except Exception as e:
            return {'error': f"Parse error: {str(e)}"}

    def _determine_interface_type(self, interface_name):
        """Determine interface type based on name"""
        if interface_name.startswith('et-'):
            return 'Ethernet'
        elif interface_name.startswith('xe-'):
            return '10GigEthernet'
        elif interface_name.startswith('ae'):
            return 'AggregatedEthernet'
        elif interface_name.startswith('fxp'):
            return 'Management'
        elif interface_name.startswith('lo'):
            return 'Loopback'
        else:
            return 'Unknown'

    def _parse_interface_units(self, units):
        """Parse interface units"""
        if not isinstance(units, list):
            units = [units] if units else []
        
        result = []
        for unit in units:
            if not unit:
                continue
                
            unit_data = {
                'name': unit.get('name', 'N/A'),
                'description': unit.get('description', ''),
                'disabled': 'disable' in unit,
                'vlan_id': unit.get('vlan-id', ''),
                'family': self._parse_interface_family(unit.get('family', {}))
            }
            
            result.append(unit_data)
        
        return result

    def _parse_interface_family(self, family):
        """Parse interface family (inet, inet6)"""
        result = {
            'inet': [],
            'inet6': []
        }
        
        if family.get('inet'):
            inet_config = family['inet']
            addresses = inet_config.get('address', [])
            if not isinstance(addresses, list):
                addresses = [addresses] if addresses else []
            
            for addr in addresses:
                if addr and 'name' in addr:
                    result['inet'].append(addr['name'])
        
        if family.get('inet6'):
            inet6_config = family['inet6']
            addresses = inet6_config.get('address', [])
            if not isinstance(addresses, list):
                addresses = [addresses] if addresses else []
            
            for addr in addresses:
                if addr and 'name' in addr:
                    result['inet6'].append(addr['name'])
        
        return result

    def _parse_interface_options(self, interface):
        """Parse interface options"""
        options = {}
        
        # Gigether options (LAG member)
        if interface.get('gigether-options'):
            gigether = interface['gigether-options']
            if gigether.get('ieee-802.3ad'):
                lacp = gigether['ieee-802.3ad']
                options['bundle'] = lacp.get('bundle', 'N/A')
        
        # Aggregated ether options (LAG)
        if interface.get('aggregated-ether-options'):
            ae_options = interface['aggregated-ether-options']
            options['minimum_links'] = ae_options.get('minimum-links', '1')
            
            if ae_options.get('lacp'):
                lacp = ae_options['lacp']
                options['lacp_active'] = 'active' in lacp
                options['lacp_periodic'] = lacp.get('periodic', 'N/A')
        
        return options

    def _parse_interfaces_manual(self, response_text):
        """Fallback parsing manual jika JSON parsing gagal"""
        try:
            # Coba ekstrak JSON secara manual
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                data = json.loads(json_str)
                return True, self._parse_interfaces(data)
            else:
                return False, "Tidak dapat menemukan JSON dalam response"
        except Exception as e:
            return False, f"Manual parsing error: {str(e)}"




# HELPER GROUP

def _resolve_verify(use_ssl=False, rest_insecure=True):
    """Normalize use_ssl/rest_insecure values and derive verify_ssl."""
    if isinstance(use_ssl, str):
        use_ssl_flag = use_ssl.lower() in {"1", "true", "yes", "on"}
    else:
        use_ssl_flag = bool(use_ssl)

    if isinstance(rest_insecure, str):
        rest_insecure_flag = rest_insecure.lower() in {"1", "true", "yes", "on"}
    else:
        rest_insecure_flag = bool(rest_insecure)

    verify_ssl_flag = use_ssl_flag and not rest_insecure_flag
    return use_ssl_flag, verify_ssl_flag


def _resolve_gnmi_tls(gnmi_insecure=None, gnmi_use_ssl=None):
    """Derive gNMI TLS usage from various flag combinations."""
    if gnmi_use_ssl is not None:
        use_tls = bool(gnmi_use_ssl)
    elif gnmi_insecure is not None:
        use_tls = not bool(gnmi_insecure)
    else:
        use_tls = Config.GNMI_DEFAULT_USE_SSL
    return use_tls


def get_juniper_bgp_neighbor_detail(ip_address, port, username, password, neighbor_address, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk get BGP neighbor detail"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.get_bgp_neighbor_detail(neighbor_address)

def test_juniper_connection(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk test koneksi"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.test_connection()

def get_juniper_bgp_summary(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk get BGP summary"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.get_bgp_summary()

def get_juniper_system_info(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk get system info"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.get_system_information()

def get_juniper_policy_options(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk get policy options"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.get_policy_options()

# STATIC ROUTE
def get_juniper_static_routes(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk get static routes"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.get_static_routes()

# INTERFACES
def get_juniper_interfaces(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Fungsi helper untuk get interfaces configuration"""
    use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
    api = JuniperAPI(
        ip_address,
        port,
        username,
        password,
        use_ssl=use_ssl_flag,
        verify_ssl=verify_ssl_flag
    )
    return api.get_interfaces()


# GRPC Traffic Monitoring functions
def get_interfaces_for_monitoring(ip_address, port, username, password, use_ssl=False, rest_insecure=True):
    """Get list of interfaces available for monitoring"""
    try:
        use_ssl_flag, verify_ssl_flag = _resolve_verify(use_ssl, rest_insecure)
        rest_insecure_flag = not verify_ssl_flag if use_ssl_flag else True
        # First, try to get interfaces from configuration
        success, interfaces_data = get_juniper_interfaces(
            ip_address,
            port,
            username,
            password,
            use_ssl=use_ssl_flag,
            rest_insecure=rest_insecure_flag
        )
        
        if success and 'interfaces' in interfaces_data:
            monitoring_interfaces = []
            
            for interface in interfaces_data['interfaces']:
                # Add physical interfaces
                if interface['type'] in ['Ethernet', '10GigEthernet', 'AggregatedEthernet']:
                    monitoring_interfaces.append({
                        'name': interface['name'],
                        'description': interface['description'],
                        'type': interface['type'],
                        'disabled': interface['disabled']
                    })
                
                # Add logical interfaces (units)
                for unit in interface.get('units', []):
                    if unit['vlan_id']:
                        unit_name = f"{interface['name']}.{unit['vlan_id']}"
                        monitoring_interfaces.append({
                            'name': unit_name,
                            'description': unit['description'] or interface['description'],
                            'type': f"{interface['type']} Unit",
                            'vlan_id': unit['vlan_id']
                        })
            
            return True, monitoring_interfaces
    except Exception as e:
        return False, f"gNMI Error: {str(e)}"


def start_grpc_traffic_monitoring(
    ip_address,
    username,
    password,
    interface_filter=None,
    sample_interval_ms: int | None = None,
    gnmi_port: int | None = None,
    gnmi_insecure: bool | None = None,
    **kwargs,
):
    """Start gRPC streaming untuk monitoring traffic"""
    try:
        from src.juniper.gnmi_client import start_gnmi_monitoring

        gnmi_port = gnmi_port or Config.GNMI_DEFAULT_PORT
        gnmi_use_ssl = kwargs.pop('gnmi_use_ssl', None)
        kwargs.pop('gnmi_verify_ssl', None)
        use_tls = _resolve_gnmi_tls(gnmi_insecure=gnmi_insecure, gnmi_use_ssl=gnmi_use_ssl)
        # NOTE: gNMI client saat ini belum membedakan verify flag, hanya menentukan TLS on/off.
        device_id = f"{ip_address}:{gnmi_port}:{1 if use_tls else 0}"
        success, message = start_gnmi_monitoring(
            device_id,
            ip_address,
            gnmi_port,
            username,
            password,
            interface_filter,
            sample_interval_ms,
            use_tls,
        )
        return success, message
    except Exception as e:
        return False, f"GRPC Error: {str(e)}"


def stop_grpc_traffic_monitoring(
    ip_address,
    gnmi_port: int | None = None,
    gnmi_insecure: bool | None = None,
    **kwargs,
):
    """Hentikan sesi monitoring untuk device tertentu"""
    try:
        from src.juniper.gnmi_client import stop_gnmi_monitoring

        gnmi_port = gnmi_port or Config.GNMI_DEFAULT_PORT
        gnmi_use_ssl = kwargs.pop('gnmi_use_ssl', None)
        kwargs.pop('gnmi_verify_ssl', None)
        use_tls = _resolve_gnmi_tls(gnmi_insecure=gnmi_insecure, gnmi_use_ssl=gnmi_use_ssl)
        device_id = f"{ip_address}:{gnmi_port}:{1 if use_tls else 0}"
        return stop_gnmi_monitoring(device_id)
    except Exception as e:
        return False, f"gNMI Error: {str(e)}"


def get_live_traffic_data(
    ip_address,
    username,
    password,
    gnmi_port: int | None = None,
    gnmi_insecure: bool | None = None,
    **kwargs,
):
    """Get live traffic data from GRPC client"""
    try:
        from src.juniper.gnmi_client import get_gnmi_traffic_data

        gnmi_port = gnmi_port or Config.GNMI_DEFAULT_PORT
        gnmi_use_ssl = kwargs.pop('gnmi_use_ssl', None)
        use_tls = _resolve_gnmi_tls(gnmi_insecure=gnmi_insecure, gnmi_use_ssl=gnmi_use_ssl)
        device_id = f"{ip_address}:{gnmi_port}:{1 if use_tls else 0}"
        traffic_data = get_gnmi_traffic_data(device_id)

        return True, traffic_data
    except Exception as e:
        return False, f"Error getting traffic data: {str(e)}"
