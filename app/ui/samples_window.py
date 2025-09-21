from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

class SamplesDialog(QDialog):
    def __init__(self, df, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Samples encontrados")
        self.resize(980, 600)

        lay = QVBoxLayout(self)
        title = QLabel("<b>Samples</b>"); lay.addWidget(title)

        self.table = QTableWidget(); lay.addWidget(self.table)

        row = QHBoxLayout(); row.addStretch(1)
        btn = QPushButton("Cerrar"); btn.clicked.connect(self.accept)
        row.addWidget(btn); lay.addLayout(row)

        self._populate(df)

    def _populate(self, df):
        # columnas mostradas
        cols = ["batch_number", "id", "custom_formatted_id", "sample_name", "matrix_type", "state", "date_created"]
        headers = ["Batch", "ID", "Formatted ID", "Sample", "Matrix", "State", "Date created"]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(df))
        for i, row in df.iterrows():
            for j, col in enumerate(cols):
                val = row.get(col, "")
                item = QTableWidgetItem("" if val is None else str(val))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
