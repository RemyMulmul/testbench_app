from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QSizePolicy, QSpacerItem, QFormLayout, QMessageBox, QToolButton
)
from PySide6.QtCore    import Signal, Qt, QTimer, QSize
from PySide6.QtGui     import QPixmap, QFont, QIcon
from serial.tools       import list_ports
from utils.setting_utils import get_app_root
import os


class PortSelectionPage(QWidget):
    connected = Signal(str)
    analysis_requested = Signal()


    def __init__(self, serial_handler, settings):
        super().__init__()
        self.settings = settings
        self.serial = serial_handler
        self._build_ui()
        self._refresh_ports()

        # Timer pour le timeout READY
        self._handshake_timer = QTimer(self)
        self._handshake_timer.setSingleShot(True)
        self._handshake_timer.timeout.connect(self._on_handshake_timeout)

        self.serial.line_received.connect(self._on_line_received)

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(40, 5, 40, 40)
        main.setSpacing(20)

        # --- Header logo + titre ---
        top = QHBoxLayout()
        logo = QLabel()
        logo_rel_path = self.settings["default_paths"].get("logo_path")
        logo_path = os.path.join(get_app_root(), logo_rel_path)
        pix = QPixmap(logo_path)

    
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(60, Qt.SmoothTransformation))
        top.addWidget(logo, alignment=Qt.AlignLeft)
        
        icons_dir = self.settings.get("default_paths", {}).get("icons_dir")
        icon_name = self.settings.get("default_paths", {}).get("ico_analyse")
        icon_path = os.path.join(os.path.dirname(__file__), "..", icons_dir, icon_name)
        self.btn_analysis  = make_button(icon_path, "Analysis",  self.analysis_requested.emit)

        title = QLabel("Test Bench Controller")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        top.addSpacerItem(QSpacerItem(20,20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        top.addWidget(title, alignment=Qt.AlignCenter)
        top.addSpacerItem(QSpacerItem(20,20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        top.addWidget(self.btn_analysis, alignment=Qt.AlignRight)

        main.addLayout(top)

        # --- Cadre blanc ---
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #fffaf5; border-radius: 8px; border: 1px solid #ccc; }"
        )
        f_layout = QVBoxLayout(frame)
        f_layout.setContentsMargins(20, 60, 20, 20)
        f_layout.setSpacing(15)

        # --- Création de la combo de ports ---
        self.combo = QComboBox()
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo.setFont(QFont("Arial", 14))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        lbl = QLabel("Arduino port:")
        lbl.setFont(QFont("Arial", 14))
        form.addRow(lbl, self.combo)
        f_layout.addLayout(form)

        # --- Boutons Refresh / Connect ---
        btns = QHBoxLayout()
        btns.setSpacing(10)

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btns.addWidget(self.btn_refresh)

        self.btn_connect = QPushButton("🔌 Connect")
        self.btn_connect.setEnabled(False)
        self.btn_connect.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btns.addWidget(self.btn_connect)

        f_layout.addLayout(btns)
        main.addWidget(frame)

        # --- Version en bas ---
        version_str = self.settings.get("version")
        version = QLabel(version_str)
        version.setAlignment(Qt.AlignRight)
        version.setStyleSheet("color: #888; font-size: 10px;")
        main.addWidget(version)

        # --- Connexions UI ---
        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.combo.currentIndexChanged.connect(
            lambda i: self.btn_connect.setEnabled(i >= 0)
        )
        self.btn_connect.clicked.connect(self._attempt_connect)

    def _refresh_ports(self):
        """Reloads the list of available ports."""
        self.combo.clear()
        ports = [p.device for p in list_ports.comports()]
        if not ports:
            ports = ["(aucun port détecté)"]
        self.combo.addItems(ports)
        self.combo.setCurrentIndex(len(ports) - 1)


    def _attempt_connect(self):
        port = self.combo.currentText()
        try:
            self.serial.open(port)
        except Exception as e:
            self.serial.stop()
            QMessageBox.critical(self, "Error", f"Unable to open {port} :\n{e}")
            return

        # Désactive les boutons pour éviter de re-cliquer
        self.btn_connect.setEnabled(False)
        self.btn_refresh.setEnabled(False)

        # Lance le timeout READY
        self._handshake_timer.start(4000)

    def _on_line_received(self, line: str):
        if line.strip() == "READY" and self._handshake_timer.isActive():
            self._handshake_timer.stop()
            QMessageBox.information(self, "success", "Arduino ready!")
            self.connected.emit(self.combo.currentText())

    def _on_handshake_timeout(self):
        QMessageBox.warning(self, "Timeout", "No ‘READY’ response received within 4 seconds")
        try:
            if self.serial.ser and self.serial.ser.is_open:
                self.serial.ser.close()
        except Exception:
            pass
        # Réactive les boutons
        self.btn_connect.setEnabled(True)
        self.btn_refresh.setEnabled(True)

def make_button(icon_path, text, slot):
        btn = QToolButton()
        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(48, 48))               
        btn.setText(text)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setAutoRaise(True)                     
        btn.setStyleSheet("border: none; background: transparent;")
        btn.clicked.connect(slot)
        btn.setFixedSize(QSize(72, 80))
        return btn