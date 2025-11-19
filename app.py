import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
import folium
from dem_utils import process_slope

st.set_page_config(page_title="Slope Analysis", layout="wide")
st.title("Slope Analysis Tool")


uploaded = st.file_uploader("Upload KML", type=["kml"])
draw_mode = st.checkbox("Or draw AOI manually", value=False)

geom = None

# Load uploaded KML
if uploaded:
    gdf = gpd.read_file(uploaded)
    geom = gdf.geometry.iloc[0]

# Draw AOI manually
if draw_mode:
    m = leafmap.Map(draw_control=True)
    m.to_streamlit(height=450)

    if m.user_roi_bounds() is not None:
        geom = m.user_roi_as_geometry()


# -------------------------------------------------------------
# RUN SLOPE
# -------------------------------------------------------------
if geom is not None and st.button("Generate Slope Map"):

    result = process_slope(geom)

    if result:
        st.success("Slope map created.")

        centroid = [geom.centroid.y, geom.centroid.x]
        m2 = leafmap.Map(center=centroid, zoom=13)
        m2.add_basemap("HYBRID")

        # FIX BOUNDS
        min_lat, min_lon = result["bounds"][0]
        max_lat, max_lon = result["bounds"][1]

        if min_lat > max_lat:
            min_lat, max_lat = max_lat, min_lat
        if min_lon > max_lon:
            min_lon, max_lon = max_lon, min_lon

        bounds = [[min_lat, min_lon], [max_lat, max_lon]]

        # Add slope raster
        folium.raster_layers.ImageOverlay(
            image=result["data_url"],
            bounds=bounds,
            opacity=1.0,
            interactive=True,
            cross_origin=False,
        ).add_to(m2)

        # Add AOI boundary
        gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
        m2.add_gdf(gdf, layer_name="AOI")

        m2.to_streamlit(height=650)
