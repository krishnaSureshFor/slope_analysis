import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from streamlit_js_eval import streamlit_js_eval
from folium.plugins import Draw
from dem_utils import detect_flat_areas_from_polygon
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
.main .block-container { padding: 0rem 0rem; }

.stButton>button {
    width: 100%;
    padding: 1rem;
    font-size: 1.1rem;
    border-radius: 12px;
}

.mobile-map { height: 85vh !important; }

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
st.markdown("<h2 style='text-align:center;'>🌍 Plain Area Detector</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;'>Auto DEM • Draw Polygon • GPS • Mobile UI</p>", unsafe_allow_html=True)

tabs = st.tabs(["📱 Draw", "📂 Upload KML"])


# =========================================================
# TAB 1 — DRAW + GPS
# =========================================================
with tabs[0]:

    st.markdown("### 📍 Get GPS Location")

    gps_button = st.button("Get My Location (GPS)", use_container_width=True)

    user_lat = None
    user_lon = None

    if gps_button:
        loc = streamlit_js_eval(
            js_expressions=[
                "navigator.geolocation.getCurrentPosition((pos) => pos.coords.latitude)",
                "navigator.geolocation.getCurrentPosition((pos) => pos.coords.longitude)"
            ],
            key="gps",
        )
        if loc and len(loc) == 2:
            user_lat, user_lon = loc
            st.success("GPS location fetched!")
        else:
            st.error("Enable GPS permission.")

    st.markdown("### 🗺 Draw Area on Map")

    # Map initialization
    if user_lat and user_lon:
        m = leafmap.Map(center=[user_lat, user_lon], zoom=17)
        m.add_circle_marker([user_lat, user_lon], radius=6,
                            color="#0066FF", fill=True, fill_opacity=1.0)
    else:
        m = leafmap.Map(center=[11.0, 78.0], zoom=7)

    m.add_basemap("HYBRID")

    # ============= DRAW TOOL (Fix) ==============
    draw = Draw(
        draw_options={
            "polyline": False,
            "rectangle": True,
            "polygon": True,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)
    # ============================================

    m.to_streamlit(height=600, css_class="mobile-map")

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        process_draw = st.button("⚙️ Process DEM")
    with c2:
        st.button("🧹 Clear Map")
    st.markdown("</div>", unsafe_allow_html=True)

    if process_draw:
        drawn = m.get_last_draw()  # leafmap method

        if drawn is None:
            st.error("Draw a polygon first!")
        else:
            gdf = gpd.GeoDataFrame.from_features([drawn])
            geom = gdf.geometry[0]

            with st.spinner("Downloading DEM & detecting flat areas…"):
                out_kml = detect_flat_areas_from_polygon(geom)

            st.success("Flat area generated!")

            with open(out_kml, "rb") as f:
                st.download_button("⬇️ Download flat_areas.kml", f,
                                   "flat_areas.kml", use_container_width=True)

            # Preview Map
            st.markdown("### Preview Result")

            rmap = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=15)
            rmap.add_basemap("HYBRID")
            rmap.add_gdf(gdf, layer_name="Boundary")

            flat = gpd.read_file(out_kml, driver="KML")
            rmap.add_gdf(flat, "Flat Areas")

            rmap.add_legend({"Boundary": "blue", "Flat Areas": "yellow"})
            rmap.to_streamlit(height=600)


# =========================================================
# TAB 2 — UPLOAD KML
# =========================================================
with tabs[1]:

    st.markdown("### Upload KML File")

    uploaded = st.file_uploader("Choose KML", type=["kml"])

    if uploaded:
        kml_path = "uploaded.kml"
        with open(kml_path, "wb") as f:
            f.write(uploaded.read())

        geodf = gpd.read_file(kml_path, driver="KML")
        geom = geodf.geometry[0]

        if st.button("⚙️ Process Uploaded KML", use_container_width=True):
            with st.spinner("Processing…"):
                out_kml = detect_flat_areas_from_polygon(geom)

            st.success("Done!")

            with open(out_kml, "rb") as f:
                st.download_button("⬇️ Download flat_areas.kml", f,
                                   "flat_areas.kml", use_container_width=True)

            st.markdown("### Result Preview")

            m2 = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=15)
            m2.add_basemap("HYBRID")
            m2.add_gdf(geodf, "Polygon")

            flat = gpd.read_file(out_kml, driver="KML")
            m2.add_gdf(flat, "Flat Areas")

            m2.add_legend({"Polygon": "blue", "Flat Areas": "yellow"})
            m2.to_streamlit(height=600)
