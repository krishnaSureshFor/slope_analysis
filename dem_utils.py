import requests
import rasterio
import numpy as np
from rasterio.mask import mask
from rasterio.transform import array_bounds
from shapely.geometry import mapping, Polygon, LinearRing
from shapely.validation import make_valid
from shapely.ops import unary_union
from PIL import Image
import streamlit as st


# ---------------------------------------------------------
# Clean and fix invalid polygon geometries
# ---------------------------------------------------------
def clean_geometry(geom):
    if geom is None:
        return None

    # Fix invalid geometry
    if not geom.is_valid:
        geom = make_valid(geom)

    # Extract polygons if GeometryCollection
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom if g.geom_type == "Polygon"]
        if not polys:
            return None
        geom = unary_union(polys)

    # Ensure polygon rings are closed
    if geom.geom_type == "Polygon":
        ext = geom.exterior
        coords = list(ext.coords)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        geom = Polygon(coords, [list(i.coords) for i in geom.interiors])

    return geom


# ---------------------------------------------------------
# Safe bounding box ordering
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
# Download DEM from OpenTopography
# ---------------------------------------------------------
def download_dem_from_opentopo(bbox, out_path="dem.tif"):
    if "OPENTOPO_API_KEY" not in st.secrets:
        st.error("Missing OPENTOPO_API_KEY in Streamlit secrets.")
        return None

    api_key = st.secrets["OPENTOPO_API_KEY"]
    west, south, east, north = bbox

    url = (
        "https://portal.opentopography.org/API/globaldem?"
        f"demtype=SRTMGL1&south={south}&north={north}"
        f"&west={west}&east={east}&outputFormat=GTiff"
        f"&API_Key={api_key}"
    )

    st.write("DEM URL:", url)

    try:
        r = requests.get(url, timeout=90)
    except Exception as e:
        st.error(f"DEM request failed: {e}")
        return None

    if r.status_code != 200:
        st.error(f"OpenTopo Error {r.status_code}: {r.text}")
        return None

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


# ---------------------------------------------------------
# Process AOI → Clip DEM → Calculate Slope → Classify → Save PNG + PGW
# ---------------------------------------------------------
def process_slope_raster(geom):

    geom = clean_geometry(geom)
    if geom is None:
        st.error("Geometry invalid even after cleaning.")
        return None

    bbox = safe_bbox(geom)

    dem_path = download_dem_from_opentopo(bbox, out_path="dem.tif")
    if dem_path is None:
        return None

    # Clip DEM with AOI
    try:
        with rasterio.open(dem_path) as src:
            dem_img, out_transform = mask(src, [mapping(geom)], crop=True)
            nodata = src.nodata
    except Exception as e:
        st.error(f"Failed to clip DEM: {e}")
        return None

    dem = dem_img[0].astype("float32")

    # Replace nodata with mean of valid values
    if nodata is not None:
        dem[dem == nodata] = np.nan

    if np.isnan(dem).all():
        st.error("DEM after clipping contains only nodata!")
        return None

    if np.isnan(dem).any():
        dem[np.isnan(dem)] = np.nanmean(dem)

    # ----- Slope computation -----
    gy, gx = np.gradient(dem)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    # ----- Classify slope in 8-degree bins -----
    classes = np.floor(slope / 8).astype(int)
    classes[classes < 0] = 0
    classes[classes > 8] = 8  # Cap >64° to class 8

    # ----- Fixed Color Table -----
    COLOR_TABLE = [
        (173, 216, 230),  # 0: Light Blue
        (144, 238, 144),  # 1: Light Green
        (0, 100, 0),      # 2: Dark Green
        (255, 255, 102),  # 3: Yellow
        (255, 165, 0),    # 4: Orange
        (255, 0, 0),      # 5: Red
        (139, 0, 0),      # 6: Dark Red
        (128, 0, 128),    # 7: Purple
        (0, 0, 0),        # 8: Black
    ]

    # ----- Build RGB raster -----
    h, w = classes.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for i, color in enumerate(COLOR_TABLE):
        rgb[classes == i] = color

    # Save slope.png
    png_path = "slope.png"
    Image.fromarray(rgb).save(png_path, "PNG")

    # ----- Correct WorldFile using array_bounds -----
    bounds = array_bounds(h, w, out_transform)
    bottom, left, top, right = bounds  # rasterio order: (bottom, left, top, right)

    pixel_width = out_transform.a            # positive
    pixel_height = out_transform.e           # negative

    # CENTER of top-left pixel
    X_center = left + (pixel_width / 2)
    Y_center = top + (pixel_height / 2)

    with open("slope.pgw", "w") as wf:
        wf.write(f"{pixel_width}\n")
        wf.write("0.0\n")
        wf.write("0.0\n")
        wf.write(f"{pixel_height}\n")
        wf.write(f"{X_center}\n")
        wf.write(f"{Y_center}\n")

    return png_path
