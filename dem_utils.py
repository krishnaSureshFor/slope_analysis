import requests
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping, Polygon
from shapely.validation import make_valid
from shapely.ops import unary_union
from PIL import Image
import streamlit as st
import base64
from io import BytesIO
from rasterio.transform import array_bounds


# ---------------------------------------------------------
# Fix polygon geometry
# ---------------------------------------------------------
def clean_geometry(geom):
    if geom is None:
        return None

    if not geom.is_valid:
        geom = make_valid(geom)

    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom if g.geom_type == "Polygon"]
        if not polys:
            return None
        geom = unary_union(polys)

    if geom.geom_type == "Polygon":
        coords = list(geom.exterior.coords)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geom = Polygon(coords)

    return geom


# ---------------------------------------------------------
# Proper bounding box
# ---------------------------------------------------------
def safe_bbox(geom):
    minx, miny, maxx, maxy = geom.bounds
    return (
        min(minx, maxx),  # west
        min(miny, maxy),  # south
        max(minx, maxx),  # east
        max(miny, maxy),  # north
    )


# ---------------------------------------------------------
# DEM downloader with fallback
# ---------------------------------------------------------
def download_dem(bbox, out_path="dem.tif"):
    if "OPENTOPO_API_KEY" not in st.secrets:
        st.error("Missing OPENTOPO_API_KEY in secrets.")
        return None

    api_key = st.secrets["OPENTOPO_API_KEY"]
    west, south, east, north = bbox

    urls = [
        f"https://portal.opentopography.org/API/globaldem?demtype=SRTMGL1&south={south}&north={north}&west={west}&east={east}&outputFormat=GTiff&API_Key={api_key}",
        f"https://portal-opentopography-us-west-2.s3.us-west-2.amazonaws.com/API/globaldem?demtype=SRTMGL1&south={south}&north={north}&west={west}&east={east}&outputFormat=GTiff&API_Key={api_key}",
    ]

    for attempt in range(1, 6):
        for url in urls:
            try:
                st.write(f"DEM attempt {attempt}: {url}")
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    with open(out_path, "wb") as f:
                        f.write(r.content)
                    return out_path
            except Exception as e:
                st.write(f"Failed: {e}")

        st.write("Retrying...")

    st.error("DEM download failed.")
    return None


# ---------------------------------------------------------
# MAIN SLOPE PROCESSOR (returns base64 PNG + bounds)
# ---------------------------------------------------------
def process_slope(geom):

    geom = clean_geometry(geom)
    if geom is None:
        st.error("Invalid geometry.")
        return None

    bbox = safe_bbox(geom)

    dem_path = download_dem(bbox)
    if dem_path is None:
        return None

    # Clip DEM
    try:
        with rasterio.open(dem_path) as src:
            dem_img, transform = mask(src, [mapping(geom)], crop=True)
            nodata = src.nodata
    except Exception as e:
        st.error(f"DEM clip error: {e}")
        return None

    dem = dem_img[0].astype("float32")

    if nodata is not None:
        dem[dem == nodata] = np.nan
    if np.isnan(dem).all():
        st.error("DEM contains only nodata.")
        return None
    dem[np.isnan(dem)] = np.nanmean(dem)

    # Slope
    gy, gx = np.gradient(dem)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))

    # Classify (8-degree bins)
    classes = np.clip((slope // 8).astype(int), 0, 8)

    # Color table
    COLORS = [
        (173, 216, 230),  # 0 light blue
        (144, 238, 144),  # 1 light green
        (0, 100, 0),      # 2 dark green
        (255, 255, 102),  # 3 yellow
        (255, 165, 0),    # 4 orange
        (255, 0, 0),      # 5 red
        (139, 0, 0),      # 6 dark red
        (128, 0, 128),    # 7 purple
        (0, 0, 0),        # 8 black
    ]

    h, w = classes.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for i, color in enumerate(COLORS):
        rgb[classes == i] = color

    # Base64 encode PNG
    buffer = BytesIO()
    Image.fromarray(rgb).save(buffer, "PNG")
    img_bytes = buffer.getvalue()
    img_b64 = base64.b64encode(img_bytes).decode()

    # Correct bounds
    minY, minX, maxY, maxX = array_bounds(h, w, transform)

    return {
        "data_url": f"data:image/png;base64,{img_b64}",
        "bounds": [[minY, minX], [maxY, maxX]],
    }
