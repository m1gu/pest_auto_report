from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QStatusBar
)
from PySide6.QtCore import Qt
from pathlib import Path
from PySide6.QtCore import Qt, QThread
from app.workers.qbench_fetch_worker import QBenchFetchWorker
from app.ui.samples_window import SamplesDialog

class MainWindow(QMainWindow):
    def __init__(self, user_email: str):
        super().__init__()
        self.setWindowTitle("Pesticides Auto Report")
        self.resize(960, 640)
        self.user_email = user_email
        self._excel_path: Path | None = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        lay = QVBoxLayout(central); lay.setContentsMargins(16,16,16,16); lay.setSpacing(14)

        header = QLabel(f"Sesión: {self.user_email}"); header.setProperty("role", "hint")
        lay.addWidget(header)

        title = QLabel("<h2>Pantalla inicial</h2>"); lay.addWidget(title)

        self.edit_batches = QLineEdit()
        self.edit_batches.setPlaceholderText("Ingresa batch numbers separados por espacio (ej: B123 B124 B125)")
        lay.addWidget(self.edit_batches)

        row = QHBoxLayout()
        self.btn_excel = QPushButton("Adjuntar Excel…")
        self.btn_excel.clicked.connect(self._pick_excel)
        self.lbl_excel = QLabel("Ningún archivo seleccionado"); self.lbl_excel.setProperty("role", "hint")
        row.addWidget(self.btn_excel); row.addWidget(self.lbl_excel); row.addStretch(1)
        lay.addLayout(row)

        nav = QHBoxLayout()
        self.btn_procesar = QPushButton("Procesar (placeholder)")
        self.btn_procesar.setDisabled(True)
        self.btn_salir = QPushButton("Cerrar sesión")
        self.btn_salir.clicked.connect(self.close)
        nav.addWidget(self.btn_procesar); nav.addStretch(1); nav.addWidget(self.btn_salir)
        self.btn_qbench = QPushButton("Buscar en QBench")
        self.btn_qbench.clicked.connect(self._start_qbench_search)
        nav.addWidget(self.btn_qbench)
        lay.addLayout(nav)

        self.setStatusBar(QStatusBar(self))

    def _pick_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona un Excel", "", "Excel (*.xlsx *.xls)")
        if path:
            self._excel_path = Path(path)
            self.lbl_excel.setText(self._excel_path.name)

    def _start_qbench_search(self):
        batches_raw = self.edit_batches.text().strip()
        if not batches_raw:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "QBench", "Ingresa al menos un batch number.")
            return
        batches = [b for b in batches_raw.split() if b.strip()]
        self.statusBar().showMessage("Conectando a QBench…")
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
        self._qb_thread.quit()
        self._qb_thread.wait()
        self._qb_thread = None
        self._qb_worker = None
        self.btn_qbench.setDisabled(False)
        # deja el último progreso visible un par de segundos
        # self.statusBar().clearMessage()

        from PySide6.QtWidgets import QMessageBox
        if not ok:
            QMessageBox.critical(self, "QBench", f"Falló la búsqueda en QBench.\n\n{err}")
            return

        # Si no hay resultados, abre de todos modos para ver columnas vacías;
        # así confirmamos que la llamada funcionó.
        import pandas as pd
        df = df_or_none if df_or_none is not None else pd.DataFrame()
        try:
            from app.ui.samples_window import SamplesDialog
            dlg = SamplesDialog(df, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "QBench", f"No se pudo mostrar la tabla: {e}")

