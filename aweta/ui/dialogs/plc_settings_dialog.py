"""Settings dialog for PLC connection configuration."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDialogButtonBox,
)


class PLCSettingsDialog(QDialog):
    """Dialog for configuring PLC connection settings."""
    
    def __init__(self, parent, plc_ip: str, plc_rack: int, plc_slot: int):
        """Initialize PLC settings dialog.
        
        Args:
            parent: Parent widget
            plc_ip: Current PLC IP address
            plc_rack: Current PLC rack number
            plc_slot: Current PLC slot number
        """
        super().__init__(parent)
        self.setWindowTitle("PLC instellingen")
        
        layout = QVBoxLayout(self)
        
        # IP
        row_ip = QHBoxLayout()
        row_ip.addWidget(QLabel("IP:", self))
        self.ip_edit = QLineEdit(plc_ip, self)
        row_ip.addWidget(self.ip_edit)
        layout.addLayout(row_ip)
        
        # Rack
        row_rack = QHBoxLayout()
        row_rack.addWidget(QLabel("Rack:", self))
        self.sp_rack = QSpinBox(self)
        self.sp_rack.setRange(0, 10)
        self.sp_rack.setValue(int(plc_rack))
        row_rack.addWidget(self.sp_rack)
        layout.addLayout(row_rack)
        
        # Slot
        row_slot = QHBoxLayout()
        row_slot.addWidget(QLabel("Slot:", self))
        self.sp_slot = QSpinBox(self)
        self.sp_slot.setRange(0, 10)
        self.sp_slot.setValue(int(plc_slot))
        row_slot.addWidget(self.sp_slot)
        layout.addLayout(row_slot)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        layout.addWidget(buttons)
        
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
    
    def get_settings(self) -> tuple[str, int, int]:
        """Get the configured settings.
        
        Returns:
            Tuple of (ip, rack, slot)
        """
        return (
            self.ip_edit.text().strip() or "192.168.241.191",
            int(self.sp_rack.value()),
            int(self.sp_slot.value())
        )

