import json
from pathlib import Path

from src.build import build_snapshot

SCENARIO_DIR = Path("data/hackathon_data_bundle/asked_at_2025-05-29T21:00:00Z")
SNAPSHOT = "asked_at_2025-05-29T21:00:00Z"
EXPECTED_FLIGHTS = 16687


def test_build_writes_the_three_artifacts(tmp_path):
    build_snapshot(SCENARIO_DIR, out_root=tmp_path)
    out = tmp_path / SNAPSHOT

    assert (out / "flights.json").exists()
    assert (out / "summary.json").exists()
    assert (out / "h3.json").exists()


def test_flights_artifact_has_one_entry_per_flight(tmp_path):
    build_snapshot(SCENARIO_DIR, out_root=tmp_path)
    flights = json.loads((tmp_path / SNAPSHOT / "flights.json").read_text())

    assert len(flights) == EXPECTED_FLIGHTS
    assert flights[0]["fuel_kg"] > 0
    assert "co2_kg" in flights[0]
    assert "aircraft_class" in flights[0]


def test_summary_aggregates_totals(tmp_path):
    summary = build_snapshot(SCENARIO_DIR, out_root=tmp_path)

    assert summary["n_flights"] == EXPECTED_FLIGHTS
    assert summary["total_fuel_kg"] > 0
    assert summary["total_co2_kg"] > summary["total_fuel_kg"]
    assert summary["snapshot"] == SNAPSHOT
