"""Port graphics item for connecting tools."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QBrush
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from aweta.core.constants import PORT_R


class Port(QGraphicsEllipseItem):
    """Graphics item representing a connection port on a tool."""
    
    def __init__(self, parent: QGraphicsItem, dx: float, dy: float):
        """Initialize a port.
        
        Args:
            parent: Parent graphics item
            dx: X offset from parent
            dy: Y offset from parent
        """
        super().__init__(-PORT_R, -PORT_R, PORT_R * 2, PORT_R * 2, parent)
        self.setBrush(QBrush(Qt.white))
        self.setPen(QPen(Qt.black, 1))
        self.setPos(dx, dy)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

