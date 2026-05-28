"""
DataSentinel Ingestion Unit Tests.
Verifies CityBikes null preservation and transforming raw JSON structures.
"""
from ingestion.citybikes import build_rows


def test_null_free_bikes_preserved():
    """Critical: null must NOT become 0, ensuring high data quality for statistical models."""
    stations = [{
        "id": "test-shibuya-01",
        "name": "Test Shibuya Station",
        "latitude": 35.6580,
        "longitude": 139.7016,
        # 'free_bikes' and 'empty_slots' keys are missing
    }]
    rows = build_rows(stations)
    assert len(rows) == 1
    assert rows[0]["station_id"] == "test-shibuya-01"
    assert rows[0]["free_bikes"] is None  # NOT 0
    assert rows[0]["empty_slots"] is None  # NOT 0


def test_all_fields_present():
    """Verifies that all transformed rows match the strict BigQuery schema requirements."""
    stations = [{
        "id": "test-shinjuku-02",
        "name": "Test Shinjuku Station",
        "free_bikes": 8,
        "empty_slots": 12,
        "latitude": 35.6895,
        "longitude": 139.6917
    }]
    rows = build_rows(stations)
    assert len(rows) == 1
    assert rows[0]["station_id"] == "test-shinjuku-02"
    assert rows[0]["name"] == "Test Shinjuku Station"
    assert rows[0]["free_bikes"] == 8
    assert rows[0]["empty_slots"] == 12
    assert rows[0]["latitude"] == 35.6895
    assert rows[0]["longitude"] == 139.6917
    assert "ingested_at" in rows[0]
