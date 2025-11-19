import requests
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping
from shapely.validation import make_valid
from shapely.ops import unary_union
import streamlit as st
from PIL import Image


# FIX INVALID GEOMETRIES
def clean_geometry(geom):
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        geom = unary_union([g for g in geom if g.geom_type == "Polygon"])
    return geom


# FIX BOUNDING BOX ORDER
def safe_bbox(geom):
    minx, miny, maxx, maxy = geom.bounds
    return (
        min(minx, maxx),  # west
        min(miny, maxy),  # south
        max(minx, maxx),  # east
        max(miny, maxy),  # north
    )


# DOWNLOAD DEM FROM OPENTOPOGRAPHY
def download_dem_from_opentopo(bbox, out_path="dem.tif"):
    api_key = st.secrets["OPENTOPO_API_KEY"]
    west, south, east, north = bbox

    url = (
        "https://portal.opentopography.org/API/globaldem?"
        f"demtype=SRTMGL1&south={south}&north={north}"
        f"&west={west}&east={east}&outputFormat=GTiff"
        f"&API_Key={api_key}"
    )

    r = requests.get(url)

    if r.status_code != 200:
        st.error(f"OpenTopo Error {r.status_code}: {r.text}")
        return None

    open(out_path, "wb").write(r.content)
    return out_path


# PROCESS SLOPE + CLASSIFY + GENERATE RASTER
def process_slope_raster(geom):

    geom = clean_geometry(geom)
    bbox = safe_bbox(geom)

    dem_file = download_dem_from_opentopo(bbox)
    if dem_file is None:
        return None

    with rasterio.open(dem_file) as src:
        dem_img, transform = mask(src, [mapping(geom)], crop=True)

    dem = dem_img[0].astype(float)

    # SLOPE CALCULATION
    gy, gx = np.gradient(dem)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    # SLOPE INTO 8° BINS
    classes = np.floor(slope / 8).astype(int)
    classes[classes < 0] = 0

    # FIXED COLOR TABLE FOR SLOPE CLASSES
    COLOR_TABLE = [
        (173, 216, 230),  # 0: Light Blue
        (144, 238, 144),  # 1: Light Green
        (0, 100, 0),      # 2: Dark Green
        (255, 255, 102),  # 3: Yellow
        (255, 165, 0),    # 4: Orange
        (255, 0, 0),      # 5: Red
        (139, 0, 0),      # 6: Dark Red
        (128, 0, 128),    # 7: Purple
        (0, 0, 0),        # 8+: Black
    ]

    max_class = classes.max()
    if max_class > 8:
        max_class = 8

    # BUILD RGB ARRAY
    h, w = classes.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for i in range(max_class + 1):
        rgb[classes == i] = COLOR_TABLE[i]

    rgb[classes > 8] = COLOR_TABLE[8]

    # SAVE PNG
    img = Image.fromarray(rgb)
    img.save("slope.png", "PNG")

    # WORLD FILE
    with open("slope.pgw", "w") as f:
        f.write(f"{transform[0]}\n0\n0\n{-transform[4]}\n{transform[2]}\n{transform[5]}")

    return "slope.png"
