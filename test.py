import streamlit as st
import osmnx as ox
import networkx as nx
import gpxpy
import gpxpy.gpx
import random
import folium
from streamlit_folium import st_folium
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Fonction pour générer plusieurs boucles crédibles
def generate_loops(start_lat, start_lon, target_distance_km=5, place_radius=1500, num_routes=3):
    logging.info("Génération des boucles avec les paramètres : lat=%s, lon=%s, distance=%s km, rayon=%s m, nombre=%s",
                 start_lat, start_lon, target_distance_km, place_radius, num_routes)
    G = ox.graph_from_point((start_lat, start_lon), dist=place_radius, network_type='walk')
    start_node = ox.distance.nearest_nodes(G, X=start_lon, Y=start_lat)

    loops = []
    attempts = 0
    while len(loops) < num_routes and attempts < num_routes * 100:
        attempts += 1
        intermediate_node = random.choice(list(G.nodes))
        try:
            path_out = nx.shortest_path(G, start_node, intermediate_node, weight='length')
            path_back = nx.shortest_path(G, intermediate_node, start_node, weight='length')
            full_path = path_out + path_back[1:]
            length = ox.distance.route_length(G, full_path)
            if abs(length - target_distance_km * 1000) < 0.1 * target_distance_km * 1000:
                if full_path not in [p[0] for p in loops]:
                    loops.append((full_path, length))
                    logging.info("Boucle trouvée : longueur=%.2f m", length)
        except Exception as e:
            logging.warning("Erreur lors de la tentative de génération de boucle : %s", e)
            continue
    logging.info("Nombre total de boucles générées : %s", len(loops))
    return G, loops

# Fonction pour créer une carte Folium avec les boucles
def create_map(G, start_lat, start_lon, loops):
    logging.info("Création de la carte Folium avec %s boucle(s)", len(loops))
    m = folium.Map(location=[start_lat, start_lon], zoom_start=15)
    folium.Marker([start_lat, start_lon], popup="Départ", icon=folium.Icon(color="red")).add_to(m)

    colors = ["blue", "green", "purple", "orange", "darkred", "cadetblue"]
    routes_coords = []

    for i, (path, length) in enumerate(loops):
        coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in path]
        routes_coords.append((coords, length))
        folium.PolyLine(
            locations=coords,
            color=colors[i % len(colors)],
            weight=5,
            opacity=0.7,
            popup=f"Boucle {i+1} - {length/1000:.2f} km"
        ).add_to(m)
        logging.info("Boucle %s ajoutée à la carte : longueur=%.2f km", i + 1, length / 1000)

    return m, routes_coords

# Fonction pour exporter une boucle en GPX
def export_gpx(coords, index):
    logging.info("Exportation de la boucle %s en GPX", index + 1)
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    for lat, lon in coords:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon))

    return gpx.to_xml()

# STREAMLIT APP
st.set_page_config(page_title="Générateur de Boucles GPX", layout="wide")
st.title("🏃‍♂️ Générateur de Boucles GPX pour la course à pied")

# Sidebar
with st.sidebar:
    st.header("Paramètres")
    lat = st.number_input("Latitude de départ", value=48.8566, format="%.6f")
    lon = st.number_input("Longitude de départ", value=2.3522, format="%.6f")
    dist = st.slider("Distance cible (km)", 1, 20, 5)
    nb = st.slider("Nombre de boucles", 1, 5, 3)

    if st.button("🎲 Générer les boucles"):
        with st.spinner("Calcul des itinéraires..."):
            logging.info("Début de la génération des boucles")
            G, loops = generate_loops(lat, lon, dist, num_routes=nb)
            if loops:
                m, route_data = create_map(G, lat, lon, loops)
                st.success(f"{len(loops)} boucle(s) trouvée(s)")
                st_data = st_folium(m, height=600)

                st.header("📥 Export GPX")
                for i, (coords, length) in enumerate(route_data):
                    gpx_code = export_gpx(coords, i)
                    st.download_button(
                        label=f"Télécharger Boucle {i+1} - {length/1000:.2f} km",
                        data=gpx_code,
                        file_name=f"boucle_{i+1}.gpx",
                        mime="application/gpx+xml"
                    )
                logging.info("Export GPX terminé")
            else:
                logging.error("Aucune boucle trouvée")
                st.error("Aucune boucle trouvée. Essaie d’augmenter le rayon ou de réduire la distance.")
