"""Toolbox dialog for selecting tools to add."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QListWidget,
    QDialogButtonBox,
)


class ToolboxDialog(QDialog):
    """Dialog for selecting tools from the toolbox."""
    
    def __init__(self, parent=None):
        """Initialize toolbox dialog.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Toolbox")
        self.resize(260, 220)
        
        layout = QVBoxLayout(self)
        self.list = QListWidget(self)
        self.list.addItem("Belt")
        self.list.addItem("Exit")
        layout.addWidget(self.list)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
    
    def selected_part(self) -> str | None:
        """Get the selected tool.
        
        Returns:
            Selected tool name or None
        """
        it = self.list.currentItem()
        return it.text() if it else None

