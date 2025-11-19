import streamlit as st
import leafmap.foliumap as leafmap
import folium
import geopandas as gpd
from shapely.geometry import shape
from dem_utils import process_slope

st.set_page_config(layout="wide", page_title="Slope Analysis")

st.title("Slope Analysis Tool (Base64 Raster Version)")


# ---------------------------------------------------------
# UPLOAD KML
# ---------------------------------------------------------
uploaded = st.file_uploader("Upload KML", type=["kml"])

draw_mode = st.checkbox("Or draw area on map", value=False)

geom = None


# Load geometry from KML
if uploaded:
    gdf = gpd.read_file(uploaded)
    geom = gdf.geometry.iloc[0]


# Draw AOI
if draw_mode:
    m = leafmap.Map(draw_control=True, measure_control=False)
    m.to_streamlit(height=500)

    drawn = m.user_roi_bounds()
    if drawn:
        g = m.user_roi_as_geometry()
        geom = g


# ---------------------------------------------------------
# RUN SLOPE PROCESSING
# ---------------------------------------------------------
if geom is not None and st.button("Generate Slope Map"):
    result = process_slope(geom)
    if result:

        st.success("Slope map created.")

        # Show map
        centroid = [geom.centroid.y, geom.centroid.x]
        m2 = leafmap.Map(center=centroid, zoom=13)
        m2.add_basemap("HYBRID")

        # Add slope raster
        folium.raster_layers.ImageOverlay(
            image=result["data_url"],
            bounds=result["bounds"],
            opacity=1.0,            # FULL opacity (max visibility)
            interactive=True,
            cross_origin=False,
        ).add_to(m2)


        # Add boundary
        gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
        m2.add_gdf(gdf, layer_name="AOI")

        m2.to_streamlit(height=600)

