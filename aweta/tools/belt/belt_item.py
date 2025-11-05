"""Belt graphics item for conveyor belt simulation."""

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
)

from aweta.core.constants import TICK_PX
from aweta.core.variables import VARS
from aweta.tools.belt.port import Port as BeltPort


class Belt(QGraphicsRectItem):
    """Graphics item representing a conveyor belt."""
    
    def __init__(self, x: float, y: float, w: float = TICK_PX, h: float = 80, label: str = "Belt"):
        """Initialize a belt.
        
        Args:
            x: X position
            y: Y position
            w: Width in pixels
            h: Height in pixels
            label: Display label
        """
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.setBrush(QBrush(Qt.darkGray))
        self.setPen(QPen(Qt.black, 2))
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable
        )
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # Ports (left/right)
        self.p_in = BeltPort(self, 0, h / 2)
        self.p_out = BeltPort(self, w, h / 2)
        self.label = label
        
        # Configurable properties
        self.width_ticks = 1  # default 1 tick wide
        self.motor_var: str | None = None
        
        # FT In / FT Out sensors
        self.ft_in_enabled: bool = False
        self.ft_in_var: str | None = None
        self.ft_in_state: bool = False
        self.ft_in_item = QGraphicsEllipseItem(-5, -5, 10, 10, self)
        self.ft_in_item.setBrush(QBrush(Qt.gray))
        self.ft_in_item.setPen(QPen(Qt.black, 1))
        self.ft_in_item.setVisible(False)
        
        self.ft_out_enabled: bool = False
        self.ft_out_var: str | None = None
        self.ft_out_state: bool = False
        self.ft_out_item = QGraphicsEllipseItem(-5, -5, 10, 10, self)
        self.ft_out_item.setBrush(QBrush(Qt.gray))
        self.ft_out_item.setPen(QPen(Qt.black, 1))
        self.ft_out_item.setVisible(False)
        
        # Segmented visuals (inner tray + dividers)
        self.inner_frame = QGraphicsRectItem(self)
        self.inner_frame.setPen(QPen(Qt.black, 3))
        self.inner_frame.setBrush(QBrush(Qt.transparent))
        self.slot_lines: list[QGraphicsPathItem] = []
        
        # Ensure sizing/ports consistent with ticks
        self.resize_for_ticks(self.width_ticks)
        
        # Title label as child item
        self.title_item = QGraphicsSimpleTextItem(self)
        self.title_item.setText(self.label)
        self.title_item.setPos(8, 6)
        
        # Occupancy (shows if a box is currently on this belt)
        self.has_box = False
        # Motor state cache for debug/visual updates
        self._motor_on_state = False
    
    def set_label(self, text: str):
        """Set the label text."""
        self.label = text
        if hasattr(self, 'title_item') and self.title_item is not None:
            self.title_item.setText(self.label)
    
    def resize_for_ticks(self, ticks: int):
        """Resize the belt based on number of ticks."""
        self.width_ticks = max(1, int(ticks))
        r = self.rect()
        new_w = self.width_ticks * TICK_PX
        self.setRect(0, 0, new_w, r.height())
        h = r.height()
        self.p_in.setPos(0, h / 2)
        self.p_out.setPos(new_w, h / 2)
        # Place FT In (left top) and FT Out (right top)
        self.ft_in_item.setPos(6, 8)
        self.ft_out_item.setPos(new_w - 12, 8)
        self._rebuild_slots()
    
    def _rebuild_slots(self):
        """Rebuild the visual slot dividers."""
        # Defensive: ensure visuals exist if called before __init__ completed
        if not hasattr(self, "inner_frame") or self.inner_frame is None:
            self.inner_frame = QGraphicsRectItem(self)
            self.inner_frame.setPen(QPen(Qt.black, 3))
            self.inner_frame.setBrush(QBrush(Qt.transparent))
        if not hasattr(self, "slot_lines") or self.slot_lines is None:
            self.slot_lines = []
        
        # Draw inner framed area and vertical dividers per tick
        r = self.rect()
        margin_top = 28  # top of middle band
        margin_bottom = 20  # bottom of middle band
        y1 = margin_top
        y2 = r.height() - margin_bottom
        self.inner_frame.setRect(8, y1, r.width() - 16, max(10, y2 - y1))
        
        # Remove old lines
        for ln in self.slot_lines:
            try:
                self.scene().removeItem(ln)
            except Exception:
                pass
        self.slot_lines = []
        
        if self.scene() is None:
            return
        
        if self.width_ticks > 1:
            cell_w = (r.width() - 16) / self.width_ticks
            x = 8 + cell_w
            for _ in range(1, self.width_ticks):
                path = QPainterPath(QPointF(x, y1))
                path.lineTo(QPointF(x, y2))
                ln = QGraphicsPathItem(path, self)
                ln.setPen(QPen(Qt.black, 3))
                self.slot_lines.append(ln)
                x += cell_w
    
    def set_sensors_enabled(self, in_enabled: bool, out_enabled: bool):
        """Enable/disable FT In and FT Out sensors."""
        self.ft_in_enabled = bool(in_enabled)
        self.ft_out_enabled = bool(out_enabled)
        self.ft_in_item.setVisible(self.ft_in_enabled)
        self.ft_out_item.setVisible(self.ft_out_enabled)
        self.update_sensor_visual()
    
    def update_sensor_visual(self):
        """Update sensor visual indicators."""
        # FT In active when a box is in the first tick cell
        if not hasattr(self, 'width_ticks'):
            return
        if self.ft_in_enabled:
            self.ft_in_item.setVisible(True)
            self.ft_in_item.setBrush(QBrush(Qt.green if self.ft_in_state else Qt.gray))
            if self.ft_in_var is not None:
                VARS[self.ft_in_var] = bool(self.ft_in_state)
        else:
            self.ft_in_item.setVisible(False)
        
        # FT Out active when box is in the last tick cell
        if self.ft_out_enabled:
            self.ft_out_item.setVisible(True)
            self.ft_out_item.setBrush(QBrush(Qt.green if self.ft_out_state else Qt.gray))
            if self.ft_out_var is not None:
                VARS[self.ft_out_var] = bool(self.ft_out_state)
        else:
            self.ft_out_item.setVisible(False)
    
    def update_box_indicator(self):
        """Update box indicator (placeholder for future use)."""
        pass
    
    def itemChange(self, change, value):
        """Handle item change events."""
        from PySide6.QtWidgets import QGraphicsItem as _QGI
        if change == _QGI.ItemPositionHasChanged:
            sc = self.scene()
            if sc is not None:
                views = sc.views()
                if views:
                    v = views[0]
                    if hasattr(v, 'update_all_link_paths'):
                        v.update_all_link_paths()
        return super().itemChange(change, value)

