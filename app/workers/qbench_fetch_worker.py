from PySide6.QtCore import QObject, Signal
import pandas as pd
from core.qbench_client import QBenchClient, QBenchError

class QBenchFetchWorker(QObject):
    progressed = Signal(str)
    # ok, dataframe (o None), error_text (o "")
    finished   = Signal(bool, object, str)

    def __init__(self, batches: list[str]):
        super().__init__()
        self.batches = [b.strip() for b in batches if b.strip()]

    def _progress(self, msg: str):
        self.progressed.emit(msg)

    def run(self):
        try:
            client = QBenchClient()
            all_rows = []
            for b in self.batches:
                self._progress(f"Buscando samples para batch: {b}…")
                rows, debug_msg = client.get_batch_samples(b)
                self._progress(debug_msg or f"  encontrados: {len(rows)}")
                all_rows.extend(rows)

            df = pd.DataFrame(all_rows)
            self.finished.emit(True, df, "")

        except QBenchError as e:
            self._progress(f"❌ QBench error: {e}")
            self.finished.emit(False, None, f"QBench error: {e}")
        except Exception as e:
            self._progress(f"❌ Error: {e}")
            self.finished.emit(False, None, str(e))
