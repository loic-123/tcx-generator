import streamlit as st
import numpy as np
import gpxpy.gpx
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import io
from geopy.distance import geodesic
import requests
import random

if 'routes' not in st.session_state:
    st.session_state.routes = []
if 'start_point' not in st.session_state:
    st.session_state.start_point = None
    


# ---------- Helper functions ----------



def compute_total_distance_km(coords):
    distance_km = 0.0
    for i in range(1, len(coords)):
        pt1 = (coords[i-1][1], coords[i-1][0])  # (lat, lon)
        pt2 = (coords[i][1], coords[i][0])
        distance_km += geodesic(pt1, pt2).km
    return distance_km


def generate_route(start_lat, start_lon, distance_km, seed):
    """
    Utilise l'API OpenRouteService pour générer une boucle avec une graine spécifique.
    """
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
    base_distance = avg_speed_mps * 2  # distance moyenne tous les 2s

    start_time = datetime.now()
    total_distance = 0
    total_seconds = 0
    track = ET.SubElement(lap, 'Track')

    for i, (lon, lat) in enumerate(coords):
        tp = ET.SubElement(track, 'Trackpoint')

        # Ajoute un bruit sinusoidal + bruit aléatoire pour la vitesse (et donc la distance)
        factor = 1 + 0.1 * np.sin(i / 10) + np.random.normal(0, 0.05)
        distance_m = base_distance * factor
        total_distance += distance_m
        total_seconds += 2

        ET.SubElement(tp, 'Time').text = (start_time + timedelta(seconds=total_seconds)).isoformat()
        pos = ET.SubElement(tp, 'Position')
        ET.SubElement(pos, 'LatitudeDegrees').text = str(lat)
        ET.SubElement(pos, 'LongitudeDegrees').text = str(lon)
        ET.SubElement(tp, 'AltitudeMeters').text = str(200 + np.sin(i / 10))
        ET.SubElement(tp, 'HeartRateBpm').append(ET.Element('Value')).text = str(int(hr_avg + np.random.normal(0, 5)))

    ET.SubElement(lap, 'TotalTimeSeconds').text = str(total_seconds)
    ET.SubElement(lap, 'DistanceMeters').text = str(int(total_distance))
    ET.SubElement(lap, 'Calories').text = str(int(np.random.randint(300, 800)))

    return ET.ElementTree(tcx)

# ---------- Streamlit Interface ----------

st.title("Générateur de fichiers TCX – 3 parcours aléatoires")

activity = st.selectbox("Type d'activité", ["Running", "Biking", "Walking"])
speed = st.slider("Vitesse moyenne (km/h)", 4.0, 40.0, 10.0)
distance = st.slider("Distance cible (km)", 1.0, 100.0, 5.0)
hr = st.slider("Fréquence cardiaque moyenne (bpm)", 90, 190, 140)

st.write("### Choisis un point de départ sur la carte")
st.write("### Clique sur la carte pour définir ton point de départ")
default_location = [48.8566, 2.3522]
m = folium.Map(location=default_location, zoom_start=13)

# On ajoute une instruction visuelle sur la carte
folium.Marker(location=default_location, popup="Lieu par défaut (clique ailleurs pour changer)", icon=folium.Icon(color="gray")).add_to(m)

# Rendu interactif avec clic pour capturer une position
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
        lat = map_data['last_clicked']['lat']
        lon = map_data['last_clicked']['lng']

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
                continue

            # Filtrer les routes hors tolérance de distance (±20%)
            route_coords = [(lng, lat) for lng, lat in route]
            total_length_km = compute_total_distance_km(route_coords)


            if abs(total_length_km - distance) / distance <= 0.2:
                coords_for_export = route_coords
                routes.append(coords_for_export)
            else:
                routes.append(None)  # pour garder l'ordre


            folium.PolyLine([(lat, lng) for lng, lat in route], color=colors[i], weight=5, opacity=0.7,
                            popup=f"Parcours {i + 1}").add_to(m)

        st_folium(m, height=500, width=700)

        if coords_for_export:
            tcx_files = []

            for i, coords in enumerate(routes):
                if coords:  # si la route a été stockée
                    tcx_tree = create_tcx(coords, speed, hr, activity)
                    tcx_io = io.BytesIO()
                    tcx_tree.write(tcx_io, encoding='utf-8', xml_declaration=True)
                    tcx_io.seek(0)
                    tcx_files.append(tcx_io)

            if tcx_files:
                st.write("### Téléchargement des fichiers TCX")
                for i, tcx_io in enumerate(tcx_files):
                    st.download_button(
                        label=f"📥 Télécharger le TCX du parcours #{i + 1}",
                        data=tcx_io.getvalue(),
                        file_name=f"parcours_{i + 1}.tcx",
                        mime="application/xml"
                    )
            else:
                st.warning("Aucun parcours valide dans la tolérance de distance ±20%. Réessaie !")
    else:
        st.warning("❗ Clique sur la carte pour définir un point de départ.")
