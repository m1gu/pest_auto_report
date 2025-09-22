from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import QObject, Signal

from app.services import ps_processing
from app.services.ps_processing import BatchProcessOutput, normalize_sample_id_text
from app.services.storage import save_samples
from core.qbench_client import QBenchClient, QBenchError


class BatchProcessWorker(QObject):
    progressed = Signal(str)
    finished = Signal(bool, object, str)

    def __init__(self, batches: List[str], excel_path: Path):
        super().__init__()
        self.batches = [b.strip() for b in batches if b.strip()]
        self.excel_path = Path(excel_path)

    def _collect_sample_info(self, client: QBenchClient) -> Dict[str, Dict[str, object]]:
        sample_info: Dict[str, Dict[str, object]] = {}
        for batch in self.batches:
            self.progressed.emit(f"Consultando batch {batch} en QBench...")
            if hasattr(client, 'get_batch_samples'):
                rows, debug_msg = client.get_batch_samples(batch)
            else:
                rows, debug_msg = self._fallback_get_batch_samples(client, batch)
            if debug_msg:
                self.progressed.emit(debug_msg)
            for row in rows:
                keys: set[str] = set()
                primary = normalize_sample_id_text(row.get('id'))
                if primary:
                    keys.add(primary)
                custom_id = row.get('custom_formatted_id')
                if custom_id:
                    cf_norm = normalize_sample_id_text(custom_id)
                    if cf_norm:
                        keys.add(cf_norm)
                    if '-' in custom_id:
                        tail_norm = normalize_sample_id_text(custom_id.split('-')[-1])
                        if tail_norm:
                            keys.add(tail_norm)
                info = {
                    'sample_weight': row.get('sample_weight'),
                    'sample_name': row.get('sample_name'),
                    'custom_formatted_id': row.get('custom_formatted_id'),
                    'batch_number': row.get('batch_number') or batch,
                }
                for key in keys:
                    if key and key not in sample_info:
                        sample_info[key] = info
        return sample_info

    def _fallback_get_batch_samples(self, client: QBenchClient, batch_id: str, page_size: int = 100):
        params = {'include': 'samples'}
        try:
            batch_payload = client.get(f"batch/{batch_id}", params=params)
        except QBenchError as exc:
            return [], f"Batch {batch_id}: fallback batch error {exc}"

        extractor = getattr(client, '_extract_sample_ids_from_batch', None)
        if extractor is None:
            return [], f"Batch {batch_id}: fallback sin extractor"

        sample_ids = extractor(batch_payload)
        if page_size:
            sample_ids = sample_ids[:int(page_size)]
        if not sample_ids:
            return [], f"Batch {batch_id}: 0 ids en fallback"

        rows: List[Dict[str, object]] = []
        errors = 0
        sample_rows_helper = getattr(client, '_sample_rows_from_payload', None)

        for sample_id in sample_ids:
            try:
                sample_payload = client.get(f"sample/{sample_id}")
            except QBenchError:
                errors += 1
                continue

            data_section = sample_payload.get('data')
            if isinstance(data_section, dict):
                sample_list = [data_section]
            elif isinstance(data_section, list):
                sample_list = data_section
            else:
                sample_list = [sample_payload]

            if sample_rows_helper:
                rows.extend(sample_rows_helper({'data': sample_list}))
            else:
                for entry in sample_list:
                    if isinstance(entry, dict):
                        rows.append({
                            'id': entry.get('id') or sample_id,
                            'custom_formatted_id': entry.get('custom_formatted_id'),
                            'sample_name': entry.get('sample_name'),
                            'matrix_type': entry.get('matrix_type'),
                            'state': entry.get('state'),
                            'date_created': entry.get('date_created'),
                            'batch_number': entry.get('batch_number') or batch_id,
                            'sample_weight': entry.get('sample_weight'),
                            '_raw': entry,
                        })

        debug_parts = [f"Batch {batch_id}: {len(rows)} samples obtenidos (fallback)", f"ids={len(sample_ids)}"]
        if errors:
            debug_parts.append(f"fallidos={errors}")
        return rows, ' | '.join(debug_parts)

    def run(self) -> None:
        try:
            if not self.batches:
                raise ValueError('No se proporcionaron batches para procesar.')
            if not self.excel_path.exists():
                raise FileNotFoundError(f'Archivo Excel no encontrado: {self.excel_path}')

            client = QBenchClient()
            sample_info = self._collect_sample_info(client)
            if not sample_info:
                raise RuntimeError('QBench no devolvio samples para los batches indicados.')

            self.progressed.emit('Leyendo Excel de resultados...')
            df = ps_processing.read_raw_results_excel(self.excel_path)

            self.progressed.emit('Procesando datos...')
            output: BatchProcessOutput = ps_processing.process_batch_dataframe(df, sample_info)

            debug_entries = []
            for sample in output.samples:
                for result in sample.results:
                    debug_entries.append({
                        'sample': sample.sample,
                        'component': result.component,
                        'mass': sample.mass_mg,
                    })
            debug_path = Path(__file__).resolve().parents[2] / 'debug_mass.json'
            try:
                debug_path.write_text(json.dumps(debug_entries, indent=2, ensure_ascii=False), encoding='utf-8')
            except Exception:
                pass

            if not output.samples:
                raise RuntimeError('No se generaron resultados a partir del Excel proporcionado.')

            self.progressed.emit('Guardando resultados en base de datos...')
            save_samples(output.samples, sample_info)

            payload = {
                'display_rows': output.display_rows,
                'sample_count': len(output.samples),
                'samples': output.samples,
            }
            self.finished.emit(True, payload, '')
        except (QBenchError, ValueError, FileNotFoundError, RuntimeError) as e:
            self.finished.emit(False, None, str(e))
        except Exception as e:
            self.finished.emit(False, None, f'Error inesperado: {e}')
