import subprocess
import requests
import re
import concurrent.futures
import folium
import psutil
import time
from collections import deque
from flask import Flask, send_file

MAX_ROUTES = 100
tracked_ips = set()
route_history = deque(maxlen=MAX_ROUTES)

app = Flask(__name__)

def get_ip_location(ip):
    """Fetch geolocation for an IP address using ip-api.com."""
    if ip in ["*", "Request timed out"]:
        return None, None, None
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=lat,lon,city,country")
        data = response.json()
        return data.get("lat"), data.get("lon"), f"{data.get('city', 'Unknown')}, {data.get('country', 'Unknown')}"
    except:
        return None, None, None

def trace_packet(destination):
    print(f"Tracing route to {destination}...\n")
    command = ["tracert", destination] if subprocess.run("ver", shell=True, capture_output=True).returncode == 0 else ["traceroute", "-n", destination]
    result = subprocess.run(command, capture_output=True, text=True)
    
    lines = result.stdout.split("\n")
    ips = [match.group(1) for line in lines if (match := re.search(r"(\d+\.\d+\.\d+\.\d+)", line))]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        locations = list(executor.map(get_ip_location, ips))

    return [(ip, lat, lon, location) for (ip, (lat, lon, location)) in zip(ips, locations) if lat and lon]

def update_map():
    m = folium.Map(location=[0, 0], zoom_start=2)
    for route in route_history:
        coords = [(lat, lon) for _, lat, lon, _ in route]
        folium.PolyLine(coords, color="blue", weight=0.2, opacity=0.7).add_to(m)  # Adjusted thickness
        
        for ip, lat, lon, location in route:
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color='red',
                fill=True,
                fill_color='red',
                fill_opacity=0.7,
                popup=f"IP: {ip}\nLocation: {location}"
            ).add_to(m)
            
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

@app.route('/')
def serve_map():
    return send_file("live_traceroute.html")

if __name__ == "__main__":
    from threading import Thread
    monitor_thread = Thread(target=monitor_connections, daemon=True)
    monitor_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
