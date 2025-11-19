import requests
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping
from skimage import measure
import simplekml
import geopandas as gpd
import streamlit as st


def download_dem_from_opentopo(bbox, out_path="dem.tif"):
    api_key = st.secrets["OPENTOPO_API_KEY"]

    dataset = "SRTMGL1"

    url = (
        "https://portal.opentopography.org/API/globaldem?"
        f"demtype={dataset}&south={bbox[1]}&north={bbox[3]}"
        f"&west={bbox[0]}&east={bbox[2]}"
        f"&outputFormat=GTiff&API_Key={api_key}"
    )

    r = requests.get(url)

    if r.status_code != 200:
        raise Exception(f"DEM download failed: {r.status_code} - {r.text}")

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path


def detect_flat_areas_from_polygon(geom, slope_threshold=0.5):
    bbox = geom.bounds
    dem_file = download_dem_from_opentopo(bbox)

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

    output = "flat_areas.kml"
    kml.save(output)
    return output
