from typing import Any, Dict, List

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QStatusBar, QMessageBox, QTableWidget,
    QTableWidgetItem, QStyledItemDelegate, QStyleOptionViewItem
)
from PySide6.QtCore import QThread
from PySide6.QtGui import QColor, QPalette
from pathlib import Path

from app.workers.batch_process_worker import BatchProcessWorker
from app.services.storage import fetch_saved_samples, save_samples


class StatusColorDelegate(QStyledItemDelegate):
    PASS_COLOR = QColor("#0a7a28")
    FAIL_COLOR = QColor("#b00020")

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        palette = QPalette(opt.palette)
        value = str(index.data() or "").strip().lower()
        if value in ("Pass", "Fail"):
            color = self.PASS_COLOR if value == "Pass" else self.FAIL_COLOR
            for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
                palette.setColor(group, QPalette.Text, color)
                palette.setColor(group, QPalette.HighlightedText, color)
        opt.palette = palette
        super().paint(painter, opt, index)


class MainWindow(QMainWindow):
    def __init__(self, user_email: str):
        super().__init__()
        self.setWindowTitle("Pesticides Auto Report")
        self.resize(1100, 680)
        self.user_email = user_email
        self._excel_path: Path | None = None
        self._process_thread: QThread | None = None
        self._process_worker = None
        self._last_samples: List[Any] = []
        self._last_sample_metadata: Dict[str, Dict[str, Any]] = {}
        self._saved_to_db = False
        self._build_ui()
        self._refresh_saved_records()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(18)

        left_container = QVBoxLayout()
        left_container.setSpacing(14)

        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setSpacing(10)

        session_label = QLabel(f"Sesion: {self.user_email}")
        session_label.setProperty("role", "hint")
        header_layout.addWidget(session_label)

        self.edit_batches = QLineEdit()
        self.edit_batches.setPlaceholderText(
            "Ingresa batch numbers separados por espacio (ej: B123 B124 B125)"
        )
        self.edit_batches.textChanged.connect(self._update_process_state)
        header_layout.addWidget(self.edit_batches)

        file_row = QHBoxLayout()
        self.btn_excel = QPushButton("Adjuntar Excel")
        self.btn_excel.clicked.connect(self._pick_excel)
        self.lbl_excel = QLabel("Ningun archivo seleccionado")
        self.lbl_excel.setProperty("role", "hint")
        file_row.addWidget(self.btn_excel)
        file_row.addWidget(self.lbl_excel)
        file_row.addStretch(1)
        header_layout.addLayout(file_row)

        action_row = QHBoxLayout()
        self.btn_procesar = QPushButton("Procesar")
        self.btn_procesar.setDisabled(True)
        self.btn_procesar.clicked.connect(self._start_processing)
        action_row.addWidget(self.btn_procesar)
        action_row.addStretch(1)
        header_layout.addLayout(action_row)

        left_container.addWidget(header_widget)

        self.lbl_summary = QLabel("Sin procesamiento todavia")
        self.lbl_summary.setProperty("role", "hint")
        left_container.addWidget(self.lbl_summary)

        results_title = QLabel("<b>Resultados</b>")
        left_container.addWidget(results_title)

        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["Sample", "Componente", "Estado", "DIL"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setItemDelegateForColumn(2, StatusColorDelegate(self.results_table))
        left_container.addWidget(self.results_table)

        self.btn_export = QPushButton("Generar reportes")
        self.btn_export.setDisabled(True)
        self.btn_export.clicked.connect(self._export_reports)
        left_container.addWidget(self.btn_export)

        left_container.addStretch(1)

        right_container = QVBoxLayout()
        right_container.setSpacing(10)

        right_title = QLabel("<b>Historial guardado</b>")
        right_container.addWidget(right_title)

        self.saved_table = QTableWidget(0, 5)
        self.saved_table.setHorizontalHeaderLabels([
            "Sample", "Batch", "Custom ID", "Nombre", "Creado"
        ])
        self.saved_table.horizontalHeader().setStretchLastSection(True)
        right_container.addWidget(self.saved_table)

        main_layout.addLayout(left_container, stretch=3)
        main_layout.addLayout(right_container, stretch=2)

        self.setStatusBar(QStatusBar(self))

    def _pick_excel(self) -> None:
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

    def _update_process_state(self) -> None:
        has_batches = bool(self.edit_batches.text().strip())
        has_excel = self._excel_path is not None
        self.btn_procesar.setDisabled(not (has_batches and has_excel))

    def _set_processing_controls_enabled(self, enabled: bool) -> None:
        self.btn_excel.setDisabled(not enabled)
        self.edit_batches.setDisabled(not enabled)
        if enabled:
            self._update_process_state()
        else:
            self.btn_procesar.setDisabled(True)

    def _start_processing(self) -> None:
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

    def _on_process_progress(self, msg: str) -> None:
        if msg:
            self.statusBar().showMessage(msg)

    def _on_process_finished(self, ok: bool, payload, err: str) -> None:
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
        sample_count = 0
        samples: List[Any] = []
        sample_metadata: Dict[str, Dict[str, Any]] = {}
        if isinstance(payload, dict):
            display_rows = payload.get("display_rows") or []
            sample_count = payload.get("sample_count") or 0
            samples = payload.get("samples") or []
            sample_metadata = payload.get("sample_metadata") or {}

        self._last_samples = samples
        self._last_sample_metadata = sample_metadata
        self._saved_to_db = False

        self._populate_results_table(display_rows)
        self.lbl_summary.setText(f"Samples procesados: {sample_count}")
        self.btn_export.setDisabled(not samples)
        self._reset_form()

        if sample_count:
            self.statusBar().showMessage(
                f"Procesamiento completado para {sample_count} sample(s).",
                5000,
            )
        else:
            self.statusBar().showMessage("Procesamiento completado.", 5000)

    def _populate_results_table(self, rows: List[Dict[str, Any]]) -> None:
        self.results_table.setRowCount(len(rows))
        for r, data in enumerate(rows):
            sample_val = str(data.get("sample", ""))
            component_val = str(data.get("component", ""))
            status_val = str(data.get("status", ""))
            dil_val = str(data.get("dil", ""))

            self.results_table.setItem(r, 0, QTableWidgetItem(sample_val))
            self.results_table.setItem(r, 1, QTableWidgetItem(component_val))

            status_item = QTableWidgetItem(status_val)
            self.results_table.setItem(r, 2, status_item)

            self.results_table.setItem(r, 3, QTableWidgetItem(dil_val))

        self.results_table.resizeColumnsToContents()

    def _refresh_saved_records(self) -> None:
        try:
            records = fetch_saved_samples(limit=200)
        except Exception as exc:
            self.statusBar().showMessage(f"No se pudo leer el historial: {exc}")
            return

        self.saved_table.setRowCount(len(records))
        for idx, rec in enumerate(records):
            sample = str(rec.get("sample_number", ""))
            batch = str(rec.get("batch_number", ""))
            custom_id = str(rec.get("custom_formatted_id", ""))
            name = str(rec.get("sample_name", ""))
            created = str(rec.get("created_at", ""))

            self.saved_table.setItem(idx, 0, QTableWidgetItem(sample))
            self.saved_table.setItem(idx, 1, QTableWidgetItem(batch))
            self.saved_table.setItem(idx, 2, QTableWidgetItem(custom_id))
            self.saved_table.setItem(idx, 3, QTableWidgetItem(name))
            self.saved_table.setItem(idx, 4, QTableWidgetItem(created))

        self.saved_table.resizeColumnsToContents()

    def _export_reports(self) -> None:
        if not self._last_samples:
            QMessageBox.information(self, "Reportes", "No hay samples disponibles para exportar.")
            return

        from datetime import date
        from app.services import ps_processing

        target_path = Path.cwd() / "Excel reports" / date.today().strftime("%Y%m%d")
        target_path.mkdir(parents=True, exist_ok=True)

        try:
            exported = ps_processing.export_samples_to_directory(self._last_samples, target_path)
        except Exception as exc:
            QMessageBox.critical(self, "Reportes", f"No se pudieron generar los reportes.\n\n{exc}")
            return

        if self._last_sample_metadata and not self._saved_to_db:
            try:
                save_samples(self._last_samples, self._last_sample_metadata)
                self._saved_to_db = True
            except Exception as exc:
                QMessageBox.critical(self, "Reportes", f"No se pudieron guardar los resultados.\n\n{exc}")
                return

        self._refresh_saved_records()

        QMessageBox.information(
            self,
            "Reportes",
            f"Se generaron {len(exported)} reporte(s) en:\n{target_path}"
        )

    def _reset_form(self) -> None:
        self.edit_batches.clear()
        self._excel_path = None
        self.lbl_excel.setText("Ningun archivo seleccionado")
        self._update_process_state()
