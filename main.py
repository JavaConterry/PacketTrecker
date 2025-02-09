import subprocess
import requests
import re
import concurrent.futures
import folium
import psutil
import time
from collections import deque, defaultdict
from flask import Flask, send_file

MAX_ROUTES = 100
tracked_ips = set()
route_history = deque(maxlen=MAX_ROUTES)
ip_process_map = defaultdict(set)  # Track processes associated with each IP

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
    print(f"\nTracing route to {destination}...\n")
    is_windows = subprocess.run("ver", shell=True, capture_output=True).returncode == 0
    command = ["tracert", destination] if is_windows else ["traceroute", "-n", destination]
    result = subprocess.run(command, capture_output=True, text=True)
    
    lines = result.stdout.split("\n")
    route = []
    
    for line in lines:
        match_ip = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
        match_time = re.findall(r"(\d+\.?\d*)\s*ms", line)

        if match_ip:
            ip = match_ip.group(1)
            rtt = ", ".join(match_time) if match_time else "N/A"
            route.append((ip, rtt))
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        locations = list(executor.map(get_ip_location, [ip for ip, _ in route]))

    full_route = []
    for (ip, rtt), (lat, lon, location) in zip(route, locations):
        if lat and lon:
            full_route.append((ip, lat, lon, location, rtt))
            print(f"Hop: {ip}, RTT: {rtt} ms, Location: {location}")

    return full_route

def update_map():
    m = folium.Map(location=[0, 0], zoom_start=2)
    for route in route_history:
        coords = [(lat, lon) for _, lat, lon, _, _ in route]
        folium.PolyLine(coords, color="blue", weight=0.5, opacity=1).add_to(m)
        
        for ip, lat, lon, location, rtt in route:
            process_names = ", ".join(ip_process_map.get(ip, []))
            
            popup_content = f"IP: {ip}\nRTT: {rtt} ms\nLocation: {location}"
            if process_names:
                popup_content += f"\nProcesses: {process_names}"
                
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color='red',
                fill=True,
                fill_color='red',
                fill_opacity=0.7,
                popup=popup_content
            ).add_to(m)

    m.save("live_traceroute.html")
    print("Map updated.")

def get_process_name(pid):
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "Unknown"

def monitor_connections():
    print("Monitoring network connections... Press Ctrl+C to stop.")
    try:
        while True:
            connections = psutil.net_connections(kind="inet")
            for conn in connections:
                if conn.status == psutil.CONN_ESTABLISHED and conn.raddr:
                    dest_ip = conn.raddr.ip
                    process_name = get_process_name(conn.pid) if conn.pid else "Unknown"

                    if dest_ip not in tracked_ips:
                        tracked_ips.add(dest_ip)
                        print(f"\n[+] New Connection: {process_name} → {dest_ip}")

                        route = trace_packet(dest_ip)
                        if route:
                            route_history.append(route)
                            
                            # Update ip_process_map to track the processes visiting each IP
                            for ip, _, _, _, _ in route:
                                ip_process_map[ip].add(process_name)
                            
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
