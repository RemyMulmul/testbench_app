# main.py
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QMenu
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction
from controllers.serial_handler import SerialHandler
from views.port_selection_page   import PortSelectionPage
from views.control_panel_page    import ControlPanelPage
from views.monitor_page          import MonitorPage
from views.analysis_page         import AnalysisPage
from utils.setting_utils import load_settings
from utils.setting_utils import get_path_from_settings
import webbrowser
POLLING_MS =30

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Bench Controller")
        self.settings = load_settings()

        # --- Centralized serial handler ---
        self.serial = SerialHandler(self, POLLING_MS)
        self.serial.error.connect(self._on_serial_error)
        self.serial.event_received.connect(self._on_arduino_event)

        # --- Page instantiation ---
        self.port_page    = PortSelectionPage(self.serial, self.settings)        
        self.control_page = ControlPanelPage(self.settings)
        self.monitor_page = MonitorPage()
        self.analysis_page= AnalysisPage(self.settings)

        # --- Stack the page ---
        self.stack = QStackedWidget()
        for page in (self.port_page, self.control_page,
                     self.monitor_page, self.analysis_page):
            self.stack.addWidget(page)
         # === Main layout===
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # --- Header with help button ---
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)  
        header.setSpacing(0)

        btn_help = QToolButton()
        btn_help.setText("?")
        btn_help.setFixedSize(15, 15)
        btn_help.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_help.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
            padding: 0px;
            margin: 0px;
            border: none;
            background: transparent;
            color: #555;
        """)
        btn_help.setCursor(Qt.PointingHandCursor)
        btn_help.clicked.connect(self.open_help)
        header.addWidget(btn_help, alignment=Qt.AlignRight | Qt.AlignTop)

        main_layout.addLayout(header)
        main_layout.addWidget(self.stack)
        self.setCentralWidget(central_widget)


        # --- Menu Bar ---
        menu_bar = self.menuBar()

        # 1. Menu Help
        help_menu = QMenu("Help", self)
        help_action = QAction("Open the documentation", self)
        help_action.triggered.connect(self.open_help)
        help_menu.addAction(help_action)
        menu_bar.addMenu(help_menu)

        # 2. Menu Assistance
        support_menu = QMenu("Support", self)
        contact_action = QAction("Contact Rémy Mühlethaler", self)
        contact_action.triggered.connect(self.show_support_info)
        support_menu.addAction(contact_action)
        menu_bar.addMenu(support_menu)

        # --- Navigation & Signals ---
        # 1) After handshake READY, PortSelectionPage emits .connected(port)
        self.port_page.connected.connect(self.on_connected)
        self.port_page.analysis_requested.connect(lambda: self.stack.setCurrentWidget(self.analysis_page))

        # 2) In ControlPanelPage: start the test
        self.control_page.start_test.connect(self._on_start_test)
        #    and “View Graph” button
        self.control_page.view_monitor.connect(
            lambda: self.stack.setCurrentWidget(self.monitor_page)
        )
        #    and “Analyze results” button
        self.control_page.analysis_requested.connect(
            lambda: self.stack.setCurrentWidget(self.analysis_page)
        )

        # 3) From MonitorPage and AnalysisPage, return to control panel
        self.monitor_page.back_to_control.connect(
            lambda: self.stack.setCurrentWidget(self.control_page)
        )
        self.analysis_page.back_to_control.connect(
            self._back_from_analysis
        )

        # 4) Start on the port selection page
        self.stack.setCurrentWidget(self.port_page)

    def on_connected(self):
        """
        As soon as PortSelectionPage confirms the connection (handshake READY),
        wire up serial pages and show the control panel.
        """
        # Initialize pages so they listen to self.serial
        self.control_page.set_serial(self.serial)
        self.monitor_page.set_serial(self.serial)
        # Switch to control panel
        self.stack.setCurrentWidget(self.control_page)

    def _on_start_test(self, context: dict):
        """
        ControlPanelPage emits its metadata when the signal start_test(meta) is triggered.
        Pass it to MonitorPage before showing the graph.
        """
        self.monitor_page.set_metadata(context)
        self.monitor_page.clear()
        self.stack.setCurrentWidget(self.monitor_page)

    def _on_arduino_event(self, event: str):
        """
        Automatically switch pages based on Arduino events (START / END / IDLE / EMERGENCY_STOP).
        """
        if event == "START":
            self.stack.setCurrentWidget(self.monitor_page)
        elif event == "EMERGENCY_STOP":
            QMessageBox.critical(self, "Emergency Stop", "Emergency stop triggered!")
            self.stack.setCurrentWidget(self.control_page)
        elif event in ("END", "IDLE"):
            self.stack.setCurrentWidget(self.control_page)

    def _on_serial_error(self, err: str):
        """
        On serial error, close the port, notify the user, and return to the port selector.
        """
        try:
            if self.serial.ser and self.serial.ser.is_open:
                self.serial.ser.close()
        except Exception:
            pass
        QMessageBox.critical(self, "Serial Error", err)
        self.stack.setCurrentWidget(self.port_page)
    
    def _back_from_analysis(self):
        if not self.serial.ser or not self.serial.ser.is_open:
            self.stack.setCurrentWidget(self.port_page)
        else:
            self.stack.setCurrentWidget(self.control_page)

    def open_help(self):
        try:
            help_doc = get_path_from_settings("help_path")

            if not help_doc.exists():
                print(f"[ERROR] Help document not found at: {help_doc}")
                return

            uri = help_doc.as_uri()
            success = webbrowser.open(uri)

            if not success:
                print("[ERROR] webbrowser.open() returned False — could not open the help document.")

        except Exception as e:
            print(f"[ERROR] Exception occurred: {e}")
    
    def show_support_info(self):
        QMessageBox.information(
            self,
            "technical support",
            "📞 Do you have a problem :\n\n"
            "Rémy Mühlethaler\n"
            "+41 77 429 94 56"
        )
        email = "remy.muhlethaler16@gmail.com"  
        subject = "Technical support Swibrace"
        body = "Hello Rémy,\n\nI have some issue with the software TestBench of Swibrace..."
        mailto_link = f"mailto:{email}?subject={subject}&body={body}"
        webbrowser.open(mailto_link)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    icon_path = get_path_from_settings("icon_path")
    app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
