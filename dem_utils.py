import requests
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping
from shapely.validation import make_valid
from shapely.ops import unary_union
from shapely.geometry import Polygon
from skimage import measure
import simplekml
import geopandas as gpd
import streamlit as st


def clean_geometry(geom):
    """Fix invalid polygons automatically."""
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        geom = unary_union([g for g in geom if g.geom_type == "Polygon"])
    return geom


def safe_bbox(geom):
    """Ensure bbox has valid north/south/east/west ordering."""
    minx, miny, maxx, maxy = geom.bounds

    south = min(miny, maxy)
    north = max(miny, maxy)
    west = min(minx, maxx)
    east = max(minx, maxx)

    return west, south, east, north


def download_dem_from_opentopo(bbox, out_path="dem.tif"):
    api_key = st.secrets["OPENTOPO_API_KEY"]

    west, south, east, north = bbox

    url = (
        "https://portal.opentopography.org/API/globaldem?"
        f"demtype=SRTMGL1&south={south}&north={north}"
        f"&west={west}&east={east}&outputFormat=GTiff"
        f"&API_Key={api_key}"
    )

    # Debug
    st.write("DEM URL:", url)

    r = requests.get(url)

    if r.status_code != 200:
        st.error(f"OpenTopography Error {r.status_code}: {r.text}")
        return None

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


def detect_flat_areas_from_polygon(geom, slope_threshold=0.5):
    geom = clean_geometry(geom)

    bbox = safe_bbox(geom)

    dem_file = download_dem_from_opentopo(bbox)
    if dem_file is None:
        return None

    with rasterio.open(dem_file) as src:
        dem_img, transform = mask(src, [mapping(geom)], crop=True)

    dem = dem_img[0].astype(float)

    gy, gx = np.gradient(dem)
    slope = np.sqrt(gx**2 + gy**2)

    flat_mask = slope < slope_threshold

    kml = simplekml.Kml()
    contours = measure.find_contours(flat_mask, 0.5)

    for contour in contours:
        coords = []
        for y, x in contour:
            lon, lat = rasterio.transform.xy(transform, y, x)
            coords.append((lon, lat))

        pol = kml.newpolygon(name="Flat Area")
        pol.outerboundaryis = coords

    out = "flat_areas.kml"
    kml.save(out)
    return out
