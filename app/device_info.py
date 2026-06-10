# device_agent.py
import uuid
import psutil
import platform
import requests

# IP & Network
addrs = psutil.net_if_addrs()
for iface, snics in addrs.items():
    for snic in snics:
        if snic.family.name == 'AF_INET':  # IPv4
            ip = snic.address
            subnet = snic.netmask
            gateway = snic.broadcast

            # MAC
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
                            for ele in range(0,8*6,8)][::-1])

            # Device info
            device_name = platform.node()   # hostname
            os_name = platform.system()     # Windows / Linux / Mac
            # interface name
            interface_name = iface

            # Send to Flask
            data = {
                "user_id": 1,  # replace with actual logged-in user id
                "ip": ip,
                "subnet": subnet,
                "gateway": gateway,
                "mac": mac,
                "device_name": device_name,
                "interface_name": interface_name,
                "platform": os_name,
            }

            requests.post("http://127.0.0.1:7000/api/device_info", json=data)
