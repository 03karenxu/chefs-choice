#
# merges Vancouver Open Data business licence data with Google Places data.
#

import sys
import re
import math
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

PRINT_NEW_RECORDS = False

NAME_EXACT_THRESHOLD = 85
ADDRESS_EXACT_THRESHOLD = 90
EXACT_DISTANCE_M = 75

# A near duplicate needs a strong address AND coordinate match.
# Name similarity is not required.
ADDRESS_NEAR_THRESHOLD = 90
NEAR_DISTANCE_M = 100

INTERNAL_DISTANCE_M = 75
ASK_INTERNAL_NEAR_MATCHES = True

# Radius used to find candidate Sheet 2 rows before scoring.
CANDIDATE_RADIUS_M = 100

SHEET1_COLUMNS = [
    "FOLDERYEAR", "LicenceRSN", "LicenceNumber", "LicenceRevisionNumber",
    "BusinessName", "BusinessTradeName", "Status", "IssuedDate", "ExpiredDate",
    "BusinessType", "BusinessSubType", "Unit", "UnitType", "House", "Street",
    "City", "Province", "Country", "PostalCode", "LocalArea",
    "NumberofEmployees", "FeePaid", "ExtractDate", "Geom", "geo_point_2d",
]

SHEET2_COLUMNS = [
    "id", "displayName", "formattedAddress", "googleMapsUri", "businessStatus",
    "primaryType", "priceLevel", "priceRange", "rating", "lat", "lng",
    "userRatingCount",
]

STREET_REPLACEMENTS = {
    r"\bst\b": "street", r"\bave\b": "avenue", r"\bav\b": "avenue",
    r"\brd\b": "road", r"\bdr\b": "drive", r"\bblvd\b": "boulevard",
    r"\bhwy\b": "highway", r"\bpkwy\b": "parkway", r"\bln\b": "lane",
    r"\bct\b": "court", r"\bpl\b": "place", r"\bter\b": "terrace",
    r"\bcres\b": "crescent", r"\bway\b": "way", r"\bw\b": "west",
    r"\be\b": "east", r"\bn\b": "north", r"\bs\b": "south",
}

CORPORATE_SUFFIX_RE = re.compile(
    r"\b(ltd|limited|inc|incorporated|corp|corporation|company|co|bc|b c)\b"
)


# ---- string / address normalization ----

def clean_string(value):
    """General text cleanup: case, punctuation, accents, whitespace."""
    if value is None or pd.isna(value):
        return ""
    value = str(value).strip()
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_name(value):
    """Normalize a business name: clean text, drop corporate suffixes."""
    text = clean_string(value)
    if not text:
        return ""
    text = CORPORATE_SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_address(value):
    """Normalize a full address: clean text, expand street abbreviations."""
    text = clean_string(value)
    if not text:
        return ""
    for pattern, replacement in STREET_REPLACEMENTS.items():
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def address_match_key(value):
    """Whitespace-insensitive version of normalize_address, used only for exact-match
    comparisons - so postal codes like 'V5Z1E6' and 'V5Z 1E6' are treated as equal."""
    return re.sub(r"\s+", "", normalize_address(value))


def _valid(value):
    return value and value.lower() not in ("nan", "none")


def build_sheet1_address(row):
    """Build a Google-style address string from Sheet 1 fields."""
    unit, house, street, city, province, postal, country = (
        str(row.get(k, "")).strip()
        for k in ("Unit", "House", "Street", "City", "Province", "PostalCode", "Country")
    )
    parts = []
    if _valid(unit):
        parts.append(f"Unit {unit}")
    street_address = " ".join(v for v in (house, street) if _valid(v))
    if street_address:
        parts.append(street_address)
    locality = " ".join(v for v in (city, province, postal) if _valid(v))
    if locality:
        parts.append(locality)
    if _valid(country):
        parts.append(country)
    return ", ".join(parts)


# ---- coordinates ----

def parse_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        value = str(value).strip()
        return float(value) if value else None
    except (ValueError, TypeError):
        return None


def extract_sheet1_coordinates(row):
    """Parse Sheet 1's 'lat, lng' geo_point_2d field."""
    value = row.get("geo_point_2d", "")
    if value is None or pd.isna(value):
        return None, None
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", str(value).strip())
    if not match:
        return None, None
    return parse_float(match.group(1)), parse_float(match.group(2))


def extract_sheet2_coordinates(row):
    return parse_float(row.get("lat")), parse_float(row.get("lng"))


def haversine_distance_m(lat1, lng1, lat2, lng2):
    """Distance in metres between two coordinates."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    earth_radius = 6_371_000
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat, delta_lng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    return earth_radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---- matching ----

def house_number(text):
    """Extract the leading street-number token, e.g. '545' or '545a'.
    Works on Sheet 1's House field and on a full address string,
    since both start with the number."""
    if text is None:
        return None
    match = re.match(r"\s*(\d+[a-z]?)\b", str(text).strip(), re.I)
    return match.group(1).lower() if match else None


def house_numbers_conflict(house1, house2):
    """True only when both numbers are known and they differ."""
    return house1 is not None and house2 is not None and house1 != house2


def sheet1_name_variants(row):
    """Return normalized BusinessTradeName and BusinessName, trade name first."""
    variants = []
    for column in ("BusinessTradeName", "BusinessName"):
        name = normalize_name(row.get(column, ""))
        if name and name not in variants:
            variants.append(name)
    return variants


def best_name_score(names1, names2):
    return max((fuzz.token_set_ratio(a, b) for a in names1 for b in names2), default=0)


def score_match(name_score, address_score, distance, name_thr, addr_thr, dist_thr, near_addr_thr, near_dist_thr, house_conflict=False):
    """Shared exact/near classification used for both Sheet1<->Sheet2 and internal comparisons.
    house_conflict blocks a match when the street numbers are known and different -
    fuzzy address scoring alone treats '545 W Broadway' and '537 W Broadway' as near-identical."""
    exact = (
        name_score >= name_thr and address_score >= addr_thr
        and distance is not None and distance <= dist_thr
        and not house_conflict
    )
    near = (
        address_score >= near_addr_thr
        and distance is not None and distance <= near_dist_thr
        and not exact and not house_conflict
    )
    return {"name_score": name_score, "address_score": address_score, "distance_m": distance, "exact": exact, "near": near}


def compare_records(sheet1_row, sheet2_row):
    """Compare a Sheet 1 licence record against a Sheet 2 Google Places record."""
    google_name = normalize_name(sheet2_row.get("displayName", ""))
    name_score = best_name_score(sheet1_name_variants(sheet1_row), [google_name]) if google_name else 0

    address1 = normalize_address(build_sheet1_address(sheet1_row))
    address2 = normalize_address(sheet2_row.get("formattedAddress", ""))
    address_score = fuzz.token_set_ratio(address1, address2) if address1 and address2 else 0

    distance = haversine_distance_m(
        *extract_sheet1_coordinates(sheet1_row), *extract_sheet2_coordinates(sheet2_row)
    )

    house_conflict = house_numbers_conflict(
        house_number(sheet1_row.get("House", "")),
        house_number(sheet2_row.get("formattedAddress", "")),
    )

    return score_match(
        name_score, address_score, distance,
        NAME_EXACT_THRESHOLD, ADDRESS_EXACT_THRESHOLD, EXACT_DISTANCE_M,
        ADDRESS_NEAR_THRESHOLD, NEAR_DISTANCE_M,
        house_conflict=house_conflict,
    )


# ---- spatial index (limits Sheet1 x Sheet2 comparisons) ----

def coordinate_grid_key(lat, lng, radius_m):
    """Map a coordinate to an approximate grid cell of size radius_m."""
    if lat is None or lng is None:
        return None
    lat_m = 111_320
    lng_m = 111_320 * math.cos(math.radians(lat))
    return math.floor(lat * lat_m / radius_m), math.floor(lng * lng_m / radius_m)


def build_spatial_index(sheet2_df):
    index = {}
    for j, row in sheet2_df.iterrows():
        key = coordinate_grid_key(*extract_sheet2_coordinates(row), CANDIDATE_RADIUS_M)
        if key is not None:
            index.setdefault(key, []).append(j)
    return index


def get_spatial_candidates(sheet1_row, spatial_index):
    """Return Sheet 2 row indices in the same or adjacent grid cell."""
    key = coordinate_grid_key(*extract_sheet1_coordinates(sheet1_row), CANDIDATE_RADIUS_M)
    if key is None:
        return set()
    cell_lat, cell_lng = key
    candidates = set()
    for dlat in (-1, 0, 1):
        for dlng in (-1, 0, 1):
            candidates.update(spatial_index.get((cell_lat + dlat, cell_lng + dlng), []))
    return candidates


# ---- display / prompts ----

def _print_sheet1_side(row, label):
    print(f"\n{label}")
    print("-" * 90)
    print(f"BusinessName:       {row.get('BusinessName', '')}")
    print(f"BusinessTradeName:  {row.get('BusinessTradeName', '')}")
    print(f"Address:            {build_sheet1_address(row)}")
    print(f"Coordinates:        {extract_sheet1_coordinates(row)}")
    print(f"LicenceRSN:         {row.get('LicenceRSN', '')}")
    print(f"LicenceNumber:      {row.get('LicenceNumber', '')}")


def print_match(metrics, title, sheet1_row, sheet2_row):
    """Print a Sheet 1 vs Sheet 2 comparison (fuzzy scores apply here - Google's
    address formatting can differ from the licence data in ways normalization won't fix)."""
    print(f"\n{'=' * 90}\n{title}\n{'=' * 90}")
    print(f"Name similarity:     {metrics['name_score']:.1f}%")
    print(f"Address similarity:  {metrics['address_score']:.1f}%")
    dist = metrics["distance_m"]
    print(f"Coordinate distance: {dist:.2f} m" if dist is not None else "Coordinate distance:  unavailable")

    _print_sheet1_side(sheet1_row, "SHEET 1")

    print("\nSHEET 2")
    print("-" * 90)
    print(f"displayName:        {sheet2_row.get('displayName', '')}")
    print(f"Address:            {sheet2_row.get('formattedAddress', '')}")
    print(f"Coordinates:        {sheet2_row.get('lat', '')}, {sheet2_row.get('lng', '')}")
    print(f"id:                 {sheet2_row.get('id', '')}")
    print(f"rating:             {sheet2_row.get('rating', '')}")
    print(f"userRatingCount:    {sheet2_row.get('userRatingCount', '')}")
    print("=" * 90)


def print_internal_pair(row1, row2, distance, title):
    """Print two Sheet 1 records being considered as duplicates (exact-match address/coords, differing names)."""
    print(f"\n{'=' * 90}\n{title}\n{'=' * 90}")
    print(f"Coordinate distance: {distance:.2f} m" if distance is not None else "Coordinate distance:  unavailable")
    _print_sheet1_side(row1, "RECORD A")
    _print_sheet1_side(row2, "RECORD B")
    print("=" * 90)


def ask_merge():
    while True:
        answer = input("Merge these records? [yes/no]: ").strip().lower()
        if answer in ("yes", "y"):
            return True
        if answer in ("no", "n"):
            return False
        print("Please enter yes or no.")


def ask_keep_choice():
    """Ask which of two internal duplicate records to keep."""
    while True:
        answer = input("Keep which record? [a/b/skip]: ").strip().lower()
        if answer in ("a", "b", "skip", "s"):
            return "skip" if answer == "s" else answer
        print("Please enter a, b, or skip.")


# ---- Sheet 1 -> Sheet 2 conversion ----

def convert_sheet1_to_sheet2(row):
    """Convert a licence record to Sheet 2's schema. Google-only fields stay blank."""
    lat, lng = extract_sheet1_coordinates(row)
    trade_name = str(row.get("BusinessTradeName", "")).strip()
    business_name = str(row.get("BusinessName", "")).strip()
    return {
        "id": "", "displayName": trade_name or business_name,
        "formattedAddress": build_sheet1_address(row), "googleMapsUri": "",
        "businessStatus": "", "primaryType": "", "priceLevel": "",
        "priceRange": "", "rating": "", "lat": lat if lat is not None else "",
        "lng": lng if lng is not None else "", "userRatingCount": "",
    }


# ---- internal Sheet 1 deduplication ----

def deduplicate_sheet1(df):
    """Remove duplicate Sheet 1 records.

    Two records can only be duplicates if their normalized address is an
    exact match (same source data, so formatting is the only expected
    difference) and their coordinates are close together:
        - names match      -> auto-merge, first occurrence kept
        - names differ      -> ask the user which record to keep

    Records are grouped by exact address up front, so only records that
    could possibly match are ever compared - no all-pairs fuzzy scoring.
    """
    if len(df) <= 1:
        return df.reset_index(drop=True)

    print(f"\n{'=' * 90}\nDEDUPLICATING SHEET 1\n{'=' * 90}")

    df = df.reset_index(drop=True)
    n = len(df)

    # Precompute per-record data once instead of recomputing it on every comparison.
    addresses, name_sets, coords = [], [], []
    for _, row in df.iterrows():
        addresses.append(address_match_key(build_sheet1_address(row)))
        name_sets.append(set(sheet1_name_variants(row)))
        coords.append(extract_sheet1_coordinates(row))

    address_groups = {}
    for i, address in enumerate(addresses):
        if address:
            address_groups.setdefault(address, []).append(i)

    removed = set()

    for indices in address_groups.values():
        if len(indices) < 2:
            continue

        for a_pos, i in enumerate(indices):
            if i in removed:
                continue

            for j in indices[a_pos + 1:]:
                if j in removed:
                    continue

                distance = haversine_distance_m(*coords[i], *coords[j])
                if distance is None or distance > INTERNAL_DISTANCE_M:
                    continue

                row_i, row_j = df.iloc[i], df.iloc[j]

                if name_sets[i] & name_sets[j]:
                    print("\n[AUTO-MERGE INTERNAL DUPLICATE]")
                    print(f"KEEP:   {row_i.get('BusinessTradeName', '')}")
                    print(f"REMOVE: {row_j.get('BusinessTradeName', '')}")
                    print(f"Distance: {distance:.2f} m")
                    removed.add(j)
                    continue

                if not ASK_INTERNAL_NEAR_MATCHES:
                    continue

                print_internal_pair(row_i, row_j, distance, "INTERNAL SHEET 1 NEAR DUPLICATE")
                choice = ask_keep_choice()
                if choice == "a":
                    removed.add(j)
                elif choice == "b":
                    removed.add(i)
                    break  # i is gone - stop comparing it against the rest of the group

    result = df.loc[[i for i in range(n) if i not in removed]].reset_index(drop=True)
    print(f"\nSheet 1 before deduplication: {n}")
    print(f"Sheet 1 after deduplication:  {len(result)}")
    print(f"Internal duplicates removed:   {n - len(result)}")
    return result


# ---- merge ----

def _review_row(sheet1_row, sheet2_row, i, metrics, match_type, decision):
    return {
        "sheet1_row": i,
        "sheet1_name": sheet1_row.get("BusinessTradeName", ""),
        "sheet2_id": sheet2_row.get("id", ""),
        "sheet2_name": sheet2_row.get("displayName", ""),
        "name_score": round(metrics["name_score"], 2),
        "address_score": round(metrics["address_score"], 2),
        "distance_m": round(metrics["distance_m"], 2),
        "match_type": match_type,
        "decision": decision,
    }


def merge_sheets(sheet1_df, sheet2_df, review_path):
    """Merge Sheet 1 into Sheet 2. Sheet 2 stays authoritative for merged records."""
    output_rows = [row.to_dict() for _, row in sheet2_df.iterrows()]
    spatial_index = build_spatial_index(sheet2_df)
    review_rows = []
    exact_matches = near_candidates = near_merged = near_kept_separate = new_records = 0

    print(f"\n{'=' * 90}\nMATCHING SHEET 1 AGAINST SHEET 2\n{'=' * 90}")

    for i, sheet1_row in sheet1_df.iterrows():
        candidates = get_spatial_candidates(sheet1_row, spatial_index)

        exact_match = None
        near_matches = []
        for j in candidates:
            sheet2_row = sheet2_df.iloc[j]
            metrics = compare_records(sheet1_row, sheet2_row)
            if metrics["exact"]:
                exact_match = (j, metrics)
                break
            if metrics["near"]:
                near_matches.append((j, metrics))

        if exact_match is not None:
            j, metrics = exact_match
            sheet2_row = sheet2_df.iloc[j]
            exact_matches += 1
            print(
                f"\n[AUTO-MERGE] {sheet1_row.get('BusinessTradeName', '')} -> "
                f"{sheet2_row.get('displayName', '')} | name={metrics['name_score']:.1f}% "
                f"address={metrics['address_score']:.1f}% distance={metrics['distance_m']:.1f}m"
            )
            review_rows.append(_review_row(sheet1_row, sheet2_row, i, metrics, "exact", "merged"))
            continue

        near_matches.sort(key=lambda x: (-x[1]["address_score"], x[1]["distance_m"]))
        merged = False

        for j, metrics in near_matches:
            sheet2_row = sheet2_df.iloc[j]
            near_candidates += 1
            print_match(metrics, "NEAR DUPLICATE", sheet1_row=sheet1_row, sheet2_row=sheet2_row)
            decision = ask_merge()
            review_rows.append(
                _review_row(sheet1_row, sheet2_row, i, metrics, "near", "merged" if decision else "kept_separate")
            )
            if decision:
                near_merged += 1
                merged = True
                print("-> MERGED. Keeping Sheet 2 record.")
                break
            near_kept_separate += 1
            print("-> Not merged.")

        if merged:
            continue

        converted = convert_sheet1_to_sheet2(sheet1_row)
        output_rows.append(converted)
        new_records += 1
        if PRINT_NEW_RECORDS:
            print(f"\n[NEW] {converted['displayName']} | {converted['formattedAddress']}")

    result = pd.DataFrame(output_rows, columns=SHEET2_COLUMNS)

    review_df = pd.DataFrame(review_rows, columns=[
        "sheet1_row", "sheet1_name", "sheet2_id", "sheet2_name",
        "name_score", "address_score", "distance_m", "match_type", "decision",
    ])
    review_df.to_csv(review_path, index=False)

    print(f"\n{'=' * 90}\nMERGE SUMMARY\n{'=' * 90}")
    print(f"Original Sheet 2 records:       {len(sheet2_df)}")
    print(f"Sheet 1 records processed:      {len(sheet1_df)}")
    print(f"Exact duplicates auto-merged:   {exact_matches}")
    print(f"Near-match candidates reviewed: {near_candidates}")
    print(f"Near matches merged:            {near_merged}")
    print(f"Near matches kept separate:     {near_kept_separate}")
    print(f"New Sheet 1 records added:      {new_records}")
    print(f"Final merged records:            {len(result)}")
    print(f"Review file:                     {review_path}")

    return result


# ---- validation / main ----

def validate_columns(df, expected, name):
    missing = [c for c in expected if c not in df.columns]
    if missing:
        print(f"\nERROR: {name} is missing columns:")
        for column in missing:
            print(f"    {column}")
        sys.exit(1)


def main():
    if len(sys.argv) != 4:
        print(
            "Usage:\n\n    python merge_restaurants.py sheet1.csv sheet2.csv merged.csv\n\n"
            "Example:\n\n    python merge_restaurants.py business-licenses.csv places_data.csv merged.csv"
        )
        sys.exit(1)

    sheet1_path, sheet2_path, output_path = (Path(p) for p in sys.argv[1:4])
    review_path = output_path.parent / f"{output_path.stem}_review.csv"

    if not sheet1_path.exists():
        print(f"ERROR: Sheet 1 not found: {sheet1_path}")
        sys.exit(1)
    if not sheet2_path.exists():
        print(f"ERROR: Sheet 2 not found: {sheet2_path}")
        sys.exit(1)

    print(f"Loading Sheet 1: {sheet1_path}")
    sheet1_df = pd.read_csv(sheet1_path, sep=";", dtype=str, keep_default_na=False)

    print(f"Loading Sheet 2: {sheet2_path}")
    sheet2_df = pd.read_csv(sheet2_path, dtype=str, keep_default_na=False)

    validate_columns(sheet1_df, SHEET1_COLUMNS, "Sheet 1")
    validate_columns(sheet2_df, SHEET2_COLUMNS, "Sheet 2")

    print(f"\nSheet 1 rows: {len(sheet1_df)}")
    print(f"Sheet 2 rows: {len(sheet2_df)}")

    sheet1_df = deduplicate_sheet1(sheet1_df)
    result = merge_sheets(sheet1_df, sheet2_df, review_path)
    result = result[SHEET2_COLUMNS]
    result.to_csv(output_path, index=False, encoding="utf-8")

    print(f"\n{'=' * 90}\nDONE\n{'=' * 90}")
    print(f"Merged output: {output_path}")
    print(f"Review output: {review_path}")


if __name__ == "__main__":
    main()