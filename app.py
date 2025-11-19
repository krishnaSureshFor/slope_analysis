import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from shapely.geometry import Polygon
from dem_utils import detect_flat_areas_from_polygon
from streamlit_js_eval import streamlit_js_eval
import simplekml

# ==========================
# PAGE CONFIG
# ==========================
st.set_page_config(
    page_title="Plain Detector",
    page_icon="🌍",
    layout="wide",
)

# ==========================
# MOBILE CSS
# ==========================
st.markdown("""
<style>

.main .block-container {
    padding: 0rem 0rem;
}

.stButton>button {
    width: 100%;
    padding: 1rem;
    font-size: 1.1rem;
    border-radius: 12px;
}

.mobile-map {
    height: 85vh !important;
}

.action-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: white;
    padding: 12px;
    border-top: 2px solid #ddd;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.15);
    z-index: 9999;
}

</style>
""", unsafe_allow_html=True)


# ==========================
# HEADER
# ==========================
st.markdown("<h2 style='text-align:center;'>🌍 Plain / Flat Area Detector</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;'>Auto DEM • Draw Polygon • Mobile Friendly • GPS Enabled</p>", unsafe_allow_html=True)

# ==========================
# TABS
# ==========================
tabs = st.tabs(["📱 Draw", "📂 Upload KML"])


# =========================================================
# TAB 1: DRAW POLYGON + GPS
# =========================================================
with tabs[0]:

    st.markdown("### 📍 Get GPS Location")

    gps_btn = st.button("Get My Location (GPS)", use_container_width=True)

    user_lat = None
    user_lon = None

    if gps_btn:
        location = streamlit_js_eval(
            js_expressions=[
                "navigator.geolocation.getCurrentPosition((pos) => pos.coords.latitude)",
                "navigator.geolocation.getCurrentPosition((pos) => pos.coords.longitude)"
            ],
            key="gps_key",
        )
        if location and len(location) == 2:
            user_lat, user_lon = location
            st.success("GPS location fetched successfully!")
        else:
            st.error("Please allow GPS permission in browser.")

    st.markdown("### 🗺 Draw Area on Map")

    # ----------------------------------------------------------
    # Map centered at GPS if available
    # ----------------------------------------------------------
    if user_lat and user_lon:
        m = leafmap.Map(center=[user_lat, user_lon], zoom=17)
        m.add_circle_marker(
            location=[user_lat, user_lon],
            radius=6,
            color="#0066FF",
            fill=True,
            fill_color="#0066FF",
            fill_opacity=1.0,
        )
    else:
        m = leafmap.Map(center=[11.0, 78.0], zoom=7)

    m.add_basemap("HYBRID")
    m.add_draw_control(rectangle=True, polygon=True, marker=False, circle=False, polyline=False)

    m.to_streamlit(height=600, css_class="mobile-map")

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        process_btn = st.button("⚙️ Process DEM")
    with col2:
        clear_btn = st.button("🧹 Clear Map")
    st.markdown("</div>", unsafe_allow_html=True)

    if process_btn:
        drawn_geom = m.user_roi

        if drawn_geom is None:
            st.error("Draw a polygon first!")
        else:
            gdf = gpd.GeoDataFrame.from_features([drawn_geom])
            geom = gdf.geometry[0]

            with st.spinner("Downloading DEM & analyzing…"):
                out_kml = detect_flat_areas_from_polygon(geom)

            st.success("Flat areas detected!")

            with open(out_kml, "rb") as f:
                st.download_button(
                    "⬇️ Download flat_areas.kml",
                    f,
                    "flat_areas.kml",
                    use_container_width=True
                )

            # Show result map
            st.markdown("### 📍 Result Preview")
            rmap = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=15)
            rmap.add_basemap("HYBRID")
            rmap.add_gdf(gdf, "Input Area")

            flat_gdf = gpd.read_file(out_kml, driver="KML")
            rmap.add_gdf(flat_gdf, "Flat Areas")

            legend = {"Input Polygon": "blue", "Flat Areas": "yellow"}
            rmap.add_legend(title="Legend", legend_dict=legend)

            rmap.to_streamlit(height=600)


# =========================================================
# TAB 2: UPLOAD KML
# =========================================================
with tabs[1]:

    st.markdown("### Upload your KML file")

    uploaded = st.file_uploader("Choose KML", type=["kml"])

    if uploaded:
        kml_file = "uploaded_boundary.kml"
        with open(kml_file, "wb") as f:
            f.write(uploaded.read())

        geodf = gpd.read_file(kml_file, driver="KML")
        geom = geodf.geometry[0]

        if st.button("⚙️ Process Uploaded KML", use_container_width=True):

            with st.spinner("Analyzing DEM…"):
                out_kml = detect_flat_areas_from_polygon(geom)

            st.success("Done!")

            with open(out_kml, "rb") as f:
                st.download_button(
                    "⬇️ Download flat_areas.kml",
                    f,
                    "flat_areas.kml",
                    use_container_width=True
                )

            st.markdown("### Preview Map")

            m2 = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=15)
            m2.add_basemap("HYBRID")
            m2.add_gdf(geodf, "Uploaded Polygon")

            flat_gdf = gpd.read_file(out_kml, driver="KML")
            m2.add_gdf(flat_gdf, "Flat Areas")

            legend = {"Uploaded Polygon": "blue", "Flat Areas": "yellow"}
            m2.add_legend(title="Legend", legend_dict=legend)

            m2.to_streamlit(height=600)
