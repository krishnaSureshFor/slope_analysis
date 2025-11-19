import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from folium.plugins import Draw
from streamlit_js_eval import streamlit_js_eval
from dem_utils import detect_flat_areas_from_polygon, clean_geometry
from shapely.geometry import shape
import json


st.set_page_config(page_title="Plain Detector", layout="wide")

# ======================================
# Mobile style
# ======================================
st.markdown("""
<style>
.main .block-container { padding:0; }
.mobile-map { height:85vh !important; }
.stButton>button { width:100%; padding:1rem; font-size:1.1rem; }
.action-bar {
    position: fixed; bottom:0; left:0; right:0;
    background:white; padding:10px;
    border-top:2px solid #ccc;
    box-shadow:0 -2px 8px rgba(0,0,0,0.2);
    z-index:9999;
}
</style>
""", unsafe_allow_html=True)

tabs = st.tabs(["📱 Draw", "📂 Upload KML"])


# ============================================================
# TAB 1 – Draw polygon
# ============================================================
with tabs[0]:

    gps_btn = st.button("📍 Get GPS Location")

    user_lat = None
    user_lon = None

    if gps_btn:
        loc = streamlit_js_eval(
            js_expressions=[
                "navigator.geolocation.getCurrentPosition((p)=>p.coords.latitude)",
                "navigator.geolocation.getCurrentPosition((p)=>p.coords.longitude)"
            ]
        )
        if loc and len(loc) == 2:
            user_lat, user_lon = loc
            st.success("GPS fetched!")

    if user_lat:
        m = leafmap.Map(center=[user_lat, user_lon], zoom=17)
        m.add_circle_marker([user_lat, user_lon], radius=6,
                            color="#0066FF", fill=True, fill_opacity=1.0)
    else:
        m = leafmap.Map(center=[11, 78], zoom=7)

    m.add_basemap("HYBRID")

    draw = Draw(
        draw_options={
            "polygon": True,
            "rectangle": True,
            "polyline": False,
            "circle": False,
            "marker": False,
            "circlemarker": False
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)

    m.to_streamlit(height=600, css_class="mobile-map")

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    process = st.button("⚙️ Process DEM")
    st.markdown("</div>", unsafe_allow_html=True)

    if process:
        last = m.get_last_draw()

        if last is None:
            st.error("Draw an area first!")
        else:
            geom = shape(last["geometry"])
            geom = clean_geometry(geom)

            out = detect_flat_areas_from_polygon(geom)

            if out is None:
                st.error("DEM request failed")
            else:
                st.success("Done!")

                with open(out, "rb") as f:
                    st.download_button("⬇️ Download KML", f, "flat_areas.kml")

                # Preview
                rmap = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=15)
                rmap.add_basemap("HYBRID")
                rmap.add_gdf(gpd.GeoDataFrame(geometry=[geom]), "Boundary")
                rmap.add_gdf(gpd.read_file(out, driver="KML"), "Flat")
                rmap.to_streamlit(height=600)


# ============================================================
# TAB 2 – Upload KML
# ============================================================
with tabs[1]:

    up = st.file_uploader("Upload KML", type=["kml"])

    if up:
        open("uploaded.kml", "wb").write(up.read())
        gdf = gpd.read_file("uploaded.kml", driver="KML")
        geom = clean_geometry(gdf.geometry[0])

        if st.button("Process Uploaded KML"):
            out = detect_flat_areas_from_polygon(geom)
            if out:
                with open(out, "rb") as f:
                    st.download_button("Download Result", f, "flat_areas.kml")
