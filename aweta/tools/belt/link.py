"""Link graphics item for connecting tools."""

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QPainterPath
from PySide6.QtWidgets import QGraphicsPathItem


class RubberLink(QGraphicsPathItem):
    """Temporary link shown while connecting tools."""
    
    def __init__(self, start_pos: QPointF):
        """Initialize a rubber link.
        
        Args:
            start_pos: Starting position of the link
        """
        super().__init__()
        self.setPen(QPen(Qt.darkGreen, 2))
        self.start = start_pos
        self.update_to(start_pos)
    
    def update_to(self, end_pos: QPointF):
        """Update the link to end at the given position.
        
        Args:
            end_pos: Ending position of the link
        """
        path = QPainterPath(self.start)
        # Simple bezier curve
        mid = (self.start + end_pos) / 2
        ctrl = QPointF(mid.x(), self.start.y())
        path.cubicTo(ctrl, QPointF(mid.x(), end_pos.y()), end_pos)
        self.setPath(path)

