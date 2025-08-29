import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QLabel, QLineEdit, QMessageBox, QSpinBox, QCheckBox, QDoubleSpinBox, QGroupBox, QGridLayout, QInputDialog, QDialog, QComboBox
)
from PySide6.QtCore import Signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

import matplotlib.pyplot as plt
import pandas as pd
import json
# Importez vos fonctions
from utils.data_to_excel_report import export_to_excel_report
from utils.data_treatement import*
from utils.data_treatement import _pava
from matplotlib.lines import Line2D
from matplotlib import rcParams
import subprocess, sys

OPEN_EXCEL = True

class AnalysisPage(QWidget):
    back_to_control = Signal()

    def __init__(self, settings):
        super().__init__()
        self.config_data = {}  # Initialise vide
        self.settings = settings
        self._build_ui()
        self.loaded_cycles = []
        self.target_mm = None


    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 1) Sélecteur de fichier
        file_layout = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        btn_browse = QPushButton("📂 Select file")
        btn_browse.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(btn_browse)
        layout.addLayout(file_layout)

        # 2) Boutons d’analyse
        btn_plot_cycles = QPushButton("Trace cycles")
        btn_plot_cycles.clicked.connect(self._on_plot_cycles)
        
        plast_layout = QHBoxLayout()
        btn_plot_plast = QPushButton("Cycle plasticity")
        btn_plot_plast.clicked.connect(self._on_plot_plast)

        self.threshold_input = QDoubleSpinBox()
        self.threshold_input.setDecimals(3)
        self.threshold_input.setRange(0.01, 5.0)
        self.threshold_input.setValue(0.3)
        self.threshold_input.setSingleStep(0.01)
        self.threshold_input.setMaximumWidth(100)

        plast_layout.addWidget(btn_plot_plast)
        plast_layout.addSpacing(20)
        plast_layout.addWidget(QLabel("Threshold:"))
        plast_layout.addWidget(self.threshold_input)
        plast_layout.addStretch(1)

        # ➕ Nouveau bouton
        btn_save_plast = QPushButton("💾 Save plasticity")
        btn_save_plast.clicked.connect(self._on_save_plasticity)
        plast_layout.addWidget(btn_save_plast)

        plast_layout.addStretch(1)

        layout.addLayout(plast_layout)


        btn_calib = QPushButton("Calculate best threshold")
        btn_calib.clicked.connect(self._on_calibrate_threshold)

        layout.addWidget(btn_plot_cycles)
        layout.addWidget(btn_calib)

        # 3) Zone pour afficher les résultats (seuil, erreurs…)
        self.result_label = QLabel("")
        layout.addWidget(self.result_label)

        # 4) Canvas Matplotlib
        
        self.figure = Figure(figsize=(6, 4), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.ax = self.figure.add_subplot(111)

        # >>> NETTETÉ HiDPI
        try:
            
            dpr = self.window().devicePixelRatioF() if self.window() else self.devicePixelRatioF()
            base_dpi = rcParams.get("figure.dpi", self.figure.dpi)
            self.figure.set_dpi(base_dpi * max(1.0, dpr))
        except Exception:
            pass

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        

        # Show dummy plot for test
        self.ax.text(0.5, 0.5, "No graph available at this time", ha="center", va="center")
        self.canvas.draw()
        #6) Section d'export filtré
        filter_box = QGroupBox("Export a range of filtered cycles")
        filter_layout = QGridLayout()

        self.spin_start = QSpinBox()
        self.spin_end   = QSpinBox()
        self.spin_start.setMinimum(0)
        self.spin_end.setMinimum(0)
        self.spin_start.setMaximum(1000000)
        self.spin_end.setMaximum(1000000)

        self.force_min = QDoubleSpinBox()
        self.force_max = QDoubleSpinBox()
        self.force_min.setRange(-0.05, 100); self.force_min.setSuffix(" N")
        self.force_max.setRange(0, 100); self.force_max.setSuffix(" N")
        self.force_max.setValue(51)


        filter_layout.addWidget(QLabel("Beginning cycle:"), 0, 0)
        filter_layout.addWidget(self.spin_start,         0, 1)
        filter_layout.addWidget(QLabel("End cycle:"),   0, 2)
        filter_layout.addWidget(self.spin_end,           0, 3)

        filter_layout.addWidget(QLabel("Minimum force:"),   1, 0)
        filter_layout.addWidget(self.force_min,          1, 1)
        filter_layout.addWidget(QLabel("Maximum force:"),   1, 2)
        filter_layout.addWidget(self.force_max,          1, 3)

        self.chk_rising_only = QCheckBox("Ascent phase only")
        self.chk_rising_only.setChecked(False)
        filter_layout.addWidget(self.chk_rising_only, 2, 0, 1, 4)

        btn_export = QPushButton("📤 Export filtered cycles")
        btn_export.clicked.connect(self._on_export_filtered)
        filter_layout.addWidget(btn_export,              3, 0, 1, 4)

        filter_box.setLayout(filter_layout)
        layout.addWidget(filter_box)

        self.spin_start.valueChanged.connect(self._preview_filtered_cycles)
        self.spin_end.valueChanged.connect(self._preview_filtered_cycles)
        self.force_min.valueChanged.connect(self._preview_filtered_cycles)
        self.force_max.valueChanged.connect(self._preview_filtered_cycles)
        self.chk_rising_only.toggled.connect(self._preview_filtered_cycles)

        btn_excel_export = QPushButton("📊 Calculate and export the result on Excel")
        btn_excel_export.clicked.connect(lambda: self._on_export_excel_report(OPEN_EXCEL))
        layout.addWidget(btn_excel_export)

          # 5) Bouton retour
        btn_back = QPushButton("← Back to control")
        btn_back.clicked.connect(lambda: self.back_to_control.emit())
        layout.addWidget(btn_back)

    def ask_torque_threshold(self):
        values = self.settings.get("analysis").get("torque_threshold", [])
        items = [str(v) for v in values]
        selected, ok = QInputDialog.getItem(self, "Torque threshold", "Selecting a torque :", items, 0, False)
        if ok:
            return float(selected)
        return None

    def _browse_file(self):
        # récupérer le dossier "data" depuis settings
        data_dir = self.settings.get("default_paths", {}).get("data_path", "")

        path, _ = QFileDialog.getOpenFileName(self, "Select a file", data_dir, "Text files (*.txt)")
        if path:
            self.file_path_edit.setText(path)
            self.loaded_cycles = self._load_raw_data(path)
            self._preview_filtered_cycles()
            self.test_folder = os.path.dirname(path)



    def _on_plot_cycles(self):
        path = self.file_path_edit.text()
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid file", "Please select a valid file.")
            return

        if not self.loaded_cycles:
            self.loaded_cycles = self._load_raw_data(path)
            if not self.loaded_cycles:
                QMessageBox.warning(self, "No data", "Could not load cycles from the file.")
                return

        # show ALL cycles using the same preview logic
        total = len(self.loaded_cycles)
        self.spin_start.blockSignals(True)
        self.spin_end.blockSignals(True)
        self.spin_start.setValue(0)
        self.spin_end.setValue(max(0, total - 1))
        self.spin_start.blockSignals(False)
        self.spin_end.blockSignals(False)

        self._preview_filtered_cycles()

    
    
    def _on_plot_plast(self):
        path = self.file_path_edit.text()
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid file", "Please select a valid file.")
            return

        if not self.loaded_cycles:
            self.loaded_cycles = self._load_raw_data(path)
            if not self.loaded_cycles:
                QMessageBox.warning(self, "No data", "Could not load cycles from the file.")
                return

        Fref = float(self.threshold_input.value())
        df = compute_abs_plasticity(
            path,
            time_reset_threshold=0.05,
            force_threshold=Fref,
            min_cycle_length=10
        )
        if df.empty:
            QMessageBox.warning(self, "No results", "No absolute plasticity could be computed at this threshold.")
            return

        target_to_plot = self.target_mm
        

        # Plot
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_title(f"Absolute plasticity vs cycle (Fref = {Fref:.3f} N)")
        ax.set_xlabel("Cycle")
        ax.set_ylabel("Absolute plasticity (mm)")
        ax.grid(True)
        ax.plot(df["Cycle"], df["Abs_plast_mm"], marker="o", linestyle="-", label="Abs_plast")
        if target_to_plot is not None:
            ax.axhline(target_to_plot, linestyle=":", label=f"Target {target_to_plot:.3f} mm")
        ax.legend()
        self.canvas.draw()

        last_abs = float(df["Abs_plast_mm"].iloc[-1])
        self.result_label.setText(f"Absolute plasticity (last cycle) = {last_abs:.3f} mm (Fref = {Fref:.3f} N)")


    def _on_calibrate_threshold(self):
        path = self.file_path_edit.text()
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid file", "Please select a valid file.")
            return

        try:
            best_t, diag = calibrate_threshold_match_target_first(
                path,
                target_F0=0.05,                 # ← “petit peu plus grand que 0”
                time_reset_threshold=0.05,
                min_cycle_length=10,
                search_range=(0.01,2),
                step=0.05
            )
        except Exception as e:
            QMessageBox.critical(self, "Calibration failed", f"An error occurred:\n{e}")
            return

        target = diag.get("target")
        self.target_mm = float(target) if target is not None else None

        if best_t is None or target is None:
            self.result_label.setText("No satisfactory threshold (no near-zero target).")
            return

        self.threshold_input.setValue(float(best_t))
        c = diag["candidates"][best_t]
        self.result_label.setText(
            f"Best Fref ≈ {best_t:.3f} N | target≈{target:.3f} mm | ")

        # Optional: plot
        df = compute_abs_plasticity(path, time_reset_threshold=0.05,
                                    force_threshold=float(best_t), min_cycle_length=10)
        if not df.empty:
            y = pd.to_numeric(df["Abs_plast_mm"], errors="coerce").dropna().values
            x = np.arange(1, len(y)+1)
            yhat = _pava(y)
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.set_title(f"ABS plasticity (Fref={best_t:.3f} N) vs target≈{target:.3f} mm")
            ax.set_xlabel("Cycle"); ax.set_ylabel("Plasticité absolue (mm)"); ax.grid(True)
            ax.plot(x, y, "o-", label="Abs_plast (raw)")
            ax.plot(x, yhat, "--", label="Isotone")
            ax.axhline(target, linestyle=":", label="Target")
            ax.legend()
        self.canvas.draw()

    def _on_export_filtered(self):
        path = self.file_path_edit.text()
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid file", "Please select a valid file.")
            return

        if not self.loaded_cycles:
            QMessageBox.warning(self, "Error," "No cycle loaded.")
            return

        start = self.spin_start.value()
        end   = self.spin_end.value()
        fmin  = self.force_min.value()
        fmax  = self.force_max.value()

        df = self._filter_cycles(self.loaded_cycles, start, end, fmin, fmax)
        #print(df)
        if df.empty:
            QMessageBox.warning(self, "No results", "No data matches the filter.")
            return

        self.ax.clear()
        self.ax.set_title(f"Filtered cycles {start}–{end}, force {fmin}-{fmax} N")
        self.ax.set_xlabel("Distance (mm)")
        self.ax.set_ylabel("Force (N)")
        self.ax.grid(True)
        self.ax.plot(df["distance"], df["force"], marker='o', linestyle='-')
        self.canvas.draw()

        self._export_filtered_cycles(df, path, start, end, fmin, fmax)

    def _load_raw_data(self, path: str, time_reset_threshold: float = 0.05) -> list:
        """
        Loads raw data from a text file and splits cycles
        based on time zero returns.

        Returns a list of DataFrames [time, distance, force].
        """
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid file", "File not found.")
            return []

        try:
            # Read file, automatic separation (spaces or tabs)
            data = pd.read_csv(path, sep=r"\s+", engine="python", header=None, names=["time", "distance", "force"])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read file:\n{e}")
            return []

        if data.empty or len(data.columns) != 3:
            QMessageBox.warning(self, "Invalid format", "The file does not contain three columns.")
            return []

        t = data["time"].values
        reset_idx = [0]

        # Detect cycle starts (time strongly decreases = reset)
        for i in range(1, len(t)):
            if t[i] < t[i - 1] - time_reset_threshold:
                reset_idx.append(i)
        reset_idx.append(len(t))

        # Split into cycles
        cycles = []
        for i in range(len(reset_idx) - 1):
            i0, i1 = reset_idx[i], reset_idx[i + 1]
            cycle_df = data.iloc[i0:i1].reset_index(drop=True)
            cycles.append(cycle_df)

        return cycles


    def _filter_cycles(self, cycles: list, start: int, end: int, fmin=None, fmax=None) -> pd.DataFrame:
        """
        Filter cycles by index and force range.
        Optionally, keep only the rising phase.
        """
        filtered = []
        rising_only = self.chk_rising_only.isChecked()

        for idx in range(start, end + 1):
            if idx < 0 or idx >= len(cycles):
                continue
            df = cycles[idx]

            # Option: filter by force
            if fmin is not None:
                df = df[df["force"] >= fmin]
            if fmax is not None:
                df = df[df["force"] <= fmax]

            # Option: keep only rising phase
            if rising_only and not df.empty:
                df = df.reset_index(drop=True)
                idx_max = df["force"].idxmax()  # Index of maximum force
                df = df.iloc[:idx_max + 1]      # Keep everything until the peak

            if not df.empty:
                filtered.append(df)

        if not filtered:
            return pd.DataFrame(columns=["time", "distance", "force"])
        return pd.concat(filtered, ignore_index=True)

    def _export_filtered_cycles(self, df: pd.DataFrame, base_path: str, start: int, end: int, fmin=None, fmax=None):
        """
        Export filtered cycles into a file with an adapted name.
        Replaces '_raw' with '_filtered' in the file name, or adds '_filtered' if missing.
        """
        base_name = os.path.basename(base_path)
        name, _ = os.path.splitext(base_name)

        if "_raw" in name:
            name = name.replace("_raw", "_filtered")
        elif "_filtré" not in name:
            name += "_filtered"

        parts = [f"{name}-cycle{start}-{end}"]

        filename = "_".join(parts) + ".txt"
        output_path = os.path.join(os.path.dirname(base_path), filename)

        df.to_csv(output_path, sep="\t", index=False, header=False)
        QMessageBox.information(self, "Export complete", f"File exported:\n{output_path}")
                                
    def _preview_filtered_cycles(self):
        if not self.loaded_cycles:
            return

        start = self.spin_start.value()
        end   = self.spin_end.value()
        fmin  = self.force_min.value()
        fmax  = self.force_max.value()

        df_all = self._filter_cycles(self.loaded_cycles, start, end, fmin, fmax)

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_title(f"Preview cycles {start}–{end}, force {fmin}-{fmax} N")
        ax.set_xlabel("Distance (mm)")
        ax.set_ylabel("Force (N)")
        ax.grid(True)

        if df_all.empty:
            self.canvas.draw()
            return

        # --- Color by cycle, mais légende limitée ---
        segments = []
        for idx in range(start, end + 1):
            if idx < 0 or idx >= len(self.loaded_cycles):
                continue
            seg_df = self._filter_cycles([self.loaded_cycles[idx]], 0, 0, fmin, fmax)
            if not seg_df.empty:
                segments.append((idx, seg_df))

        n = len(segments)
        if n == 0:
            self.canvas.draw()
            return

        cmap = plt.cm.get_cmap("tab20", max(n, 1))

        # indices qui auront une entrée de légende
        label_idxs = set(range(min(4, n))) | set(range(max(0, n - 4), n))
        middle_count = n - len(label_idxs)

        handles, labels = [], []

        for i, (cycle_idx, seg_df) in enumerate(segments):
            color = cmap(i)
            show_label = (i in label_idxs)
            label = f"Cycle {cycle_idx}" if show_label else "_nolegend_"

            ax.plot(
                seg_df["distance"], seg_df["force"],
                label=label, color=color,
                linewidth=1.25, alpha=0.9,
            )
            ax.scatter(
                seg_df["distance"], seg_df["force"],
                s=4, color=color, alpha=0.9,
            )

        # Construire la légende
        if middle_count > 0:
            # proxy pour "… X cycles au milieu"
            proxy = Line2D([], [], linestyle='-', linewidth=1.25, color='0.5', alpha=0.6)
            h, l = ax.get_legend_handles_labels()
            h.append(proxy)
            l.append(f"… {middle_count} cycles au milieu")
            ax.legend(h, l, loc="best", title="Légende")
        else:
            ax.legend(loc="best", title="Légende")

        self.canvas.draw()

    def _on_export_excel_report(self, open_excel: bool = True):
        options = QFileDialog.Option()
        options |= QFileDialog.DontUseNativeDialog
        data_dir = self.settings.get("default_paths", {}).get("data_path", "")

        flexion_path, _ = QFileDialog.getOpenFileName(
            self, "Flexion file", data_dir, "Text files (*.txt)", options=options
        )
        extension_path, _ = QFileDialog.getOpenFileName(
            self, "Extension file", data_dir, "Text files (*.txt)", options=options
        )

        # ❗ allow ONE or TWO files
        if not flexion_path and not extension_path:
            QMessageBox.warning(self, "Missing files", "Select at least one file (flexion OR extension).")
            return

        has_flex = bool(flexion_path)
        has_ext  = bool(extension_path)

        # Export dir
        sel_dirs = [os.path.dirname(p) for p in (flexion_path, extension_path) if p]
        if len(set(sel_dirs)) == 1:
            export_dir = sel_dirs[0]
        else:
            export_dir = QFileDialog.getExistingDirectory(self, "Export folder")
            if not export_dir:
                QMessageBox.warning(self, "Canceled", "No folder selected.")
                return

        # ---- helpers
        def _safe_load_json(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    j = json.load(f)
                return j
            except Exception as ex:
                return {}

        # ---- load configs
        config_flex = {}
        config_ext  = {}
        if has_flex:
            flex_dir = os.path.dirname(flexion_path)
            cfg_path = os.path.join(flex_dir, "config_flexion.json")
            config_flex = _safe_load_json(cfg_path)

        if has_ext:
            ext_dir = os.path.dirname(extension_path)
            cfg_path = os.path.join(ext_dir, "config_extension.json")
            config_ext = _safe_load_json(cfg_path)

        # ---- compatibility (both sides only)
        if has_flex and has_ext:
            try:
                check_compatibility(config_flex, config_ext)
            except ValueError as e:
                QMessageBox.warning(self, "Incompatibility", str(e))
                return

        # ---- choose meta/config (NO merge when single file)
        if has_flex and has_ext:
            merged_meta   = merge_data(config_flex.get("metadata", {}), config_ext.get("metadata", {}))
            merged_config = merge_data(config_flex.get("config", {}),    config_ext.get("config", {}))
        elif has_flex:
            merged_meta   = config_flex.get("metadata", {}) or {}
            merged_config = config_flex.get("config",   {}) or {}
        else:
            merged_meta   = config_ext.get("metadata", {}) or {}
            merged_config = config_ext.get("config",   {}) or {}

        # ---- prefill fields
        title    = get_fused_value(merged_meta.get("name", ""), "Name")
        date     = get_fused_value(merged_meta.get("date", ""), "Date")
        brace    = get_fused_value(merged_meta.get("splint", ""), "Brace type")
        ref      = get_fused_value(merged_meta.get("reference", ""), "Reference")
        operator = get_fused_value(merged_meta.get("operator",""), "Operator")
        material = get_fused_value(merged_meta.get("material", ""), "Material")
        note     = get_fused_value(merged_meta.get("note", ""), "Note")

        speed     = get_fused_value(merged_config.get("speed", ""), "Speed")
        force_max = get_fused_value(merged_config.get("force_max",""), "Force Max")
        bench_cfg = merged_config.get("bench", {}) or {}
        factor    = bench_cfg.get("factor", 0.025)
        lever     = bench_cfg.get("lever_arm_mm", 85.0)
        torque_th = bench_cfg.get("torque_threshold", 3.4)

        # ---- dialogs (user may cancel)
        def _is_missing(val):
            if val is None:
                return True
            if isinstance(val, str):
                s = val.strip()
                return s == "" or s.lower() in {"none", "n/a", "na", "nan", "null"}
            return False


        # ---- dialogs (ask ONLY if missing/invalid)
        ok1 = ok2 = ok3 = ok4 = True

        # Title
        if _is_missing(title):
            title, ok1 = QInputDialog.getText(self, "Title", "File title:", text=str(title or ""))
        # Reference
        if _is_missing(ref):
            ref, ok4 = QInputDialog.getText(self, "Reference", "Sample reference:", text=str(ref or ""))
        # Date (must be YYYY-MM-DD)
        if _is_missing(date):
            date, ok2 = QInputDialog.getText(self, "Date", "Test date (YYYYMMDD):", text="")
        # Brace / Brand type
        if _is_missing(brace):
            brace, ok3 = QInputDialog.getText(self, "Brace type", "Brace type (RHIZ, SCAPH, WRST):", text=str(brace or ""))

        if not all([ok1, ok2, ok3, ok4]):
            return
        # ---- export
        try:
            results = export_to_excel_report(
                flexion_path if has_flex else None,
                extension_path if has_ext else None,
                output_folder=export_dir,
                file_title=title, test_date=date,
                brace_type=brace, sample_reference=ref, speed=speed,
                force_max=force_max, operator=operator, material=material,
                torque=torque_th, factor=factor, lever_arm_mm=lever,
                note=note   # ensure the function signature accepts note=None
            )
            merge_configs_and_results(export_dir, results)
            QMessageBox.information(self, "Success", "Excel export and config_final.json generated successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{e}")
        try : 
            if open_excel:
                excel_path = os.path.join(export_dir, f"{title}.xlsx")
                if os.path.exists(excel_path):
                    if sys.platform.startswith("darwin"):      # macOS
                        subprocess.call(["open", excel_path])
                    elif os.name == "nt":                      # Windows
                        os.startfile(excel_path)
                    elif os.name == "posix":                   # Linux
                        subprocess.call(["xdg-open", excel_path])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Open of excel failed:\n{e}")
        
    def _on_save_plasticity(self):
        path = self.file_path_edit.text()
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Invalid file", "Please load a file first.")
            return

        seuil = float(self.threshold_input.value())

        try:
            df = compute_abs_plasticity(path, time_reset_threshold=0.05, force_threshold=seuil, min_cycle_length=10)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Plasticity calculation error:\n{e}")
            return

        if df.empty or "Abs_plast_mm" not in df.columns:
            QMessageBox.warning(self, "Error", "Invalid absolute plasticity data.")
            return

        abs_series = df["Abs_plast_mm"].dropna()
        if abs_series.empty:
            QMessageBox.warning(self, "Error", "Absolute plasticity series is empty.")
            return

        plast_abs_value = round(float(abs_series.iloc[-1]), 4)
        seuil = round(seuil, 3)

        base_dir = os.path.dirname(path)
        config_path = os.path.join(
            base_dir, "config_extension.json" if "extension" in path.lower() else "config_flexion.json"
        )
        if not os.path.isfile(config_path):
            QMessageBox.warning(self, "Missing file", f"Config file not found:\n{config_path}")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            if "mechanical_results" not in config:
                config["mechanical_results"] = {}

            # Écrire uniquement les champs utiles
            config["mechanical_results"]["plasticity_absolute"] = plast_abs_value
            config["mechanical_results"]["plasticity_threshold"] = seuil

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

            QMessageBox.information(self, "Success", f"Plastic deformation saved to:\n{config_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write config file:\n{e}")

def get_fused_value(value, key=""):
    if isinstance(value, dict):
        v_flex = value.get("flexion", "")
        v_ext  = value.get("extension", "")
        if v_flex == v_ext:
            return v_flex
        return f"{v_flex} (flexion), {v_ext} (extension)"
    return value


def merge_data(meta1, meta2):
    merged = {}
    for key in set(meta1.keys()).union(meta2.keys()):
        v1 = meta1.get(key)
        v2 = meta2.get(key)

        if isinstance(v1, dict) and isinstance(v2, dict):
            merged[key] = merge_data(v1, v2)
            
        if v1 == v2 or v2 is None:
            merged[key] = v1
        elif v1 is None:
            merged[key] = v2
        else:
            merged[key] = {"flexion": v1, "extension": v2}
    return merged


def check_compatibility(config1, config2):
    keys_to_match = ["speed", "force_max"]
    for key in keys_to_match:
        if config1["config"].get(key) != config2["config"].get(key):
            raise ValueError(f"Parameter '{key}' differs between the two tests.")

def merge_configs_and_results(folder_path: str, results: dict) -> str:
    """
    Écrit config_final.json en utilisant:
      - les 2 configs si présentes (fusion tolérante),
      - sinon la seule dispo (flexion OU extension).
    Lève une erreur seulement si AUCUNE des deux n'existe.
    Retourne le chemin du fichier final.
    """
    import os, json

    def _safe_load(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as ex:
            return {}

    flex_path = os.path.join(folder_path, "config_flexion.json")
    ext_path  = os.path.join(folder_path, "config_extension.json")

    has_flex = os.path.isfile(flex_path)
    has_ext  = os.path.isfile(ext_path)

    # ❗ Ancienne condition probablement 'or' → trop stricte.
    if not has_flex and not has_ext:
        raise FileNotFoundError("No config_flexion.json nor config_extension.json found.")

    flex_cfg = _safe_load(flex_path) if has_flex else {}
    ext_cfg  = _safe_load(ext_path)  if has_ext  else {}

    # Choix/merge
    if has_flex and has_ext:
        merged_metadata = merge_data(flex_cfg.get("metadata", {}), ext_cfg.get("metadata", {}))
        merged_config   = merge_data(flex_cfg.get("config",   {}), ext_cfg.get("config",   {}))
    elif has_flex:
        merged_metadata = flex_cfg.get("metadata", {}) or {}
        merged_config   = flex_cfg.get("config",   {}) or {}
    else:
        merged_metadata = ext_cfg.get("metadata", {}) or {}
        merged_config   = ext_cfg.get("config",   {}) or {}

    final = {
        "metadata": merged_metadata,
        "config": merged_config,
        "mechanical_results": results,
    }

    final_path = os.path.join(folder_path, "config_final.json")
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=4)

    return final_path

