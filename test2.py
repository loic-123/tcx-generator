import streamlit as st
import numpy as np
import gpxpy.gpx
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import io
import requests

# ---------- Helper functions ----------

def generate_route(start_lat, start_lon, distance_km):
    """
    Utilise l'API OpenRouteService pour générer une boucle.
    """
    api_key = "5b3ce3597851110001cf6248cae52fb8f7894709b0afefda9e71296f"
    if not api_key:
        st.error("Clé API OpenRouteService manquante. Ajoute-la dans `.streamlit/secrets.toml`.")
        return []

    headers = {
        'Authorization': api_key,
        'Content-Type': 'application/json'
    }
    body = {
        "coordinates": [[start_lon, start_lat]],
        "profile": "foot-walking",
        "format": "geojson",
        "options": {"round_trip": {"length": distance_km * 1000, "seed": 1}}
    }
    response = requests.post("https://api.openrouteservice.org/v2/directions/foot-walking/geojson", json=body, headers=headers)
    if response.status_code == 200:
        return response.json()['features'][0]['geometry']['coordinates']
    else:
        st.error("Erreur de récupération de l'itinéraire : " + response.text)
        return []

def add_noise(data, std_dev):
    return data + np.random.normal(0, std_dev, size=data.shape)

def create_tcx(coords, speed_kmh, hr_avg, activity_type):
    # Create XML structure
    NSMAP = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    ET.register_namespace('', NSMAP)

    tcx = ET.Element('TrainingCenterDatabase', xmlns=NSMAP)
    activities = ET.SubElement(tcx, 'Activities')
    activity = ET.SubElement(activities, 'Activity', Sport=activity_type)
    ET.SubElement(activity, 'Id').text = datetime.now().isoformat()
    lap = ET.SubElement(activity, 'Lap', StartTime=datetime.now().isoformat())
    ET.SubElement(lap, 'TotalTimeSeconds').text = str(len(coords) * 5)
    ET.SubElement(lap, 'DistanceMeters').text = str(len(coords) * (speed_kmh / 3.6) * 5)
    ET.SubElement(lap, 'Calories').text = str(int(np.random.randint(300, 800)))
    track = ET.SubElement(lap, 'Track')

    start_time = datetime.now()

    for i, (lon, lat) in enumerate(coords):
        tp = ET.SubElement(track, 'Trackpoint')
        ET.SubElement(tp, 'Time').text = (start_time + timedelta(seconds=i * 5)).isoformat()
        pos = ET.SubElement(tp, 'Position')
        ET.SubElement(pos, 'LatitudeDegrees').text = str(lat)
        ET.SubElement(pos, 'LongitudeDegrees').text = str(lon)
        ET.SubElement(tp, 'AltitudeMeters').text = str(200 + np.sin(i / 10))
        ET.SubElement(tp, 'HeartRateBpm').append(ET.Element('Value')).text = str(int(hr_avg + np.random.normal(0, 5)))

    return ET.ElementTree(tcx)

# ---------- Streamlit Interface ----------
st.title("Générateur de fichier TCX pour activité sportive")

activity = st.selectbox("Type d'activité", ["Running", "Biking", "Walking"])
speed = st.slider("Vitesse moyenne (km/h)", 4.0, 40.0, 10.0)
distance = st.slider("Distance de la boucle (km)", 1.0, 100.0, 5.0)
hr = st.slider("Fréquence cardiaque moyenne (bpm)", 90, 190, 140)

st.write("### Choisis un point de départ sur la carte")
default_location = [48.8566, 2.3522]  # Paris par défaut
m = folium.Map(location=default_location, zoom_start=13)
marker = folium.Marker(location=default_location, draggable=True)
marker.add_to(m)
map_data = st_folium(m, height=400, width=700)

if st.button("Générer le fichier TCX"):
    if map_data and map_data['last_clicked']:
        lat = map_data['last_clicked']['lat']
        lon = map_data['last_clicked']['lng']

        route = generate_route(lat, lon, distance)
        if route:
            coords = [(lng, lat) for lng, lat in route]

            # Afficher la route sur la carte
            m = folium.Map(location=[lat, lon], zoom_start=13)
            folium.Marker([lat, lon], popup="Départ").add_to(m)
            folium.PolyLine([(lat, lng) for lng, lat in route], color="blue").add_to(m)
            st_folium(m, height=400, width=700)

            tcx_tree = create_tcx(coords, speed, hr, activity)
            tcx_io = io.BytesIO()
            tcx_tree.write(tcx_io, encoding='utf-8', xml_declaration=True)
            st.download_button("📥 Télécharger le fichier TCX", data=tcx_io.getvalue(), file_name="activité.tcx", mime="application/xml")
    else:
        st.warning("Clique sur la carte pour définir un point de départ.")
