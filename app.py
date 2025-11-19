import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
import folium
from dem_utils import process_slope


st.set_page_config(page_title="Slope Analysis", layout="wide")
st.title("Slope Analysis Tool")


# ---------------------------------------------------------
# Load only polygon layer from KML
# ---------------------------------------------------------
def load_polygon_from_kml(file):
    gdf = gpd.read_file(file)

    # Keep only polygons/multipolygons
    poly_gdf = gdf[gdf.geometry.apply(
        lambda g: isinstance(g, (Polygon, MultiPolygon))
    )]

    if poly_gdf.empty:
        st.error("❌ This KML has no polygon boundaries. It contains only points/lines.")
        return None

    # Merge all polygon pieces into one
    merged = poly_gdf.unary_union

    return merged


# ---------------------------------------------------------
# INPUT SECTION
# ---------------------------------------------------------
uploaded = st.file_uploader("Upload KML", type=["kml"])
draw_mode = st.checkbox("Or draw AOI manually", value=False)

geom = None

# Load uploaded polygon KML
if uploaded:
    geom = load_polygon_from_kml(uploaded)

# Draw AOI manually
if draw_mode:
    m = leafmap.Map(draw_control=True)
    m.to_streamlit(height=450)

    if m.user_roi_bounds() is not None:
        geom = m.user_roi_as_geometry()


# ---------------------------------------------------------
# GENERATE SLOPE MAP
# ---------------------------------------------------------
if geom is not None and st.button("Generate Slope Map"):

    result = process_slope(geom)

    if result:
        st.success("Slope map created.")

        centroid = [geom.centroid.y, geom.centroid.x]
        m2 = leafmap.Map(center=centroid, zoom=13)
        m2.add_basemap("HYBRID")

        # Correct bounds
        min_lat, min_lon = result["bounds"][0]
        max_lat, max_lon = result["bounds"][1]

        if min_lat > max_lat:
            min_lat, max_lat = max_lat, min_lat
        if min_lon > max_lon:
            min_lon, max_lon = max_lon, min_lon

        bounds = [[min_lat, min_lon], [max_lat, max_lon]]

        # Add slope raster overlay
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

        # -----------------------------
        # LEGEND
        # -----------------------------
        legend_html = """
        <div style="
            position: fixed;
            bottom: 25px;
            left: 25px;
            z-index: 9999;
            background-color: white;
            padding: 10px 15px;
            border: 2px solid #444;
            border-radius: 8px;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
            max-width: 180px;
            font-size: 14px;
        ">
        <b>Slope Classes (°)</b><br>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#ADD8E6;"></div>&nbsp;0–8°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#90EE90;"></div>&nbsp;8–16°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#006400;"></div>&nbsp;16–24°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#FFFF66;"></div>&nbsp;24–32°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#FFA500;"></div>&nbsp;32–40°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#FF0000;"></div>&nbsp;40–48°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#8B0000;"></div>&nbsp;48–56°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#800080;"></div>&nbsp;56–64°</div>
        <div style="display:flex;align-items:center;"><div style="width:18px;height:18px;background:#000;"></div>&nbsp;>64°</div>
        </div>
        """
        m2.get_root().html.add_child(folium.Element(legend_html))

        # Display map
        m2.to_streamlit(height=650)
