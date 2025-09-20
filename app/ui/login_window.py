from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import Qt
from core.supa import get_client

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Iniciar sesión")
        self.setModal(True)
        self.resize(380, 220)

        lay = QVBoxLayout(self)
        title = QLabel("<b>Acceso</b>"); title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        self.email = QLineEdit(); self.email.setPlaceholderText("Email")
        self.pwd = QLineEdit(); self.pwd.setPlaceholderText("Contraseña"); self.pwd.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.email); lay.addWidget(self.pwd)

        row = QHBoxLayout()
        self.btn_login = QPushButton("Ingresar")
        self.btn_cancel = QPushButton("Cancelar")
        row.addWidget(self.btn_login); row.addWidget(self.btn_cancel)
        lay.addLayout(row)

        self.msg = QLabel(""); self.msg.setProperty("role", "hint")
        lay.addWidget(self.msg)

        self.btn_login.clicked.connect(self.do_login)
        self.btn_cancel.clicked.connect(self.reject)

        self.user = None
        self.session = None

    def do_login(self):
        email = self.email.text().strip()
        pwd = self.pwd.text().strip()
        if not email or not pwd:
            QMessageBox.warning(self, "Login", "Ingresa email y contraseña.")
            return
        self.btn_login.setDisabled(True)
        self.msg.setText("Verificando credenciales…")
        try:
            supa = get_client()
            res = supa.auth.sign_in_with_password({"email": email, "password": pwd})
            self.session = res.session
            self.user = res.user
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Login", f"Error: {e}")
            self.msg.setText("Verifica tus credenciales.")
            self.btn_login.setDisabled(False)
