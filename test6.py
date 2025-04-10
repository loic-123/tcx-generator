import streamlit as st
import numpy as np
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import io
from geopy.distance import geodesic
import requests
import random
import matplotlib.pyplot as plt

# ---------- Initialisation session ----------
if 'routes' not in st.session_state:
    st.session_state.routes = []
if 'start_point' not in st.session_state:
    st.session_state.start_point = None
if "map_display" not in st.session_state:
    st.session_state.map_display = None

# ---------- Helper functions ----------
def extract_speed_hr_time(coords, avg_speed_kmh, hr_avg):
    avg_speed_mps = avg_speed_kmh / 3.6
    base_distance = avg_speed_mps * 2  # tous les 2s
    times = []
    speeds = []
    hrs = []

    total_seconds = 0
    for i in range(len(coords)):
        factor = 1 + 0.1 * np.sin(i / 10) + np.random.normal(0, 0.05)
        speed = avg_speed_mps * factor
        hr = hr_avg + np.random.normal(0, 5)

        total_seconds += 2
        times.append(total_seconds)
        speeds.append(speed * 3.6)  # conversion en km/h
        hrs.append(hr)

    return times, speeds, hrs

def compute_total_distance_km(coords):
    distance_km = 0.0
    for i in range(1, len(coords)):
        pt1 = (coords[i-1][1], coords[i-1][0])  # (lat, lon)
        pt2 = (coords[i][1], coords[i][0])
        distance_km += geodesic(pt1, pt2).km
    return distance_km

def generate_route(start_lat, start_lon, distance_km, seed):
    api_key = "5b3ce3597851110001cf6248cae52fb8f7894709b0afefda9e71296f"
    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    body = {
        "coordinates": [[start_lon, start_lat]],
        "profile": "foot-walking",
        "format": "geojson",
        "options": {"round_trip": {"length": distance_km * 1000, "seed": seed}}
    }
    response = requests.post("https://api.openrouteservice.org/v2/directions/foot-walking/geojson", json=body, headers=headers)
    if response.status_code == 200:
        return response.json()['features'][0]['geometry']['coordinates']
    else:
        return []

def create_tcx(coords, avg_speed_kmh, hr_avg, activity_type):
    NSMAP = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    ET.register_namespace('', NSMAP)

    tcx = ET.Element('TrainingCenterDatabase', xmlns=NSMAP)
    activities = ET.SubElement(tcx, 'Activities')
    activity = ET.SubElement(activities, 'Activity', Sport=activity_type)
    ET.SubElement(activity, 'Id').text = datetime.now().isoformat()
    lap = ET.SubElement(activity, 'Lap', StartTime=datetime.now().isoformat())

    avg_speed_mps = avg_speed_kmh / 3.6
    start_time = datetime.now()
    total_seconds = 0
    total_distance = 0
    track = ET.SubElement(lap, 'Track')

    for i in range(1, len(coords)):
        lat1, lon1 = coords[i - 1][1], coords[i - 1][0]
        lat2, lon2 = coords[i][1], coords[i][0]
        dist_m = geodesic((lat1, lon1), (lat2, lon2)).m

        # Vitesse locale avec un bruit réaliste (±10 % max)
        local_speed = avg_speed_mps * (1 + np.random.normal(0, 0.05))
        time_step = max(3, int(dist_m / local_speed))  # au moins 1 point toutes les 3 s

        total_seconds += time_step
        total_distance += dist_m

        tp = ET.SubElement(track, 'Trackpoint')
        ET.SubElement(tp, 'Time').text = (start_time + timedelta(seconds=total_seconds)).isoformat()

        pos = ET.SubElement(tp, 'Position')
        ET.SubElement(pos, 'LatitudeDegrees').text = str(lat2)
        ET.SubElement(pos, 'LongitudeDegrees').text = str(lon2)
        ET.SubElement(tp, 'AltitudeMeters').text = str(200 + np.sin(i / 10))  # bruit sur altitude

        hr_element = ET.SubElement(tp, 'HeartRateBpm')
        value_element = ET.SubElement(hr_element, 'Value')
        value_element.text = str(int(hr_avg + np.random.normal(0, 5)))

    ET.SubElement(lap, 'TotalTimeSeconds').text = str(total_seconds)
    ET.SubElement(lap, 'DistanceMeters').text = str(int(total_distance))
    ET.SubElement(lap, 'Calories').text = str(int(np.random.randint(300, 800)))

    return ET.ElementTree(tcx)


# ---------- Interface Streamlit ----------
st.title("Générateur de fichiers TCX – 3 parcours aléatoires")

activity = st.selectbox("Type d'activité", ["Running", "Biking", "Walking"])
speed = st.slider("Vitesse moyenne (km/h)", 4.0, 40.0, 10.0)
distance = st.slider("Distance cible (km)", 1.0, 100.0, 5.0)
hr = st.slider("Fréquence cardiaque moyenne (bpm)", 90, 190, 140)

st.write("### Choisis un point de départ sur la carte")
default_location = [48.8566, 2.3522]
m = folium.Map(location=default_location, zoom_start=13)
folium.Marker(location=default_location, popup="Lieu par défaut (clique ailleurs pour changer)", icon=folium.Icon(color="gray")).add_to(m)
map_data = st_folium(m, height=400, width=700)

lat, lon = None, None
if map_data and map_data.get("last_clicked"):
    lat = map_data["last_clicked"]["lat"]
    lon = map_data["last_clicked"]["lng"]
    st.success(f"✅ Point de départ sélectionné : {lat:.5f}, {lon:.5f}")
else:
    st.info("🗺️ Clique sur la carte pour choisir un point de départ.")

if st.button("Générer les 3 parcours et le fichier TCX"):
    if lat is not None and lon is not None:
        colors = ["blue", "green", "red"]
        routes = []
        coords_for_export = []

        m = folium.Map(location=[lat, lon], zoom_start=13)
        folium.Marker([lat, lon], popup="Départ").add_to(m)

        for i in range(3):
            seed = random.randint(0, 10000)
            route = generate_route(lat, lon, distance, seed)

            if not route:
                st.error(f"Impossible de générer le parcours #{i+1}")
                routes.append(None)
                continue

            route_coords = [(lng, lat) for lng, lat in route]
            total_length_km = compute_total_distance_km(route_coords)

            if abs(total_length_km - distance) / distance <= 0.2:
                coords_for_export = route_coords
                routes.append(coords_for_export)
                folium.PolyLine(
                    [(lat, lng) for lng, lat in route],
                    color=colors[i], weight=5, opacity=0.7,
                    popup=f"Parcours {i + 1}"
                ).add_to(m)
            else:
                routes.append(None)

        st.session_state.map_display = m
        st.session_state.routes = routes
    else:
        st.warning("❗ Clique sur la carte pour définir un point de départ.")

# ---------- Affichage de la carte et export ----------
if st.session_state.map_display:
    st.write("### Carte des parcours générés")
    st_folium(st.session_state.map_display, height=500, width=700)

    tcx_files = []
    for i, coords in enumerate(st.session_state.routes):
        if coords:
            tcx_tree = create_tcx(coords, speed, hr, activity)
            tcx_io = io.BytesIO()
            tcx_tree.write(tcx_io, encoding='utf-8', xml_declaration=True)
            tcx_io.seek(0)
            tcx_files.append((i + 1, tcx_io))

    if tcx_files:
        st.write("### Téléchargement des fichiers TCX")
        for i, tcx_io in tcx_files:
            st.download_button(
                label=f"📥 Télécharger le TCX du parcours #{i}",
                data=tcx_io.getvalue(),
                file_name=f"parcours_{i}.tcx",
                mime="application/xml"
            )
    else:
        st.warning("Aucun parcours valide dans la tolérance de distance ±20%. Réessaie !")

    # ---------- Affichage graphique ----------
    if tcx_files:
        st.write("### 📈 Évolution de la vitesse et de la fréquence cardiaque")
        first_valid_coords = tcx_files[0][1]
        if st.session_state.routes[0]:
            times, speeds, hrs = extract_speed_hr_time(st.session_state.routes[0], speed, hr)
            fig, ax1 = plt.subplots(figsize=(10, 4))
            ax1.set_xlabel("Temps (s)")
            ax1.set_ylabel("Vitesse (km/h)", color='tab:blue')
            ax1.plot(times, speeds, color='tab:blue')
            ax1.tick_params(axis='y', labelcolor='tab:blue')

            ax2 = ax1.twinx()
            ax2.set_ylabel("Fréquence cardiaque (bpm)", color='tab:red')
            ax2.plot(times, hrs, color='tab:red')
            ax2.tick_params(axis='y', labelcolor='tab:red')

            fig.tight_layout()
            st.pyplot(fig)
            
    else:
        st.warning("Aucun parcours valide dans la tolérance de distance ±20%. Réessaie !")
