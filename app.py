# app.py
import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from shapely.geometry import shape
from folium.plugins import Draw
from streamlit_js_eval import streamlit_js_eval
import simplekml
from dem_utils import process_slope_raster, clean_geometry

st.set_page_config(page_title="Slope Analysis", layout="wide")

# Mobile friendly CSS
st.markdown("""
<style>
.main .block-container { padding: 0; }
.mobile-map { height: 85vh !important; }
.stButton>button { width: 100%; padding: 1rem; font-size: 1.05rem; }
.action-bar { position: fixed; bottom:0; left:0; right:0; background:white; padding:10px; border-top:2px solid #ccc; z-index:9999; }
</style>
""", unsafe_allow_html=True)

st.title("Slope Analysis — 8° bins (fixed colors)")
st.caption("Upload a KML or draw an AOI. Slope will be classified into 8° bins and shown as a georeferenced raster. Draw on the slope map and export drawn polygon as KML.")

tabs = st.tabs(["📂 Upload Area", "📱 Draw & Inspect"])

# -----------------------------
# TAB 1: Upload
# -----------------------------
with tabs[0]:
    st.subheader("Upload KML to produce slope map")
    uploaded = st.file_uploader("Upload KML (Polygon)", type=["kml"])

    if uploaded:
        open("uploaded.kml", "wb").write(uploaded.read())
        try:
            gdf = gpd.read_file("uploaded.kml", driver="KML")
        except Exception as e:
            st.error(f"Failed to read KML: {e}")
            gdf = None

        if gdf is not None and len(gdf) > 0:
            geom = clean_geometry(gdf.geometry[0])
            if geom is None:
                st.error("Uploaded geometry invalid after cleaning.")
            else:
                st.info("Processing DEM and computing slope (this may take some seconds)...")
                png = process_slope_raster(geom)
                if png:
                    st.success("Slope map created.")
                    m = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=13)
                    m.add_basemap("HYBRID")

                    # add slope image (PNG + PGW) and the boundary polygon
                    m.add_image(png, "slope.pgw", layer_name="Slope Map", opacity=0.85)
                    m.add_gdf(gdf, layer_name="Boundary")

                    # Add Draw tools so user can draw on the slope map
                    draw = Draw(
                        draw_options={
                            "polygon": True,
                            "rectangle": True,
                            "polyline": False,
                            "circle": False,
                            "marker": False,
                            "circlemarker": False,
                        },
                        edit_options={"edit": True, "remove": True},
                    )
                    draw.add_to(m)

                    # legend (simple)
                    legend_dict = {
                        "0-8°": "#ADD8E6",
                        "8-16°": "#90EE90",
                        "16-24°": "#006400",
                        "24-32°": "#FFFF66",
                        "32-40°": "#FFA500",
                        "40-48°": "#FF0000",
                        "48-56°": "#8B0000",
                        "56-64°": "#800080",
                        ">64°": "#000000",
                    }
                    try:
                        m.add_legend(title="Slope classes (°)", legend_dict=legend_dict)
                    except Exception:
                        pass

                    m.to_streamlit(height=600)

                    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
                    if st.button("Export last drawn polygon as KML"):
                        last = m.get_last_draw()
                        if last is None:
                            st.error("No polygon drawn on the map.")
                        else:
                            g = shape(last["geometry"])
                            kml = simplekml.Kml()
                            pol = kml.newpolygon()
                            # ensure closed ring when writing coords
                            coords = list(g.exterior.coords)
                            if coords[0] != coords[-1]:
                                coords.append(coords[0])
                            pol.outerboundaryis = coords
                            kml.save("exported_drawn.kml")
                            st.download_button("Download exported_drawn.kml", open("exported_drawn.kml","rb").read(), "exported_drawn.kml", mime="application/vnd.google-earth.kml+xml")
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.error("Slope processing failed.")
        else:
            st.info("Upload a polygon KML to begin.")

# -----------------------------
# TAB 2: Draw & Inspect
# -----------------------------
with tabs[1]:
    st.subheader("Draw area → process slope → draw again on slope → export KML")

    m = leafmap.Map(center=[11.0, 78.0], zoom=6)
    m.add_basemap("HYBRID")

    draw = Draw(
        draw_options={
            "polygon": True,
            "rectangle": True,
            "polyline": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)
    m.to_streamlit(height=600, css_class="mobile-map")

    st.markdown("<div class='action-bar'>", unsafe_allow_html=True)
    if st.button("⚙️ Process slope for drawn AOI"):
        last = m.get_last_draw()
        if last is None:
            st.error("Draw an AOI first.")
        else:
            geom = clean_geometry(shape(last["geometry"]))
            if geom is None:
                st.error("AOI geometry invalid after cleaning.")
            else:
                st.info("Generating slope raster...")
                png = process_slope_raster(geom)
                if png:
                    st.success("Slope generated — now draw on slope map and export polygon.")
                    m2 = leafmap.Map(center=[geom.centroid.y, geom.centroid.x], zoom=13)
                    m2.add_basemap("HYBRID")
                    m2.add_image("slope.png", "slope.pgw", layer_name="Slope Map", opacity=0.85)

                    # add draw plugin again to draw on slope map
                    draw2 = Draw(
                        draw_options={
                            "polygon": True,
                            "rectangle": True,
                            "polyline": False,
                            "circle": False,
                            "marker": False,
                        },
                        edit_options={"edit": True, "remove": True},
                    )
                    draw2.add_to(m2)

                    m2.to_streamlit(height=600)

                    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
                    if st.button("Export polygon drawn on slope map to KML"):
                        last2 = m2.get_last_draw()
                        if last2 is None:
                            st.error("Draw a polygon on the slope map first.")
                        else:
                            g = shape(last2["geometry"])
                            kml = simplekml.Kml()
                            pol = kml.newpolygon()
                            coords = list(g.exterior.coords)
                            if coords[0] != coords[-1]:
                                coords.append(coords[0])
                            pol.outerboundaryis = coords
                            kml.save("output_drawn_slope.kml")
                            st.download_button("Download output_drawn_slope.kml", open("output_drawn_slope.kml","rb").read(), "output_drawn_slope.kml", mime="application/vnd.google-earth.kml+xml")
                else:
                    st.error("Slope raster generation failed.")
    st.markdown("</div>", unsafe_allow_html=True)

# End of app.py
