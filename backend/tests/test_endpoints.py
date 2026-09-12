import pytest

# --- GET /restaurants/ ---------------------------------------------------

def test_get_restaurants_with_valid_params(client, seeded_db):
    response = client.get(
        "/restaurants/",
        params={"price_level": "MODERATE", "sort_by": "rating", "order": "desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(r["priceLevel"] == "MODERATE" for r in data)


def test_get_restaurants_filter_by_type(client, seeded_db):
    response = client.get(
        "/restaurants/",
        params={"type": "Mexican", "sort_by": "name", "order": "asc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(r["type"] == "Mexican" for r in data)
    assert len(data) == 2


def test_get_restaurants_sort_by_rating_desc(client, seeded_db):
    response = client.get(
        "/restaurants/",
        params={"sort_by": "rating", "order": "desc"},
    )
    assert response.status_code == 200
    data = response.json()
    ratings = [r["rating"] for r in data if r["rating"] is not None]
    assert ratings == sorted(ratings, reverse=True)


def test_get_restaurants_sort_by_name_asc(client, seeded_db):
    response = client.get(
        "/restaurants/",
        params={"sort_by": "name", "order": "asc"},
    )
    assert response.status_code == 200
    data = response.json()
    names = [r["name"] for r in data]
    assert names == sorted(names)


@pytest.mark.parametrize(
    "params",
    [
        {"price_level": "NOT_A_LEVEL", "sort_by": "rating", "order": "asc"},
        {"price_level": "INEXPENSIVE", "sort_by": "not_a_field", "order": "asc"},
        {"price_level": "INEXPENSIVE", "sort_by": "rating", "order": "not_valid"},
    ],
    ids=["invalid_price_level", "invalid_sort_field", "invalid_order"],
)
def test_get_restaurants_invalid_params(client, params):
    response = client.get("/restaurants/", params=params)
    assert response.status_code == 422


def test_get_restaurants_empty_db_returns_empty_list(client, db_session):
    # no seeded_db here — DB is empty on purpose
    response = client.get(
        "/restaurants/", params={"sort_by": "rating", "order": "desc"}
    )
    assert response.status_code == 200
    assert response.json() == []


# --- GET /restaurants/types ------------------------------------------------

def test_get_restaurant_types(client, seeded_db):
    response = client.get("/restaurants/types")
    assert response.status_code == 200
    data = response.json()
    assert "types" in data
    assert "count" in data
    assert data["count"] == len(data["types"])
    assert None not in data["types"]
    assert "Italian" in data["types"]
    assert "Mexican" in data["types"]


def test_get_restaurant_types_ordered_by_frequency(client, seeded_db):
    response = client.get("/restaurants/types")
    data = response.json()
    assert data["types"][0] == "Mexican"


def test_get_restaurant_types_empty_db(client, db_session):
    response = client.get("/restaurants/types")
    assert response.status_code == 200
    assert response.json() == {"types": [], "count": 0}


# --- GET /restaurants/types/stats ------------------------------------------

def test_get_type_stats_shape(client, seeded_db):
    response = client.get("/restaurants/types/stats")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for entry in data:
        assert "type" in entry
        assert "avg_rating" in entry
        assert "count" in entry


def test_get_type_stats_counts(client, seeded_db):
    response = client.get("/restaurants/types/stats")
    data = response.json()
    stats_by_type = {entry["type"]: entry for entry in data}

    assert stats_by_type["Mexican"]["count"] == 2
    assert stats_by_type["Italian"]["count"] == 1
    assert stats_by_type["Japanese"]["count"] == 1
    assert None not in stats_by_type


def test_get_type_stats_avg_rating(client, seeded_db):
    response = client.get("/restaurants/types/stats")
    data = response.json()
    stats_by_type = {entry["type"]: entry for entry in data}

    assert stats_by_type["Mexican"]["avg_rating"] == pytest.approx(4.05, abs=0.01)


def test_get_type_stats_empty_db(client, db_session):
    response = client.get("/restaurants/types/stats")
    assert response.status_code == 200
    assert response.json() == []


# --- GET /restaurants/{id} --------------------------------------------------

def test_get_restaurant_by_id_found(client, seeded_db):
    target = seeded_db[0]  # rest-001
    response = client.get(f"/restaurants/{target.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == target.id
    assert data["name"] == target.name


def test_get_restaurant_by_id_not_found(client):
    response = client.get("/restaurants/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Restaurant with id does-not-exist not found"


def test_get_restaurant_by_id_with_null_fields(client, seeded_db):
    response = client.get("/restaurants/rest-005")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] is None
    assert data["priceLevel"] is None
    assert data["rating"] is None