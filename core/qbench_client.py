import time
import re
import json
import jwt
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path

from .config import (
    QBENCH_BASE_URL, QBENCH_CLIENT_ID, QBENCH_CLIENT_SECRET,
    QBENCH_JWT_LEEWAY_S, QBENCH_JWT_TTL_S
)

class QBenchError(RuntimeError):
    pass

class QBenchClient:
    def __init__(self):
        if not (QBENCH_BASE_URL and QBENCH_CLIENT_ID and QBENCH_CLIENT_SECRET):
            raise QBenchError("Faltan variables QBENCH_* en .env")
        self.base = QBENCH_BASE_URL
        self._token_exp = 0.0
        self.auth_header = {"content_type": "application/json", "Authorization": ""}
        self._debug_sample_dumped = False

    # ---------- Auth ----------
    def _is_token_expired(self) -> bool:
        return (not self.auth_header.get("Authorization")) or (time.time() >= self._token_exp)

    def authenticate(self) -> bool:
        try:
            now = time.time()
            iat = now - QBENCH_JWT_LEEWAY_S          # p.ej. 5s
            # Garantiza estrictamente < 3600s entre exp e iat (dejamos margen holgado)
            exp = iat + min(QBENCH_JWT_TTL_S, 3300)  # p.ej. 3300s (~55 min)

            assertion = jwt.encode(
                {"iat": iat, "exp": exp, "sub": QBENCH_CLIENT_ID},
                QBENCH_CLIENT_SECRET,
                algorithm="HS256",
            )
            url = f"{self.base}/qbench/oauth2/v1/token"
            data = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}

            r = requests.post(url, data=data, timeout=30)
            # si el status es 4xx/5xx, que salte excepción con el body
            try:
                r.raise_for_status()
            except requests.HTTPError as he:
                raise QBenchError(f"Auth HTTP {r.status_code}: {r.text}") from he

            payload = r.json()
            if payload.get("error"):
                # QBench devuelve error con descripción
                msg = payload.get("error_description") or payload.get("error") or "desconocido"
                self.auth_header["Authorization"] = ""
                self._token_exp = 0.0
                raise QBenchError(f"Auth error: {msg}")

            token = payload.get("access_token")
            if not token:
                self.auth_header["Authorization"] = ""
                self._token_exp = 0.0
                raise QBenchError("Auth: no se recibió access_token")

            self.auth_header["Authorization"] = f"Bearer {token}"
            self._token_exp = exp
            return True

        except requests.RequestException as e:
            self.auth_header["Authorization"] = ""
            self._token_exp = 0.0
            raise QBenchError(f"Auth request failed: {e}") from e

    # ---------- Request base con reintentos ----------
    def _request(self, method, path: str, *, params=None, json=None, data=None,
                 tries=5, delay=1.0, backoff=2.0) -> requests.Response:
        url = f"{self.base}/qbench/api/v1/{path.lstrip('/')}"
        attempt = 0
        while attempt < tries:
            attempt += 1
            if self._is_token_expired():
                # si no autentica, elevamos con el motivo real
                self.authenticate()

            try:
                req_kwargs = {
                    "headers": self.auth_header,
                    "timeout": 30,
                }
                if params is not None:
                    req_kwargs["params"] = params
                if json is not None:
                    req_kwargs["json"] = json
                if data is not None:
                    req_kwargs["data"] = data

                resp = method(url, **req_kwargs)
                if resp.status_code == 429:
                    ttl = resp.headers.get("X-QBAPI-Throttle-TTL")
                    sleep_s = int(ttl) + 1 if ttl else delay
                    time.sleep(sleep_s); delay *= backoff; continue

                if resp.status_code == 401:
                    # token inválido o vencido: fuerza re-auth
                    self.auth_header["Authorization"] = ""
                    self._token_exp = 0.0
                    time.sleep(delay); delay *= backoff; continue

                resp.raise_for_status()
                return resp

            except requests.Timeout:
                time.sleep(delay); delay *= backoff
            except requests.RequestException as e:
                if attempt == tries:
                    raise QBenchError(f"Solicitud falló: {e}") from e
                time.sleep(delay); delay *= backoff

        raise QBenchError(f"Fallo tras {tries} intentos: {url}")

    def get(self, endpoint: str, params=None) -> Dict[str, Any]:
        return self._request(requests.get, endpoint, params=params).json()
    
    def _sample_rows_from_payload(self, payload):
        data = payload.get("data", [])
        rows = []
        for s in data:
            self._maybe_dump_sample(s)
            cf = (s.get("custom_fields") or {}) or (s.get("fields") or {})
            weight = self._extract_sample_weight(s, cf)
            batch_detected = (
                s.get("batch_number")
                or cf.get("Batch")
                or cf.get("batch")
                or cf.get("Batch #")
                or cf.get("Lote")
                or cf.get("Lot")
                or ""
            )
            rows.append({
                "id": s.get("id"),
                "custom_formatted_id": s.get("custom_formatted_id"),
                "sample_name": s.get("sample_name"),
                "matrix_type": s.get("matrix_type"),
                "state": s.get("state"),
                "date_created": s.get("date_created"),
                "batch_number": batch_detected or "",
                "sample_weight": weight,
                "_raw": s,  # para debug opcional
            })
        return rows

    def _maybe_dump_sample(self, sample: Dict[str, Any]) -> None:
        if self._debug_sample_dumped:
            return
        try:
            out_path = Path(__file__).resolve().parents[1] / "debug_sample.json"
            with out_path.open("w", encoding="utf-8") as fh:
                json.dump(sample, fh, indent=2)
        except Exception:
            return
        else:
            self._debug_sample_dumped = True


    def _extract_sample_weight(self, sample: Dict[str, Any], custom_fields: Dict[str, Any]) -> Any:
        preferred_keys = (
            'sample_weight',
            'Sample_weight',
            'Sample_weight_mg',
            'Sample_weight_200mg',
            'Sample_weight_20mg',
            'Weight_mg',
            'Trip_Weight_mg',
            'Dup_weight_mg',
            'Weight_g',
            'Trip_Weight_g',
            'Dup_weight_g',
        )

        def normalize_output(value: Any) -> Any:
            if value is None:
                return ''
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, (dict, list)):
                return ''
            text = str(value).strip()
            return text

        def parse_float(value: Any) -> Optional[float]:
            if isinstance(value, (int, float)):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
            try:
                return float(str(value).replace(',', '').strip())
            except Exception:
                return None

        def test_priority(test: Dict[str, Any]) -> int:
            assay = test.get('assay') or {}
            label = str(assay.get('label_abbr') or '').lower()
            name = str(assay.get('name') or '').lower()
            if 'pest' in name or label == 'ps' or 'pest' in label:
                return 2
            return 0

        def state_bonus(test: Dict[str, Any]) -> int:
            state = str(test.get('state') or '').lower()
            return 1 if state == 'completed' else 0

        tests = sample.get('tests') if isinstance(sample, dict) else None
        candidate_weights = []
        if isinstance(tests, list):
            for order, test in enumerate(tests):
                if not isinstance(test, dict):
                    continue
                priority = test_priority(test)
                bonus = state_bonus(test)
                for key in preferred_keys:
                    if key not in test:
                        continue
                    raw_value = test.get(key)
                    normalized = normalize_output(raw_value)
                    if normalized == '':
                        continue
                    numeric = parse_float(normalized)
                    closeness = abs((numeric or 0.0) - 500.0) if numeric is not None else float('inf')
                    candidate_weights.append((
                        -priority,
                        -bonus,
                        closeness,
                        order,
                        normalized,
                    ))
                worksheet = test.get('worksheet_data')
                if isinstance(worksheet, dict):
                    for key, value in worksheet.items():
                        normalized = normalize_output(value)
                        if normalized == '':
                            continue
                        numeric = parse_float(normalized)
                        closeness = abs((numeric or 0.0) - 500.0) if numeric is not None else float('inf')
                        candidate_weights.append((
                            -priority,
                            -bonus,
                            closeness,
                            order,
                            normalized,
                        ))
        if candidate_weights:
            candidate_weights.sort()
            return candidate_weights[0][-1]

        def search_container(container: Dict[str, Any] | None) -> Any:
            if not isinstance(container, dict):
                return ''
            for key, value in container.items():
                if not isinstance(key, str):
                    continue
                lower = key.lower()
                if 'weight' in lower or 'peso' in lower:
                    normalized = normalize_output(value)
                    if normalized != '':
                        return normalized
            return ''

        for container in (
            custom_fields,
            sample.get('custom_fields') if isinstance(sample, dict) else None,
            sample.get('fields') if isinstance(sample, dict) else None,
            sample,
        ):
            result = search_container(container)
            if result != '':
                return result

        return ''
    def _extract_sample_ids_from_batch(self, payload: Dict[str, Any]) -> List[str]:
        ids: List[str] = []
        seen = set()

        def add(candidate: Any) -> None:
            if isinstance(candidate, (int, float)):
                candidate_str = str(int(candidate))
            else:
                candidate_str = str(candidate).strip() if candidate is not None else ""
            if not candidate_str:
                return
            if candidate_str not in seen:
                seen.add(candidate_str)
                ids.append(candidate_str)

        if not isinstance(payload, dict):
            return ids

        data_section = payload.get("data")
        if isinstance(data_section, dict):
            payload = data_section

        for key in ("sample_ids", "sample_ids_ordered"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    add(item)

        for key in ("samples", "sample_records", "sample_list"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, (str, int, float)):
                        add(item)
                    elif isinstance(item, dict):
                        if "id" in item:
                            add(item.get("id"))
                        elif "sample_id" in item:
                            add(item.get("sample_id"))
                        elif "sample" in item:
                            add(item.get("sample"))

        relationships = payload.get("relationships")
        if isinstance(relationships, dict):
            rel_samples = relationships.get("samples") or relationships.get("sample")
            if isinstance(rel_samples, dict):
                rel_data = rel_samples.get("data")
                if isinstance(rel_data, list):
                    for entry in rel_data:
                        if isinstance(entry, dict) and "id" in entry:
                            add(entry.get("id"))

        included = payload.get("included")
        if isinstance(included, list):
            for entry in included:
                if isinstance(entry, dict) and entry.get("type") in ("sample", "samples"):
                    if "id" in entry:
                        add(entry.get("id"))

        return ids

    def search_samples_by_batch(self, batch_number: str, page_size: int = 200):
        """
        Estrategia:
          A) Intentar SIN 'search' (compatible con tu script).
          B) Filtrar en cliente por batch en campos conocidos.
          C) (Opcional) Intentar con 'search'; si 400, ignorarlo y quedarnos con A.
        Retorna: (rows_filtradas, debug_msg)
        """
        # --- A) petición sin 'search' (como tu script que funciona) ---
        params = {
            "page_size": page_size,
            "page_num": 1,
            "sort_by": "date_created",
            "sort_order": "desc",
        }
        payload = self.get("sample", params=params)
        rows = self._sample_rows_from_payload(payload)
        dbg = [f"GET /sample sin search → {len(rows)} items"]

        # Filtrado en cliente por coincidencia de texto
        # Ajusta aquí el criterio exacto que te sirva:
        bn = str(batch_number).strip()
        matches = []
        for r in rows:
            bucket = " ".join([
                str(r.get("batch_number", "")),
                str(r.get("custom_formatted_id", "")),
                str(r.get("sample_name", "")),
            ])
            if bn and bn in bucket:
                matches.append(r)

        debug_msg = " | ".join(dbg) + f" | matches={len(matches)}"
        return matches, debug_msg

    def get_batch_samples(self, batch_id: str, page_size: int = 100):
        """Obtiene los samples asociados a un batch consultando el endpoint de batches y luego cada sample."""
        if not batch_id:
            return [], "Batch vacio"

        params = {
            "include": "samples",
        }
        batch_payload = self.get(f"batch/{batch_id}", params=params)
        sample_ids = self._extract_sample_ids_from_batch(batch_payload)
        if page_size:
            sample_ids = sample_ids[:int(page_size)]

        if not sample_ids:
            return [], f"Batch {batch_id}: 0 samples referenciados"

        rows: List[Dict[str, Any]] = []
        errors: List[str] = []

        for sample_id in sample_ids:
            try:
                sample_payload = self.get(f"sample/{sample_id}")
            except QBenchError as exc:
                errors.append(f"{sample_id}: {exc}")
                continue

            data_section = sample_payload.get("data")
            if isinstance(data_section, dict):
                sample_list = [data_section]
            elif isinstance(data_section, list):
                sample_list = data_section
            elif isinstance(sample_payload, dict):
                sample_list = [sample_payload]
            else:
                continue

            parsed_rows = self._sample_rows_from_payload({"data": sample_list})
            for parsed in parsed_rows:
                cleaned = parsed.copy()
                cleaned.pop("_raw", None)
                rows.append(cleaned)

        debug_parts = [f"Batch {batch_id}: {len(rows)} samples obtenidos", f"ids={len(sample_ids)}"]
        if errors:
            debug_parts.append(f"fallidos={len(errors)}")
        return rows, " | ".join(debug_parts)





