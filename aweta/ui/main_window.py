"""Main window for AWETA application."""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QPen
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QDoubleSpinBox,
    QDialog,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QLineEdit,
    QGraphicsEllipseItem,
)

try:
    from TIA_Db.utlis import S7DataBlock as TIA_S7DataBlock
except ImportError:
    TIA_S7DataBlock = None  # type: ignore

try:
    import snap7  # type: ignore
except ImportError:
    snap7 = None  # type: ignore

try:
    from rich.console import Console
    from rich.table import Table as RichTable
    _RICH_OK = True
except ImportError:
    _RICH_OK = False

from aweta.core.constants import TICK_PX
from aweta.core.variables import VARS
from aweta.tools.belt.belt_item import Belt
from aweta.tools.belt.exit_item import ExitBlock
from aweta.tools.belt.box_generator import BoxGenerator
from aweta.ui.view import View
from aweta.ui.dialogs.toolbox_dialog import ToolboxDialog
from aweta.ui.dialogs.plc_settings_dialog import PLCSettingsDialog
from aweta.plc.db_viewer import DBViewer
from aweta.project.manager import ProjectManager


class MainWindow(QMainWindow):
    """Main window for the AWETA application."""
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Conveyor UI – drag, link, animate")
        central = QWidget(self)
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        
        # Top bar
        topbar = QHBoxLayout()
        
        # Toolbox button
        self.btn_toolbox = QPushButton("Toolbox", self)
        self.btn_toolbox.clicked.connect(self.open_toolbox)
        topbar.addWidget(self.btn_toolbox)
        
        # Project buttons
        self.btn_new = QPushButton("Nieuw", self)
        self.btn_open = QPushButton("Open...", self)
        self.btn_save = QPushButton("Opslaan als...", self)
        self.btn_new.clicked.connect(self.new_project)
        self.btn_open.clicked.connect(self.open_project)
        self.btn_save.clicked.connect(self.save_project_as)
        topbar.addWidget(self.btn_new)
        topbar.addWidget(self.btn_open)
        topbar.addWidget(self.btn_save)
        self.current_path: Optional[str] = None
        
        # Testing controls
        self.btn_all_on = QPushButton("All belts ON", self)
        self.btn_all_on.clicked.connect(self.all_belts_on)
        topbar.addWidget(self.btn_all_on)
        
        self.btn_gen_start = QPushButton("Generator Start", self)
        self.btn_gen_start.clicked.connect(self.gen_start)
        topbar.addWidget(self.btn_gen_start)
        
        self.btn_gen_stop = QPushButton("Generator Stop", self)
        self.btn_gen_stop.clicked.connect(self.gen_stop)
        topbar.addWidget(self.btn_gen_stop)
        
        self.btn_clear_boxes = QPushButton("Clear all boxes", self)
        self.btn_clear_boxes.clicked.connect(self.clear_all_boxes)
        topbar.addWidget(self.btn_clear_boxes)
        
        # DB Viewer
        self.btn_db = QPushButton("DB Viewer", self)
        self.btn_db.clicked.connect(self.open_db_viewer)
        topbar.addWidget(self.btn_db)
        
        # PLC settings and connection
        self.btn_plc_settings = QPushButton("PLC instellingen", self)
        self.btn_plc_settings.clicked.connect(self.open_plc_settings)
        topbar.addWidget(self.btn_plc_settings)
        
        self.btn_connect = QPushButton("Verbind", self)
        self.btn_connect.clicked.connect(self.start_connection)
        topbar.addWidget(self.btn_connect)
        
        self.lbl_status = QLabel("Snap7: Not connected", self)
        topbar.addWidget(self.lbl_status)
        
        # Simulation speed
        topbar.addWidget(QLabel("Speed:", self))
        self.spin_speed = QDoubleSpinBox(self)
        self.spin_speed.setRange(0.1, 5.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        self.spin_speed.valueChanged.connect(self.on_speed_changed)
        topbar.addWidget(self.spin_speed)
        
        topbar.addStretch(1)
        lay.addLayout(topbar)
        
        # Create graphics view (canvas)
        self.view = View()
        lay.addWidget(self.view)
        
        # DB / Snap7 state
        self.db_block = None
        self.db_definition_path: Optional[str] = None
        self._db_dialog: Optional[QDialog] = None
        self._db_tree = None
        self._snap_client = None
        self._snap_timer = QTimer(self)
        self._snap_timer.timeout.connect(self._poll_snap7)
        
        # PLC connection parameters
        self.plc_ip = "192.168.241.191"
        self.plc_rack = 0
        self.plc_slot = 1
        
        # Project manager
        self.project_manager = ProjectManager()
        
        # DB viewer instance
        self._db_viewer: Optional[DBViewer] = None
    
    def all_belts_on(self):
        """Set all belts' motor_var to True."""
        for item in self.view.scene.items():
            if isinstance(item, Belt) and item.motor_var:
                VARS[item.motor_var] = True
    
    def gen_start(self):
        """Start the generator."""
        if getattr(self.view, 'generator', None) is not None:
            self.view.generator.start()
    
    def gen_stop(self):
        """Stop the generator."""
        if getattr(self.view, 'generator', None) is not None:
            self.view.generator.stop()
    
    def clear_all_boxes(self):
        """Remove all boxes on the conveyor line."""
        if hasattr(self, 'view') and hasattr(self.view, 'clear_line_boxes'):
            self.view.clear_line_boxes()
    
    def on_speed_changed(self, val: float):
        """Update simulation speed multiplier."""
        self.view.sim_speed = max(0.1, float(val))
    
    def open_toolbox(self):
        """Open the toolbox dialog."""
        dlg = ToolboxDialog(self)
        if dlg.exec() == QDialog.Accepted:
            choice = dlg.selected_part()
            if choice == "Belt":
                self.view.add_belt()
                self.view.refresh_link_tooltips()
            elif choice == "Exit":
                self.view.add_exit()
                self.view.refresh_link_tooltips()
    
    def _make_var_input(self, parent, initial: str | None):
        """Create a variable input widget (ComboBox or LineEdit).
        
        Args:
            parent: Parent widget
            initial: Initial value
            
        Returns:
            QComboBox if DB variables available, else QLineEdit
        """
        names = []
        if self.db_block is not None and hasattr(self.db_block, 'data'):
            try:
                names = sorted(list(self.db_block.data.keys()))
            except Exception:
                names = []
        if names:
            cmb = QComboBox(parent)
            cmb.setEditable(True)
            cmb.addItems(names)
            cmb.setCurrentText(initial or "")
            return cmb
        else:
            return QLineEdit(initial or "", parent)
    
    def _get_var_value(self, widget) -> str | None:
        """Get value from variable input widget.
        
        Args:
            widget: Widget to get value from
            
        Returns:
            Variable name or None
        """
        if isinstance(widget, QComboBox):
            txt = widget.currentText().strip()
            return txt or None
        if isinstance(widget, QLineEdit):
            txt = widget.text().strip()
            return txt or None
        return None
    
    def open_db_viewer(self):
        """Open the DB viewer dialog."""
        if self._db_viewer is not None:
            try:
                if not self._db_viewer.isVisible():
                    self._db_viewer.show()
                self._db_viewer.raise_()
                self._db_viewer.activateWindow()
                self._db_viewer.set_db_block(self.db_block)
                self._db_viewer._refresh_view()
                return
            except Exception:
                self._db_viewer = None
        
        self._db_viewer = DBViewer(self)
        if self.db_block is not None:
            self._db_viewer.set_db_block(self.db_block)
        self._db_viewer.show()
    
    def open_plc_settings(self):
        """Open PLC settings dialog."""
        dlg = PLCSettingsDialog(self, self.plc_ip, self.plc_rack, self.plc_slot)
        if dlg.exec() == QDialog.Accepted:
            self.plc_ip, self.plc_rack, self.plc_slot = dlg.get_settings()
    
    def start_connection(self):
        """Start PLC connection."""
        if snap7 is None:
            QMessageBox.critical(self, "Fout", "snap7 module niet beschikbaar")
            self.lbl_status.setText("Snap7: Not connected")
            return
        
        # Create client if needed
        if self._snap_client is None:
            try:
                self._snap_client = snap7.client.Client()
            except Exception as e:
                QMessageBox.critical(self, "Fout", f"Kon snap7 client maken:\n{e}")
                self._snap_client = None
                self.lbl_status.setText("Snap7: Not connected")
                return
        
        # Attempt connect
        ok = False
        try:
            self._snap_client.connect(self.plc_ip, int(self.plc_rack), int(self.plc_slot))
            ok = bool(self._snap_client.get_connected())
        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kon niet verbinden:\n{e}")
            ok = False
        
        if ok:
            self.lbl_status.setText("Snap7: Connected")
            if not self._snap_timer.isActive():
                self._snap_timer.start(500)
        else:
            self.lbl_status.setText("Snap7: Not connected")
            if self._snap_timer.isActive():
                self._snap_timer.stop()
    
    def _poll_snap7(self):
        """Poll PLC for data updates."""
        if self._snap_client is None or self.db_block is None:
            return
        try:
            if not self._snap_client.get_connected():
                self.lbl_status.setText("Snap7: Not connected")
                return
            self.lbl_status.setText("Snap7: Connected")
            if self._snap_client.get_connected():
                buf = self._snap_client.db_read(
                    db_number=self.db_block.db_number,
                    start=0,
                    size=self.db_block.db_size
                )
                # Update buffer in place
                self.db_block.buffer = bytearray(buf)
                # Update global VARS from parsed DB variables
                try:
                    for name in list(getattr(self.db_block, 'data', {}).keys()):
                        try:
                            val = self.db_block[name]
                            # Normalize to boolean for motor/sensor flags
                            VARS[name] = bool(val)
                        except Exception:
                            continue
                except Exception:
                    pass
                # Live refresh if dialog open
                if self._db_viewer is not None and self._db_viewer.isVisible():
                    self._db_viewer._refresh_view()
        except Exception:
            # Keep trying silently
            self.lbl_status.setText("Snap7: Not connected")
    
    def new_project(self):
        """Create a new project."""
        # Clear scene
        self.view.scene.clear()
        # Reset runtime containers
        self.view.links.clear()
        self.view.links_data.clear()
        if hasattr(self.view, 'boxes'):
            self.view.boxes.clear()
        # Reset counters
        self.view.next_belt_id = 1
        self.view.next_belt_num = 1
        self.view.next_exit_id = 1
        self.view.next_exit_num = 1
        # Recreate always-present items (generator)
        self.view.generator = BoxGenerator(10, 10)
        self.view.scene.addItem(self.view.generator)
        # Animation state
        self.view.anim_path = None
        self.view.anim_t = 0.0
        # Clear downstream cache
        if hasattr(self.view, '_rebuild_downstream'):
            self.view._rebuild_downstream()
        # Reset bookkeeping/UI
        self.current_path = None
        self.setWindowTitle("Conveyor UI – drag, link, animate")
        self.view.refresh_port_indicators()
        self.view.generator_blocked = False
    
    def save_project_as(self):
        """Save project to file."""
        path, _ = QFileDialog.getSaveFileName(self, "Project opslaan", "", "Conveyor Project (*.json)")
        if not path:
            return
        self.save_to_path(path)
    
    def open_project(self):
        """Open project from file."""
        path, _ = QFileDialog.getOpenFileName(self, "Project openen", "", "Conveyor Project (*.json)")
        if not path:
            return
        self.load_from_path(path)
    
    def save_to_path(self, path: str):
        """Save project to path using ProjectManager."""
        self.project_manager.save_to_file(path, self.view, self.db_block, self.db_definition_path)
        self.current_path = path
        self.setWindowTitle(f"Conveyor UI – {path}")
        self.view.refresh_port_indicators()
    
    def load_from_path(self, path: str):
        """Load project from path using ProjectManager."""
        data = self.project_manager.load_from_file(path)
        db_block, db_definition_path = self.project_manager.load_project(data, self.view)
        
        if db_block is not None:
            self.db_block = db_block
            self.db_definition_path = db_definition_path
            if self._db_viewer is not None:
                self._db_viewer.set_db_block(db_block)
        
        self.current_path = path
        self.setWindowTitle(f"Conveyor UI – {path}")
        self.view.refresh_link_tooltips()
        self.view.refresh_port_indicators()
        self.view._rebuild_downstream()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

