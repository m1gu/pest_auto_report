from __future__ import annotations

import json
from typing import Iterable, Mapping, List, Dict, Any

from app.services.ps_processing import ProcessedSample
from core.supa import get_client

TABLE_NAME = "ps_reports"


def _build_results_json(sample: ProcessedSample) -> str:
    return json.dumps(
        [
            {
                "analyte": r.analyte,
                "component": r.component,
                "calc_conc": r.calc_conc,
                "final_result": r.final_result,
                "status": r.status,
                "dil": r.dil,
            }
            for r in sample.results
        ]
    )


def save_samples(samples: Iterable[ProcessedSample], sample_metadata: Mapping[str, dict]) -> None:
    rows: List[Dict[str, Any]] = []
    client = get_client()

    for sample in samples:
        meta = sample_metadata.get(sample.sample, {})
        payload = {
            "batch_number": sample.batch_number or meta.get("batch_number"),
            "sample_number": sample.sample,
            "custom_formatted_id": sample.custom_formatted_id or meta.get("custom_formatted_id"),
            "sample_name": sample.sample_name or meta.get("sample_name"),
            "dilution_factor": sample.dilution_factor,
            "mass_mg": sample.mass_mg,
            "results_json": _build_results_json(sample),
            "sample_date": sample.sample_date or meta.get("sample_date"),
            "client_name": meta.get("client_name"),
            "processed_by": meta.get("processed_by"),
        }
        rows.append(payload)

    if not rows:
        return

    response = client.table(TABLE_NAME).insert(rows).execute()
    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(f"Supabase insert error: {error}")


def fetch_saved_samples(limit: int = 50) -> List[Dict[str, Any]]:
    client = get_client()
    response = (
        client.table(TABLE_NAME)
        .select("batch_number, sample_number, custom_formatted_id, sample_name, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    error = getattr(response, "error", None)
    if error:
        raise RuntimeError(f"Supabase select error: {error}")

    data = getattr(response, "data", None)
    if data is None:
        return []
    return list(data)
