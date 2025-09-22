from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt, QThread
from pathlib import Path

from app.workers.qbench_fetch_worker import QBenchFetchWorker
from app.workers.batch_process_worker import BatchProcessWorker
from app.ui.samples_window import SamplesDialog
from app.ui.processed_results_window import ProcessedResultsDialog


class MainWindow(QMainWindow):
    def __init__(self, user_email: str):
        super().__init__()
        self.setWindowTitle("Pesticides Auto Report")
        self.resize(960, 640)
        self.user_email = user_email
        self._excel_path: Path | None = None
        self._process_thread: QThread | None = None
        self._process_worker = None
        self._qb_thread: QThread | None = None
        self._qb_worker = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        header = QLabel(f"Sesion: {self.user_email}")
        header.setProperty("role", "hint")
        layout.addWidget(header)

        title = QLabel("<h2>Pantalla inicial</h2>")
        layout.addWidget(title)

        self.edit_batches = QLineEdit()
        self.edit_batches.setPlaceholderText(
            "Ingresa batch numbers separados por espacio (ej: B123 B124 B125)"
        )
        self.edit_batches.textChanged.connect(self._update_process_state)
        layout.addWidget(self.edit_batches)

        file_row = QHBoxLayout()
        self.btn_excel = QPushButton("Adjuntar Excel")
        self.btn_excel.clicked.connect(self._pick_excel)
        self.lbl_excel = QLabel("Ningun archivo seleccionado")
        self.lbl_excel.setProperty("role", "hint")
        file_row.addWidget(self.btn_excel)
        file_row.addWidget(self.lbl_excel)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        nav = QHBoxLayout()
        self.btn_procesar = QPushButton("Procesar")
        self.btn_procesar.setDisabled(True)
        self.btn_procesar.clicked.connect(self._start_processing)
        self.btn_salir = QPushButton("Cerrar sesion")
        self.btn_salir.clicked.connect(self.close)
        nav.addWidget(self.btn_procesar)
        nav.addStretch(1)
        nav.addWidget(self.btn_salir)
        self.btn_qbench = QPushButton("Buscar en QBench")
        self.btn_qbench.clicked.connect(self._start_qbench_search)
        nav.addWidget(self.btn_qbench)
        layout.addLayout(nav)

        self.setStatusBar(QStatusBar(self))

    def _pick_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona un Excel",
            "",
            "Excel (*.xlsx *.xls)"
        )
        if path:
            self._excel_path = Path(path)
            self.lbl_excel.setText(self._excel_path.name)
        self._update_process_state()

    def _update_process_state(self):
        has_batches = bool(self.edit_batches.text().strip())
        has_excel = self._excel_path is not None
        self.btn_procesar.setDisabled(not (has_batches and has_excel))

    def _set_processing_controls_enabled(self, enabled: bool) -> None:
        self.btn_excel.setDisabled(not enabled)
        self.btn_qbench.setDisabled(not enabled)
        self.edit_batches.setDisabled(not enabled)
        if enabled:
            self._update_process_state()
        else:
            self.btn_procesar.setDisabled(True)

    def _start_processing(self):
        batches_raw = self.edit_batches.text().strip()
        if not batches_raw:
            QMessageBox.warning(self, "Procesamiento", "Ingresa al menos un batch number.")
            return
        if not self._excel_path:
            QMessageBox.warning(self, "Procesamiento", "Adjunta un archivo Excel.")
            return

        batches = [b for b in batches_raw.split() if b.strip()]
        if not batches:
            QMessageBox.warning(self, "Procesamiento", "Ingresa al menos un batch number valido.")
            return

        self.statusBar().showMessage("Iniciando procesamiento...")
        self._set_processing_controls_enabled(False)

        self._process_thread = QThread()
        self._process_worker = BatchProcessWorker(batches, self._excel_path)
        self._process_worker.moveToThread(self._process_thread)
        self._process_worker.progressed.connect(self._on_process_progress)
        self._process_worker.finished.connect(self._on_process_finished)
        self._process_thread.started.connect(self._process_worker.run)
        self._process_thread.start()

    def _on_process_progress(self, msg: str):
        if msg:
            self.statusBar().showMessage(msg)

    def _on_process_finished(self, ok: bool, payload, err: str):
        if self._process_thread:
            self._process_thread.quit()
            self._process_thread.wait()
            self._process_thread = None
        self._process_worker = None
        self._set_processing_controls_enabled(True)

        if not ok:
            QMessageBox.critical(self, "Procesamiento", err or "No fue posible completar el proceso.")
            return

        display_rows = []
        sample_count = None
        if isinstance(payload, dict):
            display_rows = payload.get("display_rows") or []
            sample_count = payload.get("sample_count")

        dlg = ProcessedResultsDialog(display_rows, self, sample_count, samples=payload.get("samples"))
        dlg.exec()
        self._reset_form()
        if sample_count:
            self.statusBar().showMessage(
                f"Procesamiento completado para {sample_count} sample(s).",
                5000,
            )
        else:
            self.statusBar().showMessage("Procesamiento completado.", 5000)

    def _reset_form(self):
        self.edit_batches.clear()
        self._excel_path = None
        self.lbl_excel.setText("Ningun archivo seleccionado")
        self._update_process_state()

    def _start_qbench_search(self):
        batches_raw = self.edit_batches.text().strip()
        if not batches_raw:
            QMessageBox.warning(self, "QBench", "Ingresa al menos un batch number.")
            return
        batches = [b for b in batches_raw.split() if b.strip()]
        self.statusBar().showMessage("Conectando a QBench...")
        self.btn_qbench.setDisabled(True)

        self._qb_thread = QThread()
        self._qb_worker = QBenchFetchWorker(batches)
        self._qb_worker.moveToThread(self._qb_thread)
        self._qb_worker.progressed.connect(self._on_qb_progress)
        self._qb_worker.finished.connect(self._on_qb_finished)
        self._qb_thread.started.connect(self._qb_worker.run)
        self._qb_thread.start()

    def _on_qb_progress(self, msg: str):
        self.statusBar().showMessage(msg)

    def _on_qb_finished(self, ok: bool, df_or_none, err: str):
        if self._qb_thread:
            self._qb_thread.quit()
            self._qb_thread.wait()
            self._qb_thread = None
        self._qb_worker = None
        self.btn_qbench.setDisabled(False)

        if not ok:
            QMessageBox.critical(self, "QBench", f"Fallo la busqueda en QBench.\n\n{err}")
            return

        import pandas as pd

        df = df_or_none if df_or_none is not None else pd.DataFrame()
        try:
            dlg = SamplesDialog(df, self)
            dlg.exec()
        except Exception as exc:
            QMessageBox.critical(self, "QBench", f"No se pudo mostrar la tabla: {exc}")

