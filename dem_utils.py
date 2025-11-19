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
# Clean and fix polygon geometries
# ---------------------------------------------------------
def clean_geometry(geom):
    """Fix invalid geometries and ensure closed rings."""
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
        min(minx, maxx),  # west  (lon_min)
        min(miny, maxy),  # south (lat_min)
        max(minx, maxx),  # east  (lon_max)
        max(miny, maxy),  # north (lat_max)
    )


# ---------------------------------------------------------
# DEM download with retry + fallback
# ---------------------------------------------------------
def download_dem_from_opentopo(bbox, out_path="dem.tif"):
    """Download SRTM from OpenTopography with retries."""
    if "OPENTOPO_API_KEY" not in st.secrets:
        st.error("Missing OPENTOPO_API_KEY in Streamlit secrets.")
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
                else:
                    st.write(f"Server responded {r.status_code}")
            except Exception as e:
                st.write(f"Attempt failed: {e}")

        st.write("Retrying…")

    st.error("All DEM download attempts failed.")
    return None


# ---------------------------------------------------------
# Main Slope Processor
# ---------------------------------------------------------
def process_slope_raster(geom):

    geom = clean_geometry(geom)
    if geom is None:
        st.error("Invalid geometry.")
        return None

    bbox = safe_bbox(geom)

    dem_path = download_dem_from_opentopo(bbox)
    if dem_path is None:
        return None

    # ---- Clip DEM ----
    try:
        with rasterio.open(dem_path) as src:
            dem_img, out_transform = mask(src, [mapping(geom)], crop=True)
            nodata = src.nodata
    except Exception as e:
        st.error(f"DEM clip failed: {e}")
        return None

    dem = dem_img[0].astype("float32")

    # ---- Handle NODATA ----
    if nodata is not None:
        dem[dem == nodata] = np.nan
    if np.isnan(dem).all():
        st.error("DEM contains only nodata after clipping.")
        return None
    dem[np.isnan(dem)] = np.nanmean(dem)

    # ---- Slope computation ----
    gy, gx = np.gradient(dem)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    # ---- Classification (8° bins) ----
    classes = np.floor(slope / 8).astype(int)
    classes = np.clip(classes, 0, 8)

    COLOR_TABLE = [
        (173, 216, 230),  # 0: Light blue
        (144, 238, 144),  # 1: Light green
        (0, 100, 0),      # 2: Dark green
        (255, 255, 102),  # 3: Yellow
        (255, 165, 0),    # 4: Orange
        (255, 0, 0),      # 5: Red
        (139, 0, 0),      # 6: Dark red
        (128, 0, 128),    # 7: Purple
        (0, 0, 0),        # 8: Black
    ]

    h, w = classes.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for i, color in enumerate(COLOR_TABLE):
        rgb[classes == i] = color

    # ---- Save PNG ----
    png_path = "slope.png"
    Image.fromarray(rgb).save(png_path, "PNG")

    # ---------------------------------------------------------
    # PERFECT BOUNDS FIX
    # Create a temp raster in memory to get correct bounds
    # ---------------------------------------------------------
    with rasterio.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=h,
            width=w,
            count=1,
            dtype="float32",
            transform=out_transform,
        ) as tmp:
            tmp.write(dem, 1)
            minX, minY, maxX, maxY = tmp.bounds  # ALWAYS CORRECT

    # ---- Write worldfile ----
    pixel_width = out_transform.a        # +value
    pixel_height = out_transform.e       # -value

    X_center = minX + (pixel_width / 2)
    Y_center = maxY + (pixel_height / 2)

    with open("slope.pgw", "w") as wf:
        wf.write(f"{pixel_width}\n")
        wf.write("0.0\n")
        wf.write("0.0\n")
        wf.write(f"{pixel_height}\n")
        wf.write(f"{X_center}\n")
        wf.write(f"{Y_center}\n")

    # ---- Debug info ----
    st.write("Transform:", out_transform)
    st.write("Correct bounds:", (minX, minY, maxX, maxY))
    st.write("PNG shape:", rgb.shape)
    st.write("Slope classes:", (int(classes.min()), int(classes.max())))

    st.download_button("Download slope.png (debug)", open("slope.png", "rb"), "slope.png")
    st.download_button("Download slope.pgw (debug)", open("slope.pgw", "rb"), "slope.pgw")

    return png_path
