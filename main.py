import subprocess
import requests
import re
import concurrent.futures
import folium
import psutil
import time
from collections import deque

MAX_ROUTES = 100
tracked_ips = set()
route_history = deque(maxlen=MAX_ROUTES)

def get_ip_location(ip):
    """Fetch geolocation for an IP address using ip-api.com."""
    if ip in ["*", "Request timed out"]:
        return None, None

    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=lat,lon")
        data = response.json()
        lat, lon = data.get("lat"), data.get("lon")
        return lat, lon
    except:
        return None, None

def trace_packet(destination):
    print(f"Tracing route to {destination}...\n")

    command = ["tracert", destination] if subprocess.run("ver", shell=True, capture_output=True).returncode == 0 else ["traceroute", "-n", destination]
    result = subprocess.run(command, capture_output=True, text=True)
    
    lines = result.stdout.split("\n")
    ips = [match.group(1) for line in lines if (match := re.search(r"(\d+\.\d+\.\d+\.\d+)", line))]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        locations = list(executor.map(get_ip_location, ips))

    return [(ip, lat, lon) for (ip, (lat, lon)) in zip(ips, locations) if lat and lon]

def update_map():
    m = folium.Map(location=[0, 0], zoom_start=2)

    for route in route_history:
        coords = [(lat, lon) for _, lat, lon in route]
        folium.PolyLine(coords, color="blue", weight=2.5, opacity=1).add_to(m)

    m.save("live_traceroute.html")
    print("Map updated.")

def monitor_connections():
    print("Monitoring network connections... Press Ctrl+C to stop.")
    try:
        while True:
            connections = psutil.net_connections(kind="inet")
            for conn in connections:
                if conn.status == psutil.CONN_ESTABLISHED and conn.raddr:
                    dest_ip = conn.raddr.ip
                    if dest_ip not in tracked_ips:
                        tracked_ips.add(dest_ip)
                        route = trace_packet(dest_ip)
                        if route:
                            route_history.append(route)
                            update_map()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopped monitoring.")

monitor_connections()
