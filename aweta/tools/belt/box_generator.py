"""Box generator graphics item for conveyor belt simulation."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QBrush
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsItem,
    QGraphicsSimpleTextItem,
)

from aweta.tools.belt.port import Port as BeltPort


class BoxGenerator(QGraphicsRectItem):
    """Graphics item representing a box generator.
    
    Always-present item that spawns boxes at regular intervals.
    """
    
    def __init__(self, x: float = 10, y: float = 10, w: float = 180, h: float = 70, label: str = "Box Generator"):
        """Initialize a box generator.
        
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
        self.setZValue(-5)
        
        # Always present, not movable/selectable
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        
        # Title
        self.title = QGraphicsSimpleTextItem(label, self)
        self.title.setPos(8, 6)
        
        # Output port on the right
        self.p_out = BeltPort(self, w, h / 2)
        
        # Interval (ms) and timer state
        self.interval_ms = 1500
        self.elapsed_ms = 0
        
        # Blocked state (UI hint when waiting for space downstream)
        self.blocked = False
        
        # Running flag (start/stop)
        self.running = True
        
        # Visual progress bar (bottom)
        self.pb_bg = QGraphicsRectItem(8, h - 16, w - 16, 8, self)
        self.pb_bg.setPen(QPen(Qt.black, 1))
        self.pb_bg.setBrush(QBrush(Qt.lightGray))
        self.pb_fg = QGraphicsRectItem(8, h - 16, 0, 8, self)
        self.pb_fg.setPen(QPen(Qt.NoPen))
        self.pb_fg.setBrush(QBrush(Qt.green))
    
    def set_interval(self, ms: int):
        """Set the spawn interval in milliseconds.
        
        Args:
            ms: Interval in milliseconds (minimum 100)
        """
        self.interval_ms = max(100, int(ms))
        self.elapsed_ms = 0
    
    def start(self):
        """Start the generator."""
        self.running = True
    
    def stop(self):
        """Stop the generator."""
        self.running = False
    
    def tick(self, dt_ms: int):
        """Update the generator state.
        
        Args:
            dt_ms: Delta time in milliseconds
        """
        if not self.running:
            # Keep the progress bar as-is when stopped
            return
        
        # When blocked we hold the bar full and don't advance time
        if self.blocked:
            frac = 1.0
        else:
            self.elapsed_ms = min(self.elapsed_ms + dt_ms, int(self.interval_ms))
            frac = max(0.0, min(1.0, self.elapsed_ms / max(1, int(self.interval_ms))))
        
        w = self.rect().width() - 16
        self.pb_fg.setRect(8, self.rect().height() - 16, w * frac, 8)
    
    def ready_to_spawn(self) -> bool:
        """Check if the generator is ready to spawn a new box.
        
        Returns:
            True if ready to spawn, False otherwise
        """
        return self.elapsed_ms >= int(self.interval_ms)

