# dem_utils.py
import requests
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping, Polygon, LinearRing
from shapely.validation import make_valid
from shapely.ops import unary_union
from PIL import Image
import streamlit as st


def clean_geometry(geom):
    """Make geometry valid, extract polygons, and ensure rings are closed."""
    if geom is None:
        return None

    # Make valid (fix self-intersections etc)
    if not geom.is_valid:
        geom = make_valid(geom)

    # If GeometryCollection -> merge polygons
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom if g.geom_type == "Polygon"]
        if not polys:
            return None
        geom = unary_union(polys)

    # If MultiPolygon or Polygon, ensure outer rings are closed
    if geom.geom_type == "Polygon":
        exterior = geom.exterior
        if not LinearRing(exterior.coords).is_closed:
            coords = list(exterior.coords)
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            geom = Polygon(coords, [list(i.coords) for i in geom.interiors])
    # For MultiPolygon, shapely.make_valid/unary_union above will typically fix rings

    return geom


def safe_bbox(geom):
    """Return bbox as (west, south, east, north) with correct ordering."""
    minx, miny, maxx, maxy = geom.bounds
    west = min(minx, maxx)
    east = max(minx, maxx)
    south = min(miny, maxy)
    north = max(miny, maxy)
    return (west, south, east, north)


def download_dem_from_opentopo(bbox, out_path="dem.tif"):
    """Download SRTMGL1 from OpenTopography using API key in Streamlit secrets."""
    if "OPENTOPO_API_KEY" not in st.secrets:
        st.error("Missing OPENTOPO_API_KEY in Streamlit secrets.")
        return None

    api_key = st.secrets["OPENTOPO_API_KEY"]
    west, south, east, north = bbox

    # Build URL
    url = (
        "https://portal.opentopography.org/API/globaldem?"
        f"demtype=SRTMGL1&south={south}&north={north}"
        f"&west={west}&east={east}&outputFormat=GTiff"
        f"&API_Key={api_key}"
    )

    # Debug (will appear in Streamlit logs)
    st.write("Requesting DEM:", url)

    try:
        r = requests.get(url, timeout=120)
    except Exception as e:
        st.error(f"DEM request failed: {e}")
        return None

    if r.status_code != 200:
        st.error(f"OpenTopography error {r.status_code}: {r.text}")
        return None

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


def process_slope_raster(geom):
    """
    1) Clean geometry
    2) Download DEM for bbox
    3) Clip DEM to polygon
    4) Compute slope in degrees
    5) Classify into 8-degree bins
    6) Save slope PNG and slope.pgw (worldfile)
    Returns path to PNG or None on failure.
    """

    geom = clean_geometry(geom)
    if geom is None:
        st.error("Invalid geometry after cleaning.")
        return None

    bbox = safe_bbox(geom)

    dem_path = download_dem_from_opentopo(bbox, out_path="dem.tif")
    if dem_path is None:
        return None

    try:
        with rasterio.open(dem_path) as src:
            dem_img, out_transform = mask(src, [mapping(geom)], crop=True)
    except Exception as e:
        st.error(f"Failed to clip DEM: {e}")
        return None

    # single band DEM
    dem = dem_img[0].astype(float)

    # handle nodata values if any
    dem[dem == src.nodata] = np.nan
    # simple fill: replace nan with nearest valid (very small AOIs may still work)
    if np.isnan(dem).any():
        # fill nan with local mean to avoid crashes (quick heuristic)
        nan_mask = np.isnan(dem)
        if nan_mask.all():
            st.error("DEM contains only nodata after clipping.")
            return None
        dem[nan_mask] = np.nanmean(dem[~nan_mask])

    # compute gradient in map units (approx) and slope in degrees
    gy, gx = np.gradient(dem)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    # classify into 8-degree bins: class = floor(slope/8)
    classes = np.floor(slope / 8.0).astype(int)
    classes[classes < 0] = 0

    # cap classes above 8 into 8 (8 means >64°)
    classes_clipped = classes.copy()
    classes_clipped[classes_clipped > 8] = 8

    # fixed color table (RGB)
    COLOR_TABLE = [
        (173, 216, 230),  # 0: Light Blue
        (144, 238, 144),  # 1: Light Green
        (0, 100, 0),      # 2: Dark Green
        (255, 255, 102),  # 3: Yellow
        (255, 165, 0),    # 4: Orange
        (255, 0, 0),      # 5: Red
        (139, 0, 0),      # 6: Dark Red
        (128, 0, 128),    # 7: Purple
        (0, 0, 0),        # 8: Black (>64°)
    ]

    h, w = classes_clipped.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for idx, color in enumerate(COLOR_TABLE):
        rgb[classes_clipped == idx] = color

    # Save PNG
    png_path = "slope.png"
    Image.fromarray(rgb).save(png_path, "PNG")

    # Save worldfile (.pgw) for georeferencing:
    # Using the same order used by other code: A, D, B, E, C, F
    # We keep prior convention: transform[0],0,0,-transform[4], transform[2], transform[5]
    try:
        # Correct ESRI Worldfile parameters using Rasterio affine transform
        A = out_transform.a      # pixel width
        D = out_transform.b      # row rotation
        B = out_transform.d      # column rotation
        E = out_transform.e      # pixel height
        
        # IMPORTANT: worldfile expects CENTER of the upper-left pixel
        C = out_transform.c + (out_transform.a / 2)
        F = out_transform.f + (out_transform.e / 2)
        
        with open("slope.pgw", "w") as wf:
            wf.write(f"{A}\n")   # pixel width
            wf.write(f"{D}\n")   # row rotation
            wf.write(f"{B}\n")   # column rotation
            wf.write(f"{E}\n")   # pixel height
            wf.write(f"{C}\n")   # X of upper-left pixel center
            wf.write(f"{F}\n")   # Y of upper-left pixel center


    except Exception as e:
        st.warning(f"Could not write worldfile: {e}")

    return png_path



