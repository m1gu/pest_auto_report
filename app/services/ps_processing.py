from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import datetime
import re
from openpyxl.utils import get_column_letter

LOQ = 0.1

STATE_LIMITS: Dict[str, float] = {
    "Abamectin": 0.5,
    "Acephate": 0.4,
    "Acequinocyl": 2.0,
    "Acetamiprid": 0.2,
    "Aldicarb": 0.4,
    "Azoxystrobin": 0.2,
    "Bifenazate": 0.2,
    "Bifenthrin": 0.2,
    "Boscalid": 0.4,
    "Carbaryl": 0.2,
    "Carbofuran": 0.2,
    "Chlorantraniliprole": 0.2,
    "Chlorfenapyr": 1.0,
    "Chlorpyrifos": 0.2,
    "Clofentezine": 0.2,
    "Cyfluthrin": 1.0,
    "Cypermethrin": 1.0,
    "Daminozide": 1.0,
    "Diazinon": 0.2,
    "Dichlorvos": 1.0,
    "Dimethoate": 0.2,
    "Ethoprophos": 0.2,
    "Etofenprox": 0.4,
    "Etoxazole": 0.2,
    "Fenoxycarb": 0.2,
    "Fenpyroximate": 0.4,
    "Fipronil": 0.4,
    "Flonicamid": 1.0,
    "Fludioxonil": 0.4,
    "Hexythiazox": 1.0,
    "Imazalil": 0.2,
    "Imidacloprid": 0.4,
    "Kresoxim-methyl": 0.4,
    "Malathion A": 0.2,
    "Metalaxyl": 0.2,
    "Methiocarb": 0.2,
    "Methomyl": 0.4,
    "Methyl parathion": 0.2,
    "MGK 264": 0.2,
    "Myclobutanil": 0.2,
    "Naled": 0.5,
    "Oxamyl": 1.0,
    "Paclobutrazol": 0.4,
    "Permethrins*": 0.2,
    "Phosmet": 0.2,
    "Piperonyl butoxide": 2.0,
    "Prallethrin": 0.2,
    "Propiconazole": 0.4,
    "Propoxure": 0.2,
    "Pyrethrins*": 1.0,
    "Pyridaben": 0.2,
    "Spinosad*": 0.2,
    "Spiromesifen": 0.2,
    "Spirotetramat": 0.2,
    "Spiroxamine": 0.4,
    "Tebuconazole": 0.4,
    "Thiacloprid": 0.2,
    "Thiamethoxam": 0.2,
    "Trifloxystrobin": 0.2,
}

ANALYTES: List[str] = list(STATE_LIMITS.keys())

RAW_SHEET_NAME = "raw results"


@dataclass
class ProcessedAnalyte:
    analyte: str
    component: str
    calc_conc: float
    final_result: str
    status: str
    dil: str


@dataclass
class ProcessedSample:
    sample: str
    batch_number: Optional[str]
    sample_name: Optional[str]
    custom_formatted_id: Optional[str]
    sample_date: Optional[str]
    dilution_factor: Optional[float]
    mass_mg: Optional[float]
    results: List[ProcessedAnalyte]


@dataclass
class BatchProcessOutput:
    samples: List[ProcessedSample]
    display_rows: List[Dict[str, str]]


def normalize_sample_id_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.endswith(".0"):
        try:
            f = float(s)
            if f.is_integer():
                return str(int(f))
        except Exception:
            pass
    try:
        numeric = pd.to_numeric(s, errors="coerce")
        if pd.notna(numeric) and float(numeric).is_integer():
            return str(int(numeric))
    except Exception:
        pass
    return s


def map_component_to_analyte(component_name: str) -> str:
    component_name = (component_name or "").strip()
    return component_name[:-2].strip() if component_name.endswith(" 1") else component_name


def read_raw_results_excel(xlsx_path: Path | str) -> pd.DataFrame:
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el Excel: {path}")

    try:
        df = pd.read_excel(path, sheet_name=RAW_SHEET_NAME, engine="openpyxl")
    except Exception:
        df = pd.read_excel(path, sheet_name=RAW_SHEET_NAME, header=None, engine="openpyxl")

    if df is None or df.empty:
        raise ValueError(f"La hoja '{RAW_SHEET_NAME}' del Excel est? vac?a o no se pudo leer.")

    if df.shape[1] < 6:
        raise ValueError("La hoja debe contener al menos 6 columnas (A..F).")

    norm = pd.DataFrame({
        "sample": df.iloc[:, 0],
        "component": df.iloc[:, 1],
        "calc_conc": df.iloc[:, 3],
        "dilution_factor": df.iloc[:, 4],
        "include": df.iloc[:, 5],
    })

    norm["sample"] = norm["sample"].map(normalize_sample_id_text)
    norm["component"] = norm["component"].astype(str).str.strip()
    norm["calc_conc"] = pd.to_numeric(norm["calc_conc"], errors="coerce")
    norm["dilution_factor"] = pd.to_numeric(norm["dilution_factor"], errors="coerce")
    norm["include"] = norm["include"].astype(str).str.strip().str.upper().isin(["YES", "Y", "TRUE", "1"])

    norm = norm[(norm["sample"] != "") & (norm["component"] != "")]
    return norm


def _format_sigfigs_no_sci(value: float, sig: int = 3) -> str:
    if value == 0 or not math.isfinite(value):
        return "0"
    power = math.floor(math.log10(abs(value)))
    decimals = sig - 1 - power
    rounded = round(value, decimals)
    if decimals > 0:
        s = f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")
        return s or "0"
    return f"{rounded:.0f}"


def _compute_final_result(amount: float, mass_mg: Optional[float], dilution_factor: Optional[float]) -> str:
    if amount is None or math.isnan(amount):
        return "0"
    if amount == 0:
        return "ND"
    if mass_mg is None or not isinstance(mass_mg, (int, float)) or math.isnan(mass_mg) or mass_mg <= 0:
        return "Invalid Mass"
    df_value = dilution_factor
    if df_value is None or (isinstance(df_value, float) and math.isnan(df_value)):
        df_value = 0.0
    result = (amount / mass_mg) * df_value
    if result < LOQ:
        return "ND"
    return _format_sigfigs_no_sci(result, sig=3)


def _status_from_final(analyte: str, final_result: str) -> str:
    if final_result == "ND":
        return "Pass"
    if final_result in ("-", "Invalid Mass", "Invalid Amt", "Error", ""):
        return "-"
    try:
        numeric = float(final_result)
    except ValueError:
        return "Error"
    limit = STATE_LIMITS.get(analyte)
    if limit is None:
        return "-"
    return "Fail" if numeric > limit else "Pass"


def _compute_dilution_recommendation(calc_conc: float) -> str:
    if calc_conc is None or math.isnan(calc_conc) or calc_conc <= 200:
        return "-"
    return str(int(math.ceil(calc_conc / 200)))


def process_batch_dataframe(
    df: pd.DataFrame,
    sample_info: Dict[str, Dict[str, Any]],
) -> BatchProcessOutput:
    df_yes = df[df["include"]].copy()
    if df_yes.empty:
        raise ValueError("El Excel no contiene filas marcadas como YES.")

    display_rows: List[Dict[str, str]] = []
    samples: List[ProcessedSample] = []

    unique_samples: List[str] = list(dict.fromkeys(df_yes["sample"].tolist()))

    for sample_key in unique_samples:
        subset = df_yes[df_yes["sample"] == sample_key].copy()
        if subset.empty:
            continue

        subset["analyte_base"] = subset["component"].astype(str).map(map_component_to_analyte)
        subset = subset.dropna(subset=["calc_conc"])
        subset = subset.drop_duplicates(subset=["analyte_base"], keep="first")
        if subset.empty:
            continue

        info = sample_info.get(sample_key, {})
        mass_value = info.get("sample_weight")
        mass_mg = None
        try:
            if mass_value is not None:
                mass_mg = float(str(mass_value).replace(',', '').strip())
        except Exception:
            mass_mg = None

        dil_series = subset["dilution_factor"].dropna()
        dilution_factor = float(dil_series.iloc[0]) if not dil_series.empty else None

        analyte_results: List[ProcessedAnalyte] = []
        for _, row in subset.iterrows():
            analyte_name = row.get("analyte_base") or ""
            amount = row.get("calc_conc")
            component = row.get("component") or ""
            final_result = _compute_final_result(amount, mass_mg, dilution_factor)
            status = _status_from_final(analyte_name, final_result)
            dil = _compute_dilution_recommendation(amount if amount is not None else float('nan'))

            analyte_results.append(
                ProcessedAnalyte(
                    analyte=analyte_name,
                    component=component,
                    calc_conc=float(amount) if amount is not None and not math.isnan(amount) else 0.0,
                    final_result=final_result,
                    status=status,
                    dil=dil,
                )
            )

            display_rows.append({
                "sample": sample_key,
                "component": component,
                "status": status,
                "dil": dil,
            })

        samples.append(
            ProcessedSample(
                sample=sample_key,
                batch_number=info.get("batch_number"),
                sample_name=info.get("sample_name"),
                custom_formatted_id=info.get("custom_formatted_id"),
                sample_date=info.get("sample_date"),
                dilution_factor=dilution_factor,
                mass_mg=mass_mg,
                results=analyte_results,
            )
        )

    return BatchProcessOutput(samples=samples, display_rows=display_rows)




def _normalize_component_name(name: str) -> str:
    name = (name or '').strip()
    return re.sub(r'\s+\d+$', '', name)


def build_full_analyte_table(sample: ProcessedSample) -> pd.DataFrame:
    existing = { _normalize_component_name(result.component): result for result in sample.results }
    rows: List[Dict[str, Any]] = []
    for analyte in ANALYTES:
        result = existing.get(analyte)
        if result is None:
            rows.append(
                {
                    'Analyte Name': analyte,
                    'Analyte Amount': 0.0,
                    'LOQ': LOQ,
                    'State Limit': STATE_LIMITS.get(analyte, 'N/A'),
                    'Final Result': 'ND',
                    'Status': 'Pass',
                }
            )
            continue

        rows.append(
            {
                'Analyte Name': analyte,
                'Analyte Amount': result.calc_conc,
                'LOQ': LOQ,
                'State Limit': STATE_LIMITS.get(analyte, 'N/A'),
                'Final Result': result.final_result,
                'Status': result.status,
            }
        )
    return pd.DataFrame(rows)

def build_results_dataframe(sample: ProcessedSample) -> pd.DataFrame:
    rows = []
    for result in sample.results:
        loq_value = LOQ
        state_limit = STATE_LIMITS.get(result.analyte)
        rows.append(
            {
                "Analyte Name": result.analyte,
                "Analyte Amount": result.calc_conc,
                "LOQ": loq_value,
                "State Limit": state_limit if state_limit is not None else "N/A",
                "Final Result": result.final_result,
                "Status": result.status,
            }
        )
    return pd.DataFrame(rows)


def export_sample_to_excel(sample: ProcessedSample, output_dir: Path | str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().strftime("%Y%m%d")
    safe_sample = "".join(c for c in str(sample.sample) if c.isalnum() or c in ("_", "-"))
    safe_sample = safe_sample.strip() or "NoSampleNum"
    file_path = output_dir / f"{today}_{safe_sample}_PSQuants.xlsx"

    df_results = build_full_analyte_table(sample)

    dilution_factor = sample.dilution_factor if sample.dilution_factor is not None else 0.0
    mass_in_grams = (sample.mass_mg or 0.0) / 1000.0

    sample_info = {
        "Sample Number:": sample.sample,
        "Sample Name:": sample.sample_name or "",
        "Sample Date:": sample.sample_date or "",
        "Batch Number:": sample.batch_number or "",
        "Dilution Factor:": dilution_factor,
        "Mass (g):": mass_in_grams,
    }

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df_info_keys = pd.DataFrame(list(sample_info.keys()), columns=["Parameter"])
        df_info_vals = pd.DataFrame(list(sample_info.values()), columns=["Value"])
        df_info_keys.to_excel(writer, sheet_name="Sheet1", index=False, header=False, startrow=0, startcol=0)
        df_info_vals.to_excel(writer, sheet_name="Sheet1", index=False, header=False, startrow=0, startcol=1)

        start_row = len(sample_info) + 1
        df_results.to_excel(writer, sheet_name="Sheet1", index=False, startrow=start_row)

        worksheet = writer.sheets["Sheet1"]
        for col_idx, column in enumerate(worksheet.columns, start=1):
            max_length = 0
            for cell in column:
                value = cell.value
                if value is not None:
                    value_len = len(str(value))
                    if value_len > max_length:
                        max_length = value_len
            worksheet.column_dimensions[get_column_letter(col_idx)].width = max_length + 2

    return file_path


def export_samples_to_directory(samples: Iterable[ProcessedSample], output_dir: Path | str) -> List[Path]:
    output_dir = Path(output_dir)
    exported: List[Path] = []
    for sample in samples:
        exported.append(export_sample_to_excel(sample, output_dir))
    return exported

