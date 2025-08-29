from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QHBoxLayout, QGroupBox, QCheckBox, QFormLayout,QGridLayout, QComboBox, 
    QSpinBox, QDoubleSpinBox, QTextEdit, QMessageBox,QDateEdit, QToolButton, 
    QSizePolicy, QDialog, QDialogButtonBox 
)
from PySide6.QtCore import Signal, QObject, QDate, Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
import json  
import os
from functools import partial
from controllers.serial_handler import SerialHandler
from utils.config_saver import*
from pathlib import Path
from utils.setting_utils import (
    get_path_from_settings, icons_dir, icon_path, get_app_root
)


class ControlPanelPage(QWidget):
    start_test = Signal(dict)
    analysis_requested = Signal()    
    view_monitor      = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._reading_weight = False          
        self.metadata = {}
        self.config= {}
        self._build_ui()
        self._on_mode_changed()

    def _build_ui(self):
        def make_button(icon_name_or_rel: str, text, slot):
            btn = QToolButton()
            ico_path = icon_path(icon_name_or_rel, self.settings)
            btn.setIcon(QIcon(str(ico_path)))
            btn.setIconSize(QSize(48, 48))
            btn.setText(text)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setAutoRaise(True)
            btn.setStyleSheet("border: none; background: transparent;")
            btn.clicked.connect(slot)
            btn.setFixedSize(QSize(72, 80))
            return btn
        
        layout = QVBoxLayout(self)
        # ——— Header with logo + title ——————————————————————————
        header = QHBoxLayout()

        # 2.a) Logo
        logo_lbl = QLabel()
        logo_path = get_path_from_settings("logo_path", self.settings, default="assets/swibrace-logo.png")
        pix = QPixmap(logo_path)
        if not pix.isNull():
            logo_lbl.setPixmap(pix.scaledToHeight(50, Qt.SmoothTransformation))
        header.addWidget(logo_lbl, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        header.addStretch(1)

        # 2.b) Title
        title = QLabel("Test Bench Controller")
        title.setStyleSheet("font-size: 25px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        # Pour que le label prenne tout l’espace central
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header.addWidget(title)
        header.addStretch(1)

         # Boutons à droite
        self.btn_play = make_button("play.png", "Start",  self._start_test)
        self.btn_play.setEnabled(False)    # désactivé tant que _update_start_button_state() ne l'active pas

        self.btn_stop = make_button("stop.png", "Stop",      lambda: self.serial.send_raw(b'\xFF'))
        self.btn_ana  = make_button("Analysing.png", "Analysis",  self.analysis_requested.emit)

        header.addWidget(self.btn_play)
        header.addWidget(self.btn_stop)
        header.addWidget(self.btn_ana)

        # 2.f) Ajoute le header au layout
        layout.addLayout(header)

         # ——— Métadonnées du test —————————————————————
        grp = QGroupBox("Test Informations")
        grid = QGridLayout()

        self.input_name_test     = QLineEdit()
        self.input_date     = QDateEdit(QDate.currentDate()); self.input_date.setCalendarPopup(True)
        self.input_operator = QLineEdit()
        self.input_reference = QLineEdit()
        self.input_splint = QLineEdit()
        self.input_note = QLineEdit()
        self.combo_motion = QComboBox()
        self.combo_motion.addItems(["Flexion", "Extension"])
        self.material_combo = QComboBox()
        materials = self.settings.get("materials", [])
        self.material_combo.addItems(materials)

        self.input_name_test.textChanged.connect(self._update_start_button_state)
        self.input_operator.textChanged.connect(self._update_start_button_state)
        self.input_reference.textChanged.connect(self._update_start_button_state)
        self.input_date.dateChanged.connect(self._update_start_button_state)
        self.input_splint.textChanged.connect(self._update_start_button_state)
        self.combo_motion.currentIndexChanged.connect(self._update_start_button_state)

        # Ligne 0
        grid.addWidget(QLabel("Name of the test :"),   0, 0)
        grid.addWidget(self.input_name_test,      0, 1)
        grid.addWidget(QLabel("Date :"),          0, 2)
        grid.addWidget(self.input_date,           0, 3)
        grid.addWidget(QLabel("Reference of the brace"), 0,4)
        grid.addWidget(self.input_reference,            0, 5)
        grid.addWidget(QLabel("Material:"),     0, 6)
        grid.addWidget(self.material_combo,     0, 7)

        # Ligne 15
        grid.addWidget(QLabel("Type of brace:"),1, 0)
        grid.addWidget(self.input_splint,       1, 1)
        grid.addWidget(QLabel("Motion:"),       1, 2)
        grid.addWidget(self.combo_motion,       1, 3)
        grid.addWidget(QLabel("Operator:"),     1, 4)
        grid.addWidget(self.input_operator,     1, 5)
        grid.addWidget(QLabel("Note: "),        1, 6)
        grid.addWidget(self.input_note,         1, 7)

        
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(6,6,6,6)
        grp.setLayout(grid)
        layout.addWidget(grp)

                # --- Bench selection (simple combobox) ---
        benches = self.settings.get("benches", [])
        # Keep a map name -> bench dict
        self._bench_by_name = {b.get("name", f"Bench {i+1}"): b for i, b in enumerate(benches)}
        default_bench = next(iter(self._bench_by_name.values()), {"name":"Default","factor":0.025,"lever_arm_mm":85,"torque_threshold":3.4})
        self.bench = default_bench  # current selection

        bench_row = QHBoxLayout()
        bench_row.addWidget(QLabel("Bench:"))

        self.bench_combo = QComboBox()
        self.bench_combo.addItems(list(self._bench_by_name.keys()) or ["Default"])
        if self.bench_combo.count() > 0:
            self.bench_combo.setCurrentIndex(0)
        self.bench_combo.currentTextChanged.connect(self._on_bench_changed)
        bench_row.addWidget(self.bench_combo)

        # small read-only preview
        self.bench_info_lbl = QLabel(
            f"factor={self.bench.get('factor')} | lever={self.bench.get('lever_arm_mm')} mm | τ={self.bench.get('torque_threshold')} Nm"
        )
        bench_row.addWidget(self.bench_info_lbl, stretch=1)

        bench_grp = QGroupBox("Bench")
        v = QVBoxLayout()
        v.addLayout(bench_row)
        bench_grp.setLayout(v)
        layout.addWidget(bench_grp)



        self.event_log = QTextEdit(readOnly=True)
        layout.addWidget(QLabel("Serial Console"))
        layout.addWidget(self.event_log)

        # Mode
        self.mode_select = QComboBox()
        self.mode_select.addItems(["Manual positioning", "Calibration", "Homing"])
        self.mode_select.currentTextChanged.connect(self._on_mode_changed)
        grp = QGroupBox("Mode")
        grp.setLayout(QVBoxLayout())
        grp.layout().addWidget(self.mode_select)
        layout.addWidget(grp)

        # Manuel
        self.manual_grp = self._make_button_group(
            "Manual Control",
            [("⬆ Up", "up"), ("⬇ Down", "down"), ("■ Stop", "stop")]
        )
        layout.addWidget(self.manual_grp)

        # Calibration
        self.calib_input = QDoubleSpinBox()
        self.calib_input.setSuffix(" g")
        self.calib_input.setRange(1, 10000)
        self.calib_input.setValue(1550.7)
        btn_cal = QPushButton("Start calibration")
        btn_cal.clicked.connect(lambda: self._send({
            "cmd":"calibrate",
            "weight": self.calib_input.value()
        }))

        btn_read = QPushButton("Read Weight")
        btn_read.setEnabled(True)
        btn_read.clicked.connect(self._on_read_weight)

        calib_layout = QHBoxLayout()
        calib_layout.addWidget(QLabel("Known weight:"))
        calib_layout.addWidget(self.calib_input)
        calib_layout.addWidget(btn_cal)
        calib_layout.addWidget(btn_read)
        self.calib_group = QGroupBox("Calibration")
        self.calib_group.setLayout(calib_layout)
        layout.addWidget(self.calib_group)


        # Homing
        self.homing_group = QGroupBox("Homing")
        h_layout = QHBoxLayout()
        btn_home = QPushButton("Do the Homing")
        btn_home.clicked.connect(lambda: self._send({"cmd":"homing"}))
        h_layout.addWidget(btn_home)
        self.homing_group.setLayout(h_layout)
        self.homing_group.setVisible(False)   # <- caché par défaut
        layout.addWidget(self.homing_group)

        #paramètre du test
        self.speed = QDoubleSpinBox()
        self.speed.setSuffix(" mm/s")
        self.speed.setRange(0.01, 2)
        self.speed.setValue(0.5)

        self.cycles = QSpinBox()
        self.cycles.setRange(1, 1000000)
        self.cycles.setValue(5)

        self.force = QDoubleSpinBox()
        self.force.setSuffix(" N")
        self.force.setRange(0.1, 100)
        self.force.setValue(50)

        self.dist = QDoubleSpinBox()
        self.dist.setSuffix(" mm")
        self.dist.setRange(1, 50)
        self.dist.setValue(10)

        form = QFormLayout()
        form.addRow("Speed:", self.speed)
        form.addRow("Cycles :", self.cycles)
        form.addRow("Maximum force:", self.force)
        form.addRow("Maximum distance :", self.dist)

      
        grp2 = QGroupBox("Test parameters")
        grp2.setLayout(form)
        layout.addWidget(grp2)

        self.chk_preparation = QCheckBox("Include a preparation cycle")
        self.chk_preparation.setChecked(True)  # coché par défaut
        layout.addWidget(self.chk_preparation)

        self.btn_view_graph = QPushButton("📊 See Graph")
        self.btn_view_graph.setEnabled(False)  # tu peux activer selon l’état si besoin
        self.btn_view_graph.clicked.connect(self.view_monitor.emit)
        layout.addWidget(self.btn_view_graph)

        
    def _make_button_group(self, title, items):
        grp = QGroupBox(title)
        h = QHBoxLayout()
        for text, cmd in items:
            btn = QPushButton(text)
            btn.clicked.connect(partial(self._send, {"cmd": cmd}))
            h.addWidget(btn)
        grp.setLayout(h)
        return grp

    def _on_mode_changed(self, mode=None):
        mode = mode or self.mode_select.currentText()
        self.manual_grp.setVisible(mode == "Manual positioning")
        self.calib_group.setVisible(mode == "Calibration")
        self.homing_group.setVisible(mode == "Homing")

    def _update_start_button_state(self):
        # On active le bouton dès que tous les champs meta sont non‑vides
        name_ok     = bool(self.input_name_test.text().strip())
        operator_ok = bool(self.input_operator.text().strip())
        date_ok     = self.input_date.date().isValid()
        splint_ok   = bool(self.input_splint.text().strip())
        motion_ok   = bool(self.combo_motion.currentText())
        ref_ok      = bool(self.input_reference.text().strip())
        self.btn_play.setEnabled(name_ok and operator_ok and date_ok and splint_ok and motion_ok and ref_ok)
        self.btn_view_graph.setEnabled(True)  # idem pour Voir Graphe


    def _send(self, msg: dict):
        #text = json.dumps(msg)
        self.serial.send(msg)
        self.event_log.append(f"📤 {msg}")

    def _start_test(self):
        # 1) Construis tes métadonnées en Python
        self.metadata = {
            "name":     self.input_name_test.text().strip(),
            "date":     self.input_date.date().toString("yyyyMMdd"),
            "operator": self.input_operator.text().strip().capitalize(), 
            "splint":   self.input_splint.text().strip().upper(),
            "reference" :self.input_reference.text().strip().upper(),
            "motion":   self.combo_motion.currentText().lower(),
            "material": self.material_combo.currentText().upper(),
            "note":     self.input_note.text().strip()
        }

        self.config = {
            "speed": self.speed.value(),
            "force_max": self.force.value(),
            "cycles":   self.cycles.value(),
            "prep_cycle": self.chk_preparation.isChecked(),
            "bench": {
                "name": self.bench.get("name"),
                "factor": float(self.bench.get("factor", 0.025)),
                "lever_arm_mm": float(self.bench.get("lever_arm_mm", 85)),
                "torque_threshold": float(self.bench.get("torque_threshold", 3.4))
            }
        }       
    # 2. Gestion du dossier de sauvegarde
        data_path = self.settings["default_paths"].get("data_path")
        #base_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        default_folder_name = get_default_folder(data_path, self.metadata)
        selected_folder = ask_user_for_folder(self, data_path, default_folder_name)
        
        if not selected_folder:
            QMessageBox.warning(self, "Cancel", "No files selected")
            return


        self.save_folder = selected_folder
        motion = self.metadata.get("motion", "unknown")
        filename = f"config_{motion}.json" if motion in ("flexion", "extension") else "config.json"
        json_path = os.path.join(selected_folder, filename)
        save_test_config(self.metadata, self.config, json_path)

        #self.event_log.append(f"💾 Paramètres sauvegardés : {json_path}")

        ret = QMessageBox.warning(
            self,
            "⚠️ Safety before testing",
            "Please ensure that there are no objects or hands under the load cell.\n\nPress OK to start the test.",
            QMessageBox.Ok | QMessageBox.Cancel
        )

        if ret != QMessageBox.Ok:
            self.event_log.append("❌ Test canceled by user")
            return

        #créer le fichier text des res
        filename = filename = make_filename(self.metadata, "_raw.txt")
        full_path =  os.path.join(self.save_folder, filename)

        #à envoyer a arduino 
        prep_cycle_int = 1 if self.chk_preparation.isChecked() else 0
        cfg = {
            "cmd":"start",
            "p": {
                "sp": self.speed.value(),
                "cy": self.cycles.value()+prep_cycle_int,
                "ft": self.force.value(),
                "dm" : self.dist.value()
            }
        }
        self.event_log.clear()
        self._send(cfg)
        self.event_log.append(f"📤 {cfg}")

        
        self.start_test.emit({
            "metadata": self.metadata,
            "config": self.config,  
            "folder": self.save_folder, 
            "file_path" : full_path
        })

        #self._lock_ui(True)

    def set_serial(self, handler: SerialHandler):
        self.serial = handler
        handler.line_received.connect(lambda ln: self.event_log.append(f"📥 {ln}"))
        handler.command_sent.connect(lambda c: self.event_log.append(f"📤 {json.dumps(c)}"))
        #handler.json_received.connect(lambda m: self.event_log.append(f"🔁 {json.dumps(m)}"))
        handler.error.connect(lambda e: QMessageBox.critical(self, "Serial error", e))

    def _on_read_weight(self):
        self.event_log.append("🔍 Weight reading...")
        self._reading_weight = True
        # envoie la commande JSON
        self._send({ "cmd": "read" })

    def _on_data_received(self, t, d, f):
        if self._reading_weight:
            # c’est notre trame “read_weight”
            self.event_log.append(f"⚖️ Weight measured : {f:.2f} N (pos={d:.1f} mm, t={t:.2f}s)")
            self._reading_weight = False
            return

    def _lock_ui(self, locked: bool):
        for w in (self.mode_select, self.speed, self.cycles, self.force, self.dist):
            w.setEnabled(not locked)
    
    def _on_reading_json(self, msg: dict):
        # Only handle it if we're in "read weight" mode
        if self._reading_weight and msg.get("event") == "READ":
            f = msg.get("f", float('nan'))
            self.event_log.append(f"⚖️ Weight measured : {f:.2f} N ")
            self._reading_weight = False

    def _on_bench_changed(self, name: str):
        self.bench = self._bench_by_name.get(name, self.bench)
        self.bench_info_lbl.setText(
            f"factor={self.bench.get('factor')} | lever={self.bench.get('lever_arm_mm')} mm | τ={self.bench.get('torque_threshold')} Nm"
        )
        # (optional) enforce Start enabled only when bench exists:
        self._update_start_button_state()

