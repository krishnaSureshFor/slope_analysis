import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from shapely.geometry import shape
from folium.plugins import Draw
from streamlit_js_eval import streamlit_js_eval
import simplekml
from dem_utils import process_slope_raster, clean_geometry


# PAGE SETTINGS
st.set_page_config(page_title="Slope Analysis", layout="wide")


# MOBILE CSS
st.markdown("""
<style>
.main .block-container { padding: 0; }
.mobile-map { height: 85vh !important; }
.stButton>button { width: 100%; padding: 1rem; font-size: 1.1rem; }
.action-bar {
  position: fixed; bottom:0; left:0; right:0;
  background:white; padding:10px;
  border-top:2px solid #ccc;
  box-shadow:0 -2px 8px rgba(0,0,0,0.2);
  z-index:9999;
}
</style>
""", unsafe_allow_html=True)


tabs = st.tabs(["📂 Upload Area", "📱 Draw & Extract"])


# =========================================================
# TAB 1 — UPLOAD KML → SHOW SLOPE MAP
# =========================================================
with tabs[0]:

    st.subheader("Upload KML to Generate Slope Map")

    up = st.file_uploader("Upload KML", type=["kml"])

    if up:
        open("uploaded.kml", "wb").write(up.read())

        gdf = gpd.read_file("uploaded.kml", driver="KML")
        geom = clean_geometry(gdf.geometry[0])

        st.info("Processing slope…")
        path = process_slope_raster(geom)

        if path:
            st.success("Slope map generated")

            m = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=13)
            m.add_basemap("HYBRID")
            m.add_image("slope.png", "slope.pgw", opacity=0.8, layer_name="Slope Map")
            m.add_gdf(gdf, layer_name="Boundary")

            m.to_streamlit(height=600)


# =========================================================
# TAB 2 — DRAW POLYGON → PROCESS → DRAW ON SLOPE → EXPORT KML
# =========================================================
with tabs[1]:

    st.subheader("Draw Area + Extract Slope + Export KML")

    st.markdown("### Step 1 — Draw an area on map")

    m = leafmap.Map(center=[11, 78], zoom=7)
    m.add_basemap("HYBRID")

    draw = Draw(
        draw_options={
            "polygon": True,
            "rectangle": True,
            "circle": False,
            "marker": False
        }
    )
    draw.add_to(m)

    m.to_streamlit(height=600, css_class="mobile-map")

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    btn = st.button("⚙️ Process Slope for Drawn Area")
    st.markdown("</div>", unsafe_allow_html=True)

    if btn:
        last = m.get_last_draw()

        if last is None:
            st.error("Please draw an area first.")
        else:
            geom = clean_geometry(shape(last["geometry"]))

            st.info("Generating slope map…")
            path = process_slope_raster(geom)

            if path:
                st.success("Slope generated. Now draw polygon on slope map.")

                m2 = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=13)
                m2.add_basemap("HYBRID")
                m2.add_image("slope.png", "slope.pgw", opacity=0.8, layer_name="Slope Map")

                draw2 = Draw(
                    draw_options={
                        "polygon": True,
                        "rectangle": True,
                        "circle": False,
                    }
                )
                draw2.add_to(m2)

                m2.to_streamlit(height=600)

                if st.button("Export Drawn Polygon as KML"):
                    last2 = m2.get_last_draw()
                    if last2:
                        g = shape(last2["geometry"])
                        kml = simplekml.Kml()
                        pol = kml.newpolygon()
                        pol.outerboundaryis = list(g.exterior.coords)
                        kml.save("output.kml")

                        st.success("KML exported.")
                        st.download_button("Download KML", open("output.kml", "rb"), "output.kml")
