import pynetbox
import urllib3
import ipaddress
import hashlib
from functools import lru_cache
from pydantic import BaseModel, Field, field_validator
from itertools import chain
from pprint import pprint
from typing import Any, Dict, List, Tuple
from flask import Flask, jsonify, request, send_from_directory, render_template

app = Flask(__name__)

class Device(BaseModel):
    """Basemodel to extract only the required information"""
    id: int
    name: str
    role: str
    parent: Optional[str] = Field(alias="tenant",default=None)

    @field_validator('role', mode='before')
    @classmethod
    def extract_role_name(cls, v):
        """extract the role name form the nested role object"""
        if isinstance(v, dict):
            return v.get('name')
        return v
    
    @field_validator("parent", mode="before")
    @classmethod
    def extract_tenant_name(cls, v):
        """extract the tenant name form the nested tenant object"""
        if isinstance(v, dict):
            return v.get("name")
        return v

class Interface(BaseModel):
    """Basemodel to extract only the required information"""
    id: int
    name: str
    ip_address: str
    device: str
    vrf: Optional[str] = Field(default=None)
    tenant: Optional[str] = Field(default=None)

    @field_validator('device', mode='before')
    @classmethod
    def extract_device_name(cls, v):
        """extract the device name from the nested device object"""
        if isinstance(v, dict):
            return v.get('name')
        return v

def string_to_color(string):
    # Hash the string using MD5 for simplicity, you can use other hashing algorithms too
    hash_value = hashlib.md5(string.encode()).hexdigest()
    # Take the first 6 characters of the hash value
    hex_color = hash_value[:6]
    # Convert hexadecimal to RGB values
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    # Format the RGB values into a color code
    color_code = "#{:02X}{:02X}{:02X}".format(r, g, b)
    return color_code

def init_netbox(url: str, token: str) -> pynetbox.core.api.Api:
    """Initialize the pynetbox module"""
    nb = pynetbox.api(url, token)
    nb.http_session.verify = False  # Disable certificate verification
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # Disable certificate warnings
    return nb

def get_devices(nb, tenant_id) -> Dict[Dict,Any]:
    """Gets the devices from the NetBox REST API and returns a dictionary of devices with name as key"""
    try:
        devices = nb.dcim.devices.filter(tenant_id=tenant_id, interface_count__gt=0)
        return {device.name:Device(**dict(device)).model_dump(exclude_none=True) for device in devices} if devices else {}
    except Exception as e:
        print(f"Error fetching devices: {e}")
        return {}

def chunks(lst: List[Any], n: int):
    """Yield successive n-sized chunks from the given list"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def get_interfaces(nb, device_id_list: List[int]) -> List[Dict[str, Any]]:
    """Gets the interfaces from the NetBox REST API for a list of device that is split in chunks to
    avoid to long URL in the Request to NetBox. Then it gets the matches the interfaces with the 
    IP addresses and creates a list of interfaces dictionaries with id, name, device, ip address 
    and optional vrf and tenant."""
    try:
        interfaces = list(chain.from_iterable(nb.dcim.interfaces.filter(device_id=chunk) for chunk in chunks(device_id_list, 20)))
        interface_dict = {interface.id: interface for interface in interfaces}

        ip_addresses = list(chain.from_iterable(nb.ipam.ip_addresses.filter(device_id=chunk) for chunk in chunks(device_id_list, 20)))
        clean_interfaces = []

        for ip_address in ip_addresses:
            interface = interface_dict.get(ip_address.assigned_object_id)
            if interface:
                interface_data = dict(interface)
                interface_data['ip_address'] = ip_address.address
                if vrf := ip_address.vrf:
                    interface_data['vrf'] = vrf.name
                if tenant := ip_address.tenant:
                    interface_data['tenant'] = tenant.name
                clean_interface = Interface(**interface_data).model_dump(exclude_none=True)
                clean_interfaces.append(clean_interface)
        return clean_interfaces

    except Exception as e:
        print(f"Error fetching interfaces: {e}")
        return []
 
def convert_ip2subnet(ip_address: str) -> str:
    """Converts a IP address with prefixlen to network address with prefixlen"""
    return str(ipaddress.ip_network(ip_address, strict=False))

def create_edges_and_nodes(device_dict: Dict[Dict, Any], interface_list: List[Dict[str, Any]]) -> Tuple[List, List]:
    """Takes a list of device and a list of interfaces with IP addresses and converts it into nodes and edges"""
    edges = []
    nodes = []
    subnets = set()
    devices = set()
    vrfs = set()
    tenants = set()

    for item in interface_list:
        tenant = item.get("tenant", None)
        vrf = item.get("vrf", None)
        subnet = convert_ip2subnet(item["ip_address"])
        if vrf:
            parent = vrf
            subnet_name = f"{subnet} {vrf}"
        elif tenant:
            parent = tenant
            subnet_name = f"{subnet} {tenant}"
        else:
            parent = None
            subnet_name = subnet
        if subnet_name not in subnets:
            data = {
                "id": subnet_name,
                "label": subnet,
                "role": "subnet"
            }
            if parent:
                data["parent"] = parent
            nodes.append({"data": data})
            subnets.add(subnet_name)

        device_name = item["device"]
        device = device_dict[device_name]
        if device_name not in devices:
            data = {
                "id": device_name,
                "role": device["role"]
            }
            if parent := device.get("parent", None):
                data["parent"] = parent
            nodes.append({"data": data})
            devices.add(device_name)

        if vrf and vrf not in vrfs:
            color = string_to_color(vrf)
            data = {
                "id": vrf,
                "role": "vrf",
                "borderColor": color
            }
            if tenant:
                data["parent"] = tenant
            nodes.append({"data": data})
            vrfs.add(vrf)

        if tenant and tenant not in tenants:
            color = string_to_color(tenant)
            data = {
                "id": tenant,
                "role": "tenant",
                "borderColor": color
            }
            nodes.append({"data": data})
            tenants.add(tenant)

        edges.append({"data": {
            "id": f'{device_name} - {subnet_name}',
            "label": f'{item["name"]} - {item["ip_address"]}',
            "source": device_name,
            "target": subnet_name
            }})

    return nodes, edges

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/nodes_and_edges', methods=['GET'])
@lru_cache(maxsize=32)
def get_nodes_and_edges():
    netbox_url = "https://demo.netbox.dev/" # NetBox Demo Instance
    netbox_token = "06dd3e7534485df1d3e91f80c97f05ca49e77f54" # Create your own key!
    tenant_id = 5 #  Dunder-Mifflin, Inc.

    nb = init_netbox(netbox_url, netbox_token)
    devices = get_devices(nb, tenant_id)
    if not devices:
        print("No devices found.")
        return jsonify({})
    device_id_list = [device["id"] for device in devices]
    interfaces = get_interfaces(nb, device_id_list)
    if not interfaces:
        print("No interfaces found.")
        return jsonify({})
    nodes, edges = create_edges_and_nodes(devices, interfaces)
    return jsonify({'nodes': nodes, 'edges': edges})


if __name__ == '__main__':
    app.run(debug=True)
