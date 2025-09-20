import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.ui.login_window import LoginDialog
from app.ui.main_window import MainWindow

def load_qss(app):
    qss = Path(__file__).resolve().parents[1] / "app" / "ui" / "style.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))

def main():
    app = QApplication(sys.argv)
    load_qss(app)

    dlg = LoginDialog()
    if dlg.exec() != dlg.Accepted or not dlg.user:
        sys.exit(0)

    w = MainWindow(user_email=dlg.user.email)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
