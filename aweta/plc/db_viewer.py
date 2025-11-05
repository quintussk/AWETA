"""DB viewer for displaying PLC data blocks."""

from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
)

try:
    from rich.console import Console
    from rich.table import Table as RichTable
    _RICH_OK = True
except ImportError:
    _RICH_OK = False

try:
    from TIA_Db.utlis import S7DataBlock as TIA_S7DataBlock
except ImportError:
    TIA_S7DataBlock = None  # type: ignore


class DBViewer(QDialog):
    """Dialog for viewing and loading PLC data blocks."""
    
    def __init__(self, parent=None):
        """Initialize DB viewer.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("DB Viewer")
        self.resize(520, 500)
        
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_load = QPushButton("DB laden...", self)
        self.btn_load.clicked.connect(self._choose_db_definition)
        self.btn_refresh = QPushButton("Refresh", self)
        self.btn_refresh.clicked.connect(self._refresh_view)
        toolbar.addWidget(self.btn_load)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        
        # Tree widget
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Variable", "Value"])
        layout.addWidget(self.tree)
        
        # State
        self.db_block = None
        self.db_definition_path: Optional[str] = None
    
    def _choose_db_definition(self):
        """Open file dialog to choose DB definition file."""
        path, _ = QFileDialog.getOpenFileName(self, "Kies TIA DB (.db)", "", "TIA DB (*.db)")
        if not path:
            return
        
        if TIA_S7DataBlock is None:
            QMessageBox.critical(self, "Fout", "TIA_Db module niet beschikbaar")
            return
        
        try:
            # Default to DB1 unless you prefer a prompt
            dbn = 1
            self.db_block = TIA_S7DataBlock.from_definition_file(
                path=path,
                db_number=dbn,
                nesting_depth_to_skip=1
            )
            self.db_definition_path = path
            self._refresh_view()
        except Exception as e:
            QMessageBox.critical(self, "Fout", f"Kon DB niet laden:\n{e}")
    
    def _refresh_view(self):
        """Refresh the tree view with current DB data."""
        if self.db_block is None:
            return
        
        self.tree.clear()
        names = list(getattr(self.db_block, 'data', {}).keys())
        for name in names:
            try:
                val = self.db_block[name]
            except Exception:
                val = "?"
            QTreeWidgetItem(self.tree, [name, self._fmt_val(val)])
        
        # Rich to console
        if _RICH_OK and self.db_block is not None:
            try:
                console = Console()
                title = f"DB{getattr(self.db_block, 'db_number', '?')} – {Path(self.db_definition_path).name if self.db_definition_path else ''}"
                tbl = RichTable(title=title)
                tbl.add_column("Variable", style="bold")
                tbl.add_column("Value")
                for name in names:
                    try:
                        val = self.db_block[name]
                    except Exception:
                        val = "?"
                    style = "green" if isinstance(val, bool) and val else ("red" if isinstance(val, bool) else ("cyan" if isinstance(val, (int, float)) else "white"))
                    tbl.add_row(name, f"[{style}]{self._fmt_val(val)}[/]")
                console.print(tbl)
            except Exception:
                pass
    
    def _fmt_val(self, v):
        """Format a value for display."""
        if isinstance(v, bool):
            return "True" if v else "False"
        if isinstance(v, float):
            return f"{v:.4g}"
        return str(v)
    
    def get_db_block(self):
        """Get the current DB block.
        
        Returns:
            Current DB block or None
        """
        return self.db_block
    
    def set_db_block(self, db_block):
        """Set the DB block to display.
        
        Args:
            db_block: DB block to display
        """
        self.db_block = db_block
        self._refresh_view()

