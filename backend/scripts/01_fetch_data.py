#
# fetches restaurant data from the Google Places API using predetermined search areas
#

import os
import csv
import math
import logging
import requests

from dotenv import load_dotenv
from tqdm import tqdm 

from app.config import DATA_DIR, SCRIPTS_DIR

# ------------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    filename=SCRIPTS_DIR / "logs" / "fetch_data.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

OUTPUT_FILE = DATA_DIR / "places_data.csv"

FAILED_FILE = DATA_DIR / "failed_points.csv" # all points that reached the API and failed
PROCESSED_FILE = DATA_DIR / "processed_points.csv" # all points that reached the API
SKIP_IDS_FILE = DATA_DIR / "processed_seeds.csv" # all seeds that haven't been used yet

POINTS_FILE_1KM = DATA_DIR / "1km_seeds.csv"
POINTS_FILE_500M = DATA_DIR / "500m_seeds.csv"

APPROX_M_PER_DEG = 111_320

ONE_KM = 1000.0
HALF_KM = 500.0

PLACES_API_KEY = os.getenv("PLACES_API_KEY")

INCLUDED_TYPES = [
    "restaurant",
    "coffee_shop",
    "bar",
    "cafe",
    "bakery",
]

FIELD_MASK = [
    "places.displayName",
    "places.formattedAddress",
    "places.id",
    "places.businessStatus",
    "places.primaryType",
    "places.priceLevel",
    "places.priceRange",
    "places.rating",
    "places.location",
    "places.userRatingCount",
]

OUTPUT_HEADERS = [
    "id",
    "displayName",
    "primaryType",
    "formattedAddress",
    "lat",
    "lng",
    "priceLevel",
    "priceRange",
    "rating",
    "userRatingCount",
]

API_CALL_LIMIT = 1000
api_call_count = 0
api_limit_reached = False

# ------------------------------------------------------------------------------

class APICallLimitReached(Exception):
    pass

def initialize_files() -> None:
    """
    creates all tracking/output CSVs with headers if they don't exist.
    """
    file_headers = {
        OUTPUT_FILE: OUTPUT_HEADERS,
        FAILED_FILE: ["lat", "lng", "radius_m", "error"],
        PROCESSED_FILE: ["lat", "lng", "radius_m"],
        SKIP_IDS_FILE: ["place_id"],
    }

    for file_path, headers in file_headers.items():
        if not file_path.exists():
            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            logger.info(f"Initialized {file_path.name}")


def flatten_place(place: dict) -> dict:
    """
    flattens a raw place object into a flat dict matching OUTPUT_HEADERS
    """
    display_name = place.get("displayName") or {}
    location = place.get("location") or {}
    price_range = place.get("priceRange")

    # format price range str
    price_range_str = ""
    if price_range:
        start = price_range.get("startPrice") or {}
        end = price_range.get("endPrice") or {}
        currency = start.get("currencyCode") or end.get("currencyCode") or ""
        start_units = start.get("units", "")
        end_units = end.get("units", "")
        price_range_str = f"{currency} {start_units}-{end_units}".strip()

    return {
        "id": place.get("id", ""),
        "displayName": display_name.get("text", ""),
        "formattedAddress": place.get("formattedAddress", ""),
        "primaryType": place.get("primaryType", ""),
        "priceLevel": place.get("priceLevel", ""),
        "priceRange": price_range_str,
        "rating": place.get("rating", ""),
        "lat": location.get("latitude", ""),
        "lng": location.get("longitude", ""),
        "userRatingCount": place.get("userRatingCount", ""),
    }

def load_existing_place_ids() -> set:
    """
    loads place IDs already present in the output file
    """

    place_ids = set()
    with open(OUTPUT_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            place_id = (row.get("id") or "").strip()
            if place_id:
                place_ids.add(place_id)
    logger.info(f"Loaded {len(place_ids)} existing place IDs.")

    return place_ids


def load_skip_ids() -> set:
    """
    loads seed ids that should be skipped (already done)
    """

    skip_ids = set()

    if not SKIP_IDS_FILE.exists():
        logger.info(f"No skip-ids file found at {SKIP_IDS_FILE}, skipping nothing.")
        return skip_ids

    with open(SKIP_IDS_FILE, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header row
        for row in reader:
            if not row: continue
            skip_ids.add(row[0].strip())

    logger.info(f"Loaded {len(skip_ids)} ids to skip.")

    return skip_ids


def save_failed_point(lat: float, lng: float, radius_m: float, error: Exception):
    with open(FAILED_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([lat, lng, radius_m, str(error)])

def save_processed_point(lat: float, lng: float, radius_m: float):
    with open(PROCESSED_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([lat, lng, radius_m])

def save_places(places: list, existing_place_ids: set):
    """
    append new places to the output file (no duplicates or non-operational restaurants)
    """

    new_places = []
    # ensure no duplicates and no non-operational restaurants
    for place in places:
        place_id = place.get("id")

        if not place_id:
            logger.warning("Skipping, no place id.")
            continue

        if place_id in existing_place_ids:
            logger.warning(f"Skipping, duplicate place (id={place_id})")
            continue

        business_status = place.get("businessStatus", "")
        if business_status and business_status != "OPERATIONAL":
            logger.info(f"Skipping non-operational place {place_id}, businessStatus={business_status}")
            continue

        existing_place_ids.add(place_id)
        new_places.append(place)

    if not new_places: return 0

    # write to output file
    with open(OUTPUT_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)

        for place in new_places:
            writer.writerow(flatten_place(place))

    return len(new_places)

def make_api_call(url: str, headers: dict, body: dict) -> requests.Response:
    global api_call_count
    if api_call_count >= API_CALL_LIMIT:
        raise APICallLimitReached(
            f"API call limit of {API_CALL_LIMIT} reached."
        )
    api_call_count += 1
    logger.info(f"API call #{api_call_count}")
    if api_call_count == API_CALL_LIMIT:
        logger.warning(
            f"API call limit of {API_CALL_LIMIT} reached."
        )

    return requests.post(url,headers=headers,json=body,timeout=30)

def search_nearby(lat: float, lng: float, radius_m: float, existing_place_ids: set) -> bool:
    """
    search for places around a point. if max results are returned (20), subdivide
    the search area and search again
    """

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "X-Goog-Api-Key": PLACES_API_KEY,
        "Content-Type": "application/json",
        "X-Goog-FieldMask": ",".join(FIELD_MASK),
    }
    body = {
        "includedTypes": INCLUDED_TYPES,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng,
                },
                "radius": radius_m,
            }
        },
    }

    try:
        response = make_api_call(url, headers, body)
        response.raise_for_status()
        logger.info(
            f"[{response.status_code}] Request succeeded "
            f"for point {lat}, {lng}, radius={radius_m}"
        )
    except APICallLimitReached:
        raise
    except requests.RequestException as e:
        status_code = getattr(e.response, "status_code", "N/A")

        logger.error(
            f"[{status_code}] Request failed "
            f"for point {lat}, {lng}, radius={radius_m}: {e}"
        )

        save_failed_point(lat, lng, radius_m, e)

        return False

    try:
        places = response.json()["places"]
    except ValueError as e:
        logger.error(f"Invalid JSON response for point {lat}, {lng}, radius={radius_m}: {e}")
        save_failed_point(lat, lng, radius_m, e)
        return False

    # max results reached - subdivide and search again
    if len(places) == 20:
        logger.info(f"20 places returned for {lat}, {lng}, radius={radius_m}, subdividing search area")

        sub_radius_m, centers = get_subcircles(lat, lng,radius_m)

        all_succeeded = True
        for center in centers:
            result = search_nearby(
                center["lat"],
                center["lng"],
                sub_radius_m,
                existing_place_ids,
            )

            if not result:
                all_succeeded = False
            else:
                save_processed_point(lat, lng, radius_m)
                
        return all_succeeded

    # less than 20 places returned
    new_count = save_places(places, existing_place_ids)
    logger.info(
        f"Found {len(places)} places at {lat}, {lng}, "
        f"radius={radius_m}; wrote {new_count} new places."
    )

    save_processed_point(lat, lng, radius_m)

    return True


def get_subcircles(lat: float, lng: float, radius_m: float) -> tuple[float, list]:
    """
    return four smaller search circles covering the original circle
    """

    offset_m = radius_m / 2
    sub_radius_m = radius_m / math.sqrt(2)

    d_lat = offset_m / APPROX_M_PER_DEG

    cos_lat = math.cos(math.radians(lat))

    if abs(cos_lat) < 1e-10:
        raise ValueError(f"Cannot calculate longitude offset at latitude {lat}")

    d_lng = offset_m / (APPROX_M_PER_DEG * cos_lat)

    centers = [
        {"lat": lat + d_lat, "lng": lng + d_lng},
        {"lat": lat + d_lat, "lng": lng - d_lng},
        {"lat": lat - d_lat, "lng": lng + d_lng},
        {"lat": lat - d_lat, "lng": lng - d_lng},
    ]

    return sub_radius_m, centers


def process_file(points_file: str, radius_m: float, existing_place_ids: set, skip_ids: set):
    """
    process every point in one CSV file, skipping any whose id is in skip_ids
    """

    logger.info(f"Starting {points_file.name} with radius={radius_m}m")

    with open(points_file, newline="") as f:
        total_points = sum(1 for _ in f) - 1

    skipped_count = 0

    with open(points_file, newline="") as f:
        reader = csv.DictReader(f)

        for row in tqdm(
            reader,
            total=total_points,
            desc=f"{points_file.name}",
            unit="point",
        ):
            point_id = row.get("id")

            if point_id is not None and point_id.strip() in skip_ids:
                skipped_count += 1
                continue

            try:
                lat = float(row["y"])
                lng = float(row["x"])

            except Exception as e:
                logger.error(f"Invalid point in {points_file.name}: {row} - {e}")
                continue

            search_nearby(lat, lng, radius_m, existing_place_ids)

    logger.info(
        f"Finished {points_file.name}, skipped {skipped_count} already-processed points, "
        f"total unique places: {len(existing_place_ids)}"
    )


def main():
    if not PLACES_API_KEY:
        raise RuntimeError("PLACES_API_KEY environment variable is not set.")

    initialize_files()
    existing_place_ids = load_existing_place_ids()
    skip_ids = load_skip_ids()

    try:
        # process low-density search areas
        if POINTS_FILE_1KM.exists():
            process_file(POINTS_FILE_1KM, ONE_KM, existing_place_ids, skip_ids)
        else:
            logger.warning(f"Points file not found: {POINTS_FILE_1KM}")

        # process high-density search areas
        if POINTS_FILE_500M.exists():
            process_file(POINTS_FILE_500M, HALF_KM, existing_place_ids, skip_ids)
        else:
            logger.warning(f"Points file not found: {POINTS_FILE_500M}")

    except APICallLimitReached as e:
        logger.warning(str(e))
        print(f"WARNING: {e}")
        print("Processing stopped before all points were processed.")

    print(f"Total API calls made: {api_call_count}")
    print(f"All done, found {len(existing_place_ids)} unique places")


if __name__ == "__main__":
    main()