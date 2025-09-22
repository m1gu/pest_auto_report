
from __future__ import annotations

from typing import Iterable, Mapping, Sequence
from pathlib import Path
import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QMessageBox,
    QFileDialog,
)


from app.services import ps_processing

class ProcessedResultsDialog(QDialog):
    def __init__(self, rows: Iterable[Mapping[str, str]], parent=None, sample_count: int | None = None, samples: Sequence[ps_processing.ProcessedSample] | None = None):
        super().__init__(parent)
        self.setWindowTitle('Resultados procesados')
        self.resize(820, 520)
        self._samples = list(samples) if samples else []

        layout = QVBoxLayout(self)

        title = QLabel('<b>Muestras procesadas</b>')
        layout.addWidget(title)

        if sample_count is not None:
            summary = QLabel(f'Total de samples: {sample_count}')
            summary.setProperty('role', 'hint')
            layout.addWidget(summary)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['Sample', 'Componente', 'Estado', 'DIL'])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        export_btn = QPushButton('Generar reportes')
        export_btn.clicked.connect(self._on_generate_reports)
        buttons.addWidget(export_btn)
        close_btn = QPushButton('Cerrar')
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        self._export_btn = export_btn
        self._populate(rows)

    def _populate(self, rows: Iterable[Mapping[str, str]]) -> None:
        rows_list = list(rows)
        self.table.setRowCount(len(rows_list))
        for r, data in enumerate(rows_list):
            for c, key in enumerate(('sample', 'component', 'status', 'dil')):
                value = str(data.get(key, ''))
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignCenter if c != 1 else Qt.AlignLeft | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()

    def _on_generate_reports(self) -> None:
        if not self._samples:
            QMessageBox.information(self, 'Reportes', 'No hay samples disponibles para exportar.')
            return

        default_dir = Path.cwd() / 'Excel reports' / datetime.date.today().strftime('%Y%m%d')
        default_dir.mkdir(parents=True, exist_ok=True)
        target_dir = QFileDialog.getExistingDirectory(
            self,
            'Selecciona carpeta de reportes',
            str(default_dir)
        )
        if not target_dir:
            return

        target_path = Path(target_dir)
        try:
            exported = ps_processing.export_samples_to_directory(self._samples, target_path)
        except Exception as exc:
            QMessageBox.critical(self, 'Reportes', f'No se pudieron generar los reportes.\\n\\n{exc}')
            return

        QMessageBox.information(
            self,
            'Reportes',
            f'Se generaron {len(exported)} reporte(s) en:\\n{target_path}'
        )




