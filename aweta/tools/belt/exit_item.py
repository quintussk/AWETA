"""Exit block graphics item for conveyor belt simulation."""

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


class ExitBlock(QGraphicsRectItem):
    """Graphics item representing an exit block."""
    
    def __init__(self, x: float, y: float, w: float = 180, h: float = 80, label: str = "Exit"):
        """Initialize an exit block.
        
        Args:
            x: X position
            y: Y position
            w: Width in pixels
            h: Height in pixels
            label: Display label
        """
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.setBrush(QBrush(Qt.white))
        self.setPen(QPen(Qt.black, 2))
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable
        )
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
        # Only input port (left)
        self.p_in = BeltPort(self, 0, h / 2)
        
        # Title
        self.label = label
        self.title_item = QGraphicsSimpleTextItem(self)
        self.title_item.setText(self.label)
        self.title_item.setPos(8, 6)
        
        # FT In (left-top) and FT Out (right-top)
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
        
        # Boxes per slot (left->right); each slot holds None or {"elapsed": int}
        self.capacity: int = 3
        self.slots: list[dict | None] = [None] * self.capacity
        # Dwell time (ms) for rightmost box
        self.dwell_ms: int = 2000
        # Shift interval per cell (ms)
        self.advance_ms: int = 600
        self._adv_accum: int = 0
        
        # Countdown label (bottom-right)
        self.timer_text = QGraphicsSimpleTextItem("", self)
        self.timer_text.setVisible(False)
        
        # Segmented tray visuals
        self.inner_frame = QGraphicsRectItem(self)
        self.inner_frame.setPen(QPen(Qt.black, 3))
        self.inner_frame.setBrush(QBrush(Qt.transparent))
        self.slot_lines: list[QGraphicsPathItem] = []
        
        # Per-cell visuals (background + "occupied" fill)
        self.cell_bgs: list[QGraphicsRectItem] = []
        self.cell_fills: list[QGraphicsRectItem] = []
        
        self._rebuild_slots()
    
    def set_label(self, text: str):
        """Set the label text."""
        self.label = text
        self.title_item.setText(self.label)
    
    def set_sensors_enabled(self, in_enabled: bool, out_enabled: bool):
        """Enable/disable FT In and FT Out sensors."""
        self.ft_in_enabled = bool(in_enabled)
        self.ft_out_enabled = bool(out_enabled)
        self.ft_in_item.setVisible(self.ft_in_enabled)
        self.ft_out_item.setVisible(self.ft_out_enabled)
        self.update_sensor_visual()
    
    def update_sensor_visual(self):
        """Update sensor visual indicators."""
        # FT In active if the first slot is occupied
        if self.ft_in_enabled:
            self.ft_in_state = (len(self.slots) > 0 and self.slots[0] is not None)
            self.ft_in_item.setVisible(True)
            self.ft_in_item.setBrush(QBrush(Qt.green if self.ft_in_state else Qt.gray))
            if self.ft_in_var:
                VARS[self.ft_in_var] = bool(self.ft_in_state)
        else:
            self.ft_in_item.setVisible(False)
        
        # FT Out active if the last slot is occupied
        if self.ft_out_enabled:
            self.ft_out_state = (len(self.slots) > 0 and self.slots[-1] is not None)
            self.ft_out_item.setVisible(True)
            self.ft_out_item.setBrush(QBrush(Qt.green if self.ft_out_state else Qt.gray))
            if self.ft_out_var:
                VARS[self.ft_out_var] = bool(self.ft_out_state)
        else:
            self.ft_out_item.setVisible(False)
    
    def _update_timer_text(self):
        """Update the countdown timer text."""
        last = self.slots[-1] if self.slots else None
        if not last:
            self.timer_text.setVisible(False)
            return
        rem_ms = max(0, int(self.dwell_ms) - int(last.get("elapsed", 0)))
        txt = f"{rem_ms / 1000.0:.1f}s"
        self.timer_text.setText(txt)
        br = self.timer_text.boundingRect()
        r = self.rect()
        margin = 6
        self.timer_text.setPos(r.width() - br.width() - margin, r.height() - br.height() - margin)
        self.timer_text.setVisible(True)
    
    def _rebuild_slots(self):
        """Rebuild the visual slot dividers and cells."""
        r = self.rect()
        band_top = 28
        band_bottom = r.height() - 20
        self.inner_frame.setRect(6, band_top, r.width() - 12, max(10, band_bottom - band_top))
        
        # Remove old lines
        for ln in self.slot_lines:
            try:
                self.scene().removeItem(ln)
            except Exception:
                pass
        self.slot_lines = []
        
        # Remove old per-cell visuals
        for it in getattr(self, "cell_bgs", []):
            try:
                self.scene().removeItem(it)
            except Exception:
                pass
        for it in getattr(self, "cell_fills", []):
            try:
                self.scene().removeItem(it)
            except Exception:
                pass
        self.cell_bgs = []
        self.cell_fills = []
        
        if self.scene() is None:
            return
        
        inner_x = 6
        inner_w = r.width() - 12
        inner_h = max(10, band_bottom - band_top)
        cells = max(1, int(self.capacity))
        cell_w = inner_w / cells
        
        # Vertical dividers
        if cells > 1:
            x = inner_x + cell_w
            for _ in range(1, cells):
                path = QPainterPath(QPointF(x, band_top))
                path.lineTo(QPointF(x, band_bottom))
                ln = QGraphicsPathItem(path, self)
                ln.setPen(QPen(Qt.black, 3))
                self.slot_lines.append(ln)
                x += cell_w
        
        # Per-cell surfaces
        inset = 2
        for i in range(cells):
            x0 = inner_x + i * cell_w
            bg = QGraphicsRectItem(x0 + inset, band_top + inset, cell_w - 2 * inset, inner_h - 2 * inset, self)
            bg.setPen(QPen(Qt.NoPen))
            bg.setBrush(QBrush(Qt.transparent))
            self.cell_bgs.append(bg)
            
            fill = QGraphicsRectItem(x0 + inset, band_top + inset, cell_w - 2 * inset, inner_h - 2 * inset, self)
            fill.setPen(QPen(Qt.NoPen))
            # Light green
            fill.setBrush(QBrush(Qt.green).color().lighter(170))
            fill.setVisible(False)
            self.cell_fills.append(fill)
        
        # Position FT sensors
        self.ft_in_item.setPos(6, 6)
        self.ft_out_item.setPos(self.rect().width() - 14, 6)
        
        # Z-order so the thick black frame draws on top
        self.inner_frame.setZValue(5)
        for ln in self.slot_lines:
            ln.setZValue(6)
        
        self._update_timer_text()
    
    def _refresh_fills_from_boxes(self):
        """Refresh the visual fills based on box occupancy."""
        for i, fill in enumerate(self.cell_fills):
            occupied = (i < len(self.slots) and self.slots[i] is not None)
            fill.setVisible(occupied)
    
    def apply_capacity(self, cap: int):
        """Apply a new capacity setting."""
        self.capacity = max(1, int(cap))
        # Keep existing boxes (left->right order) then right-justify into new capacity
        existing = [b for b in (self.slots if hasattr(self, 'slots') else []) if b is not None]
        keep = existing[-self.capacity:]  # keep rightmost
        self.slots = [None] * self.capacity
        # Place kept boxes at the right
        start = self.capacity - len(keep)
        for idx, b in enumerate(keep):
            self.slots[start + idx] = b
        # Geometry
        base_h = self.rect().height()
        new_w = max(120, self.capacity * TICK_PX)
        self.setRect(0, 0, new_w, base_h)
        self.p_in.setPos(0, base_h / 2)
        self._rebuild_slots()
        self._refresh_fills_from_boxes()
        self._update_timer_text()
    
    def _cell_pos(self, idx: int) -> QPointF:
        """Get the position of a cell by index."""
        r = self.rect()
        band_top = 28
        band_bottom = r.height() - 20
        cells = max(1, self.capacity if self.capacity > 0 else 1)
        cell_w = (r.width() - 12) / cells
        x = 6 + idx * cell_w + (cell_w - 14) / 2
        y = (band_top + band_bottom) / 2 - 5
        return QPointF(x, y)
    
    def _repack_boxes(self):
        """Repack boxes in slots."""
        self._refresh_fills_from_boxes()
    
    def can_accept(self) -> bool:
        """Check if this exit block can accept a new box."""
        return any(s is None for s in self.slots)
    
    def add_box(self, box_item: QGraphicsRectItem):
        """Add a box to this exit block.
        
        Args:
            box_item: The box graphics item to add
            
        Returns:
            True if box was added, False otherwise
        """
        if box_item is not None:
            try:
                if box_item.scene() is not None:
                    box_item.scene().removeItem(box_item)
            except Exception:
                pass
        # Find leftmost free slot
        for i in range(len(self.slots)):
            if self.slots[i] is None:
                self.slots[i] = {"elapsed": 0}
                self._refresh_fills_from_boxes()
                self.update_sensor_visual()
                self._update_timer_text()
                return True
        return False
    
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
    
    def tick(self, dt_ms: int):
        """Update the exit block simulation state.
        
        Args:
            dt_ms: Delta time in milliseconds
        """
        if not self.slots:
            return
        
        # Dwell timer for rightmost slot
        last = self.slots[-1] if self.slots else None
        if last is not None:
            last["elapsed"] = int(last.get("elapsed", 0)) + int(dt_ms)
            if last["elapsed"] >= int(self.dwell_ms):
                # Remove rightmost box
                self.slots[-1] = None
        
        # Accumulate advance and shift boxes one cell to the right when due
        self._adv_accum += int(dt_ms)
        if self._adv_accum >= int(self.advance_ms):
            self._adv_accum = 0
            # From right-2 down to 0, move if next is empty
            for i in range(len(self.slots) - 2, -1, -1):
                if self.slots[i] is not None and self.slots[i + 1] is None:
                    self.slots[i + 1] = self.slots[i]
                    self.slots[i] = None
        
        self._refresh_fills_from_boxes()
        self.update_sensor_visual()
        self._update_timer_text()

