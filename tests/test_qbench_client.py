import pytest

from core.qbench_client import QBenchClient


@pytest.fixture
def qbench_client():
    client = object.__new__(QBenchClient)
    client._debug_sample_dumped = True
    return client


def test_extract_sample_weight_prefers_pesticide_assay(qbench_client):
    sample = {
        "tests": [
            {"assay": {"title": "Moisture"}, "sample_weight": 3},
            {"assay": {"title": "Pesticide Residue"}, "sample_weight": 12.5},
        ]
    }

    assert qbench_client._extract_sample_weight(sample, {}) == "12.5"


def test_extract_sample_weight_uses_direct_field(qbench_client):
    sample = {"sample_weight": " 23 g"}

    assert qbench_client._extract_sample_weight(sample, {}) == "23"


def test_extract_sample_weight_from_custom_fields(qbench_client):
    sample = {}
    custom_fields = {"Mass (mg)": "12,345 mg"}

    assert qbench_client._extract_sample_weight(sample, custom_fields) == "12345"


def test_extract_sample_ids_from_batch_merges_sources(qbench_client):
    payload = {
        "data": {
            "sample_ids": [1, "002", 3],
            "samples": [
                {"id": "005"},
                {"sample_id": 6},
                {"sample": "007"},
            ],
            "relationships": {
                "samples": {"data": [{"id": "005"}, {"id": "008"}]}
            },
            "included": [
                {"type": "sample", "id": "009"},
                {"type": "other", "id": "ignored"},
            ],
        }
    }

    ids = qbench_client._extract_sample_ids_from_batch(payload)

    assert ids == ["1", "002", "3", "005", "6", "007", "008", "009"]


def test_sample_rows_from_payload_formats_output(qbench_client):
    sample = {
        "id": "S-1",
        "custom_formatted_id": "CF-1",
        "sample_name": "Sample 1",
        "matrix_type": "Flower",
        "state": "complete",
        "date_created": "2024-01-01",
        "custom_fields": {"Batch": "B-99", "Sample Weight": " 1.5 g"},
    }

    rows = qbench_client._sample_rows_from_payload({"data": [sample]})

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "S-1"
    assert row["batch_number"] == "B-99"
    assert row["sample_weight"] == "1.5"
    assert row["_raw"] == sample
