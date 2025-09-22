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



    def _extract_sample_weight(self, sample: Dict[str, Any], custom_fields: Dict[str, Any]) -> str:
            def normalize(value: Any) -> str:
                if value is None:
                    return ""
                if isinstance(value, (int, float)):
                    if isinstance(value, float) and value != value:  # NaN check
                        return ""
                    text = f"{value}"
                    if text.endswith(".0"):
                        try:
                            if float(text).is_integer():
                                return str(int(float(text)))
                        except ValueError:
                            pass
                    return text
                if isinstance(value, str):
                    text = value.strip()
                    if not text:
                        return ""
                    match = re.search(r"-?\d+(?:[.,]\d+)?", text)
                    if match:
                        return match.group(0).replace(",", "")
                    return text
                try:
                    text = str(value).strip()
                except Exception:
                    return ""
                return text

            tests = sample.get("tests") if isinstance(sample, dict) else None
            if isinstance(tests, list):
                for test in tests:
                    if not isinstance(test, dict):
                        continue
                    assay = test.get("assay") or {}
                    title = str((assay.get("title") or "")).strip().lower()
                    if "pesticide" not in title:
                        continue
                    weight = test.get("sample_weight")
                    normalized = normalize(weight)
                    if normalized:
                        return normalized

            direct_weight = normalize(sample.get("sample_weight") if isinstance(sample, dict) else None)
            if direct_weight:
                return direct_weight

            weight_keys = [
                "sample_weight",
                "Sample Weight",
                "Sample Weight (mg)",
                "Sample Weight (g)",
                "SampleWeight",
                "Sample Mass",
                "Sample mass",
                "Mass (mg)",
                "Mass_mg",
                "Mass",
            ]
            if isinstance(custom_fields, dict):
                for key in weight_keys:
                    if key in custom_fields:
                        normalized = normalize(custom_fields.get(key))
                        if normalized:
                            return normalized
                for key, value in custom_fields.items():
                    if not isinstance(key, str):
                        continue
                    lower_key = key.lower()
                    if "weight" in lower_key and "trip" not in lower_key:
                        normalized = normalize(value)
                        if normalized:
                            return normalized

            return ""


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





