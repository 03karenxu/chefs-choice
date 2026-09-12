import csv
import sys
import uuid


def normalize_address(address):
    return address.upper()

def clean_csv(input_file, output_file):
    with open(input_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows = [row for row in rows if row.get("businessStatus") in {"OPERATIONAL", ""}]
    fieldnames = [field for field in reader.fieldnames if field not in {"businessStatus", "googleMapsUri"}]

    for row in rows:
        row["id"] = uuid.uuid4().hex
        row["priceLevel"] = row.get("priceLevel", "").removeprefix("PRICE_LEVEL_")
        row["formattedAddress"] = normalize_address(row.get("formattedAddress", ""))

        row.pop("businessStatus", None)
        row.pop("googleMapsUri", None)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} input.csv output.csv")
        sys.exit(1)

    clean_csv(sys.argv[1], sys.argv[2])