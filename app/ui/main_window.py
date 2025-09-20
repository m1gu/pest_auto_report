from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QStatusBar
)
from PySide6.QtCore import Qt
from pathlib import Path

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
        lay.addLayout(nav)

        self.setStatusBar(QStatusBar(self))

    def _pick_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona un Excel", "", "Excel (*.xlsx *.xls)")
        if path:
            self._excel_path = Path(path)
            self.lbl_excel.setText(self._excel_path.name)
