# views/monitor_page.py
import os
from PySide6.QtWidgets import QWidget, QVBoxLayout,QMessageBox, QProgressBar, QHBoxLayout, QSizePolicy, QPushButton, QTextEdit,  QSpinBox, QDoubleSpinBox, QLabel, QFileDialog, QToolButton
from PySide6.QtCore import Signal,  Qt, QSize, QTimer
from PySide6.QtGui     import QIcon, QPixmap

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from utils.setting_utils import resource_path, icon_path


def make_button(icon_name, text, slot):
    btn = QToolButton()
    ico = QIcon(str(icon_path(icon_name)))        
    btn.setIcon(ico)
    btn.setIconSize(QSize(48, 48))
    btn.setText(text)
    btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    btn.setAutoRaise(True)
    btn.setStyleSheet("border: none; background: transparent;")
    btn.clicked.connect(slot)
    btn.setFixedSize(QSize(72, 80))
    return btn

class MonitorPage(QWidget):
    back_to_control = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        # Buffers pour le graphe
        self._xs, self._ys = [], []
        # Fichier de log ouvert pendant le test
        self._log_file = None
        self._logging_active = True
        self.metadata = {}
        self.config = {}
        self.file_path = ""
        self._current_cycle = 0  # nombre de cycles finis (selon Arduino)
        self.save_folder = None
        self.skip_data = False
        self.prep_overlay = None
        self.waiting_for_t0 = False

        self._dirty = False
        self._plot_timer = QTimer(self)
        self._plot_timer.setInterval(33)  # ~30 FPS
        self._plot_timer.timeout.connect(self._refresh_plot)
        self._plot_timer.start()


    def set_metadata(self, context: dict):
        """Called before START to configure the page."""
        self.metadata = context["metadata"]
        self.save_folder_path = context["folder"]
        self.file_path = context["file_path"]
        self.config = context.get("config")

        self._current_cycle = 0
        self.skip_data = self.config.get("prep_cycle", False)

        #total = int(self.config.get("cycles"))
        #self.progress.setRange(0, total)
        #self.progress.setValue(0)

        # Par exemple, afficher dans le titre du graphe :
        title = f"{self.metadata['name']} — {self.metadata['date']} — {self.metadata['operator']}"
        self.ax.set_title(title)
        self.canvas.draw()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        header = QHBoxLayout()

        # 2.a) Logo
        logo_lbl = QLabel()
        logo_path = resource_path("assets/swibrace-logo.png")
        pix = QPixmap(str(logo_path))
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaledToHeight(50, Qt.SmoothTransformation))
        header.addWidget(logo_lbl, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        header.addStretch(1)

        # 2.b) Titre
        title = QLabel("Test Bench Controller")
        title.setStyleSheet("font-size: 25px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        # Pour que le label prenne tout l’espace central
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header.addWidget(title)
        header.addStretch(1)

        btn_stop = make_button("stop.png", "Stop", lambda: self.serial.send_raw(b'\xFF'))
        header.addWidget(btn_stop)

        layout.addLayout(header)



        title = QLabel("Real-Time Monitoring")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
          # ─── Barre de progression des cycles ─────────────
        self.progress = QProgressBar()
        # On met un range temporaire, il sera réinitialisé sur START
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        # Matplotlib canvas
        self.figure = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(self.figure)
        self.ax     = self.figure.add_subplot(111)

                # >>> NETTETÉ HiDPI
        try:
            from matplotlib import rcParams
            dpr = self.window().devicePixelRatioF() if self.window() else self.devicePixelRatioF()
            base_dpi = rcParams.get("figure.dpi", self.figure.dpi)
            self.figure.set_dpi(base_dpi * max(1.0, dpr))
        except Exception:
            pass
        
        self.ax.set_xlabel('Distance (mm)')
        self.ax.set_ylabel('Force (N)')
        self.ax.grid(True) 
        self.line, = self.ax.plot([], [], '-', marker='o', markersize=2, linewidth=0.8)
        layout.addWidget(self.canvas)

  

        # Boutons
        btn_layout = QHBoxLayout()
        self.btn_back = QPushButton("Back to Control")
        btn_layout.addWidget(self.btn_back)
  
        layout.addLayout(btn_layout)

        # Connexions
        self.btn_back.clicked.connect(lambda: self.back_to_control.emit())

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.info_label)




    def set_serial(self, serial):
        """Connects data and event reception."""
        self.serial = serial
        serial.event_received.connect(self._on_event)
        serial.line_received.connect(self.log_line)
        serial.data_received.connect(self._on_data)
        

    def _on_event(self, event: str):
        """Start and end of logging session."""
        if event == "START":
            # Choisir où sauvegarder
            path = self.file_path
            try:
                self._log_file = open(path, 'w')
                #self.log.append(f"💾 Fichier ouvert : {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Unable to create file :\n{e}")
                return
            # Clear ancien graphe
            self.clear()
            # Initialise la barre avec le nombre total de cycles
            total = int(self.config.get("cycles"))
            self.progress.setRange(0, total)
            self.progress.setValue(0)
            # le reste de ta logique START…
        elif event in ("END", "IDLE"):
            if self._log_file:
                self._log_file.close()
                #self.log.append("✅ Fichier TXT fermé et sauvegardé")
                self._log_file = None
                self.clear()

    def _on_data(self, t, d, f):
        if self.skip_data:
            self.show_prep_overlay()
            return  # On ignore toutes les données jusqu’à fin du cycle 1
        
        if self.waiting_for_t0:
            if round(t, 2) == 0.0:
                self.waiting_for_t0 = False  # Start logging after this
            else:
                return

        self.info_label.setText("")  # Efface le message une fois actif

        self._xs.append(d); self._ys.append(f)
        self._dirty = True
        if self._log_file:
            self._log_file.write(f"{t:.2f}\t{d:.2f}\t{f:.2f}\n")

    def _refresh_plot(self):
        if not self._dirty:
            return
        self.line.set_data(self._xs, self._ys)
        # autoscale less often:
        if len(self._xs) % 50 == 0:
            self.ax.relim(); self.ax.autoscale_view()
        self.canvas.draw_idle()
        self._dirty = False       

    def log_line(self, line_: str):
        line = line_.strip()

        if line.startswith("Cycle finished:"):
            try:
                count = int(line.split(":", 1)[1].strip())
                self._current_cycle = count

                # On arrête d'ignorer les données après le premier cycle
                if self.skip_data and count >= 1:
                    self.skip_data = False
                    self.hide_prep_overlay()
                    self.clear() 
                    self.waiting_for_t0 = True
                self.progress.setValue(count)

            except ValueError:
                print("[⚠️] parsing error")

    def clear(self):
        """“Graphics buffer, buffers, and text log."""
        self._xs.clear(); self._ys.clear()
        self.line.set_data([], [])
        self.ax.relim(); self.ax.autoscale_view()
        self.canvas.draw()
        self._current_cycle = 0

        #self.log.clear()

    def show_prep_overlay(self):
        if self.prep_overlay is None:
            self.prep_overlay = QLabel("⏳ Preparation cycle in progress...", self)
            self.prep_overlay.setStyleSheet("""
                background-color: rgba(0, 0, 0, 160);
                color: white;
                font-size: 22px;
                padding: 15px;
                border-radius: 10px;
            """)
            self.prep_overlay.setAlignment(Qt.AlignCenter)
            self.prep_overlay.setFixedSize(400, 80)
            self.prep_overlay.move(
                (self.width() - self.prep_overlay.width()) // 2,
                (self.height() - self.prep_overlay.height()) // 2
            )
            self.prep_overlay.show()

    def hide_prep_overlay(self):
        if self.prep_overlay:
            self.prep_overlay.hide()
            self.prep_overlay.deleteLater()
            self.prep_overlay = None
