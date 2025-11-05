"""PLC connection management for AWETA application."""

from typing import Optional
from PySide6.QtCore import QTimer, QObject, Signal

try:
    import snap7  # type: ignore
except ImportError:
    snap7 = None  # type: ignore


class PLCConnection(QObject):
    """Manages connection to a PLC via snap7."""
    
    # Signals
    connected = Signal()
    disconnected = Signal()
    error = Signal(str)
    
    def __init__(self, parent=None):
        """Initialize PLC connection manager.
        
        Args:
            parent: Parent QObject
        """
        super().__init__(parent)
        self._client: Optional[any] = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        
        # Connection parameters
        self.plc_ip = "192.168.241.191"
        self.plc_rack = 0
        self.plc_slot = 1
        
        # DB block reference (set externally)
        self.db_block = None
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected to PLC."""
        if self._client is None:
            return False
        try:
            return bool(self._client.get_connected())
        except Exception:
            return False
    
    def connect(self) -> bool:
        """Connect to the PLC.
        
        Returns:
            True if connection successful, False otherwise
        """
        if snap7 is None:
            self.error.emit("snap7 module not available")
            return False
        
        if self._client is None:
            try:
                self._client = snap7.client.Client()
            except Exception as e:
                self.error.emit(f"Failed to create snap7 client: {e}")
                return False
        
        try:
            self._client.connect(self.plc_ip, int(self.plc_rack), int(self.plc_slot))
            connected = bool(self._client.get_connected())
            if connected:
                self.connected.emit()
                if not self._poll_timer.isActive():
                    self._poll_timer.start(500)
                return True
            else:
                self.disconnected.emit()
                return False
        except Exception as e:
            self.error.emit(f"Failed to connect: {e}")
            self.disconnected.emit()
            return False
    
    def disconnect(self):
        """Disconnect from the PLC."""
        if self._poll_timer.isActive():
            self._poll_timer.stop()
        
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        
        self.disconnected.emit()
    
    def set_connection_params(self, ip: str, rack: int, slot: int):
        """Set connection parameters.
        
        Args:
            ip: PLC IP address
            rack: PLC rack number
            slot: PLC slot number
        """
        self.plc_ip = ip
        self.plc_rack = rack
        self.plc_slot = slot
    
    def _poll(self):
        """Poll PLC for data updates."""
        if self._client is None or self.db_block is None:
            return
        
        try:
            if not self._client.get_connected():
                self.disconnected.emit()
                return
            
            if self.db_block is not None:
                buf = self._client.db_read(
                    db_number=self.db_block.db_number,
                    start=0,
                    size=self.db_block.db_size
                )
                # Update buffer in place
                self.db_block.buffer = bytearray(buf)
        except Exception:
            # Keep trying silently
            self.disconnected.emit()

