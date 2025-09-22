from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from app.services.ps_processing import ProcessedSample

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'reports.db'


def _ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_number TEXT,
                sample_number TEXT,
                custom_formatted_id TEXT,
                sample_name TEXT,
                dilution_factor REAL,
                mass_mg REAL,
                results_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_samples(samples: Iterable[ProcessedSample], sample_metadata: Mapping[str, dict]) -> None:
    _ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        for sample in samples:
            meta = sample_metadata.get(sample.sample, {})
            custom_id = sample.custom_formatted_id or meta.get('custom_formatted_id')
            sample_name = sample.sample_name or meta.get('sample_name')
            batch_number = sample.batch_number or meta.get('batch_number')
            results_json = json.dumps([
                {
                    'analyte': r.analyte,
                    'component': r.component,
                    'calc_conc': r.calc_conc,
                    'final_result': r.final_result,
                    'status': r.status,
                    'dil': r.dil,
                }
                for r in sample.results
            ])
            conn.execute(
                """
                INSERT INTO reports (
                    batch_number,
                    sample_number,
                    custom_formatted_id,
                    sample_name,
                    dilution_factor,
                    mass_mg,
                    results_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_number,
                    sample.sample,
                    custom_id,
                    sample_name,
                    sample.dilution_factor,
                    sample.mass_mg,
                    results_json,
                ),
            )
        conn.commit()

