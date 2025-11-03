# file: belts_demo.py
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QApplication, QLabel, QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog, QListWidget, QDialogButtonBox, QFileDialog, QInputDialog, QGraphicsSimpleTextItem, QTreeWidget, QTreeWidgetItem, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox
import sys, math
from pathlib import Path
import json

try:
    from rich.console import Console
    from rich.table import Table as RichTable
    _RICH_OK = True
except Exception:
    _RICH_OK = False

try:
    from TIA_Db.utlis import S7DataBlock as TIA_S7DataBlock
except Exception:
    TIA_S7DataBlock = None  # type: ignore

try:
    import snap7  # type: ignore
except Exception:
    snap7 = None  # type: ignore

# Simple variable store (placeholder for external PLC variables)
VARS: dict[str, bool] = {}
TICK_PX = 60  # pixels per tick width

PORT_R = 6

class ToolboxDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Toolbox")
        self.resize(260, 220)
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        self.list = QListWidget(self)
        self.list.addItem("Belt")
        self.list.addItem("Exit")
        layout.addWidget(self.list)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def selected_part(self) -> str:
        it = self.list.currentItem()
        return it.text() if it else None

class Port(QGraphicsEllipseItem):
    def __init__(self, parent, dx, dy):
        super().__init__(-PORT_R, -PORT_R, PORT_R*2, PORT_R*2, parent)
        self.setBrush(QBrush(Qt.white))
        self.setPen(QPen(Qt.black, 1))
        self.setPos(dx, dy)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

class Belt(QGraphicsRectItem):
    def __init__(self, x, y, w=TICK_PX, h=80, label="Belt"):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.setBrush(QBrush(Qt.lightGray))
        self.setPen(QPen(Qt.black, 2))
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable
        )
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # Ports (links/rechts)
        self.p_in  = Port(self, 0,  h/2)
        self.p_out = Port(self, w, h/2)
        self.label = label

        # Configurable properties
        self.width_ticks = 1  # default 1 tick breed
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

        # segmented visuals (inner tray + dividers) — create before first resize
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
        # self.box_indicator = QGraphicsRectItem(8, 24, 10, 10, self)
        # self.box_indicator.setPen(QPen(Qt.black, 1))
        # self.box_indicator.setBrush(QBrush(Qt.gray))

        # (removed duplicated mis-indented slot visuals block)

    def set_label(self, text: str):
        self.label = text
        if hasattr(self, 'title_item') and self.title_item is not None:
            self.title_item.setText(self.label)

    def resize_for_ticks(self, ticks: int):
        self.width_ticks = max(1, int(ticks))
        r = self.rect()
        new_w = self.width_ticks * TICK_PX
        self.setRect(0, 0, new_w, r.height())
        h = r.height()
        self.p_in.setPos(0, h/2)
        self.p_out.setPos(new_w, h/2)
        # place FT In (left top) and FT Out (right top)
        self.ft_in_item.setPos(6, 8)
        self.ft_out_item.setPos(new_w - 12, 8)
        self._rebuild_slots()

    def _rebuild_slots(self):
        # defensive: ensure visuals exist if called before __init__ completed
        if not hasattr(self, "inner_frame") or self.inner_frame is None:
            self.inner_frame = QGraphicsRectItem(self)
            self.inner_frame.setPen(QPen(Qt.black, 3))
            self.inner_frame.setBrush(QBrush(Qt.transparent))
        if not hasattr(self, "slot_lines") or self.slot_lines is None:
            self.slot_lines = []
        # draw inner framed area and vertical dividers per tick
        r = self.rect()
        margin_top = 28         # bovenkant van de middenband
        margin_bottom = 20      # onderkant van de middenband
        y1 = margin_top
        y2 = r.height() - margin_bottom
        self.inner_frame.setRect(8, y1, r.width() - 16, max(10, y2 - y1))

        # verwijder oude lijnen
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
        self.ft_in_enabled = bool(in_enabled)
        self.ft_out_enabled = bool(out_enabled)
        self.ft_in_item.setVisible(self.ft_in_enabled)
        self.ft_out_item.setVisible(self.ft_out_enabled)
        self.update_sensor_visual()

    def update_sensor_visual(self):
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
        pass

    def itemChange(self, change, value):
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

class ExitBlock(QGraphicsRectItem):
    def __init__(self, x, y, w=180, h=80, label="Exit"):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.setBrush(QBrush(Qt.white))
        self.setPen(QPen(Qt.black, 2))
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable
        )
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # Alleen input port (links)
        self.p_in = Port(self, 0, h/2)

        # Titel
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

        # Dozen per slot (left->right); each slot holds None or {"elapsed": int}
        self.capacity: int = 3
        self.slots: list[dict|None] = [None]*self.capacity
        # dwell tijd (ms) voor rightmost box
        self.dwell_ms: int = 2000
        # schuif-interval per cel (ms)
        self.advance_ms: int = 600
        self._adv_accum: int = 0

        # Countdown label (bottom-right)
        from PySide6.QtWidgets import QGraphicsSimpleTextItem as _QGSTI
        self.timer_text = _QGSTI("", self)
        self.timer_text.setVisible(False)

                # segmented tray visuals
        self.inner_frame = QGraphicsRectItem(self)
        self.inner_frame.setPen(QPen(Qt.black, 3))
        self.inner_frame.setBrush(QBrush(Qt.transparent))
        self.slot_lines: list[QGraphicsPathItem] = []

        # Per-cell visuals (achtergrond + "occupied" vulling)
        self.cell_bgs: list[QGraphicsRectItem] = []
        self.cell_fills: list[QGraphicsRectItem] = []

        self._rebuild_slots()

    def set_label(self, text: str):
        self.label = text
        self.title_item.setText(self.label)

    def set_sensors_enabled(self, in_enabled: bool, out_enabled: bool):
        self.ft_in_enabled = bool(in_enabled)
        self.ft_out_enabled = bool(out_enabled)
        self.ft_in_item.setVisible(self.ft_in_enabled)
        self.ft_out_item.setVisible(self.ft_out_enabled)
        self.update_sensor_visual()

    def update_sensor_visual(self):
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
        last = self.slots[-1] if self.slots else None
        if not last:
            self.timer_text.setVisible(False)
            return
        rem_ms = max(0, int(self.dwell_ms) - int(last.get("elapsed", 0)))
        txt = f"{rem_ms/1000.0:.1f}s"
        self.timer_text.setText(txt)
        br = self.timer_text.boundingRect()
        r = self.rect()
        margin = 6
        self.timer_text.setPos(r.width() - br.width() - margin, r.height() - br.height() - margin)
        self.timer_text.setVisible(True)

    def _rebuild_slots(self):
        r = self.rect()
        band_top = 28
        band_bottom = r.height() - 20
        self.inner_frame.setRect(6, band_top, r.width() - 12, max(10, band_bottom - band_top))

        # oude lijnen weg
        for ln in self.slot_lines:
            try:
                self.scene().removeItem(ln)
            except Exception:
                pass
        self.slot_lines = []

        # oude per-cell visuals weg
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

        # verticale verdelers
        if cells > 1:
            x = inner_x + cell_w
            for _ in range(1, cells):
                path = QPainterPath(QPointF(x, band_top))
                path.lineTo(QPointF(x, band_bottom))
                ln = QGraphicsPathItem(path, self)
                ln.setPen(QPen(Qt.black, 3))
                self.slot_lines.append(ln)
                x += cell_w

        # per-cell vlakken
        inset = 2
        for i in range(cells):
            x0 = inner_x + i * cell_w
            bg = QGraphicsRectItem(x0 + inset, band_top + inset, cell_w - 2*inset, inner_h - 2*inset, self)
            bg.setPen(QPen(Qt.NoPen))
            bg.setBrush(QBrush(Qt.transparent))
            self.cell_bgs.append(bg)

            fill = QGraphicsRectItem(x0 + inset, band_top + inset, cell_w - 2*inset, inner_h - 2*inset, self)
            fill.setPen(QPen(Qt.NoPen))
            # lichtgroen zoals in je referentie
            fill.setBrush(QBrush(Qt.green).color().lighter(170))
            fill.setVisible(False)
            self.cell_fills.append(fill)

        # position FT sensors
        self.ft_in_item.setPos(6, 6)
        self.ft_out_item.setPos(self.rect().width() - 14, 6)

        # z-order zodat de dikke zwarte kader erboven tekent
        self.inner_frame.setZValue(5)
        for ln in self.slot_lines:
            ln.setZValue(6)

        self._update_timer_text()

    def _refresh_fills_from_boxes(self):
        for i, fill in enumerate(self.cell_fills):
            occupied = (i < len(self.slots) and self.slots[i] is not None)
            fill.setVisible(occupied)

    def apply_capacity(self, cap: int):
        self.capacity = max(1, int(cap))
        # keep existing boxes (left->right order) then right-justify into new capacity
        existing = [b for b in (self.slots if hasattr(self, 'slots') else []) if b is not None]
        keep = existing[-self.capacity:]  # keep rightmost
        self.slots = [None]*self.capacity
        # place kept boxes at the right
        start = self.capacity - len(keep)
        for idx, b in enumerate(keep):
            self.slots[start+idx] = b
        # geometry
        base_h = self.rect().height()
        new_w = max(120, self.capacity * TICK_PX)
        self.setRect(0, 0, new_w, base_h)
        self.p_in.setPos(0, base_h / 2)
        self._rebuild_slots()
        self._refresh_fills_from_boxes()
        self._update_timer_text()

    def _cell_pos(self, idx: int) -> QPointF:
        r = self.rect()
        band_top = 28
        band_bottom = r.height() - 20
        cells = max(1, self.capacity if self.capacity > 0 else 1)
        cell_w = (r.width() - 12) / cells
        x = 6 + idx * cell_w + (cell_w - 14) / 2
        y = (band_top + band_bottom) / 2 - 5
        return QPointF(x, y)

    def _repack_boxes(self):
        self._refresh_fills_from_boxes()

    def can_accept(self) -> bool:
        return any(s is None for s in self.slots)

    def add_box(self, box_item: QGraphicsRectItem):
        if box_item is not None:
            try:
                if box_item.scene() is not None:
                    box_item.scene().removeItem(box_item)
            except Exception:
                pass
        # find leftmost free slot
        for i in range(len(self.slots)):
            if self.slots[i] is None:
                self.slots[i] = {"elapsed": 0}
                self._refresh_fills_from_boxes()
                self.update_sensor_visual()
                self._update_timer_text()
                return True
        return False

    def itemChange(self, change, value):
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
        if not self.slots:
            return
        # Dwell timer for rightmost slot
        last = self.slots[-1]
        if last is not None:
            last["elapsed"] = int(last.get("elapsed", 0)) + int(dt_ms)
            if last["elapsed"] >= int(self.dwell_ms):
                # remove rightmost box
                self.slots[-1] = None
        # Accumulate advance and shift boxes one cell to the right when due
        self._adv_accum += int(dt_ms)
        if self._adv_accum >= int(self.advance_ms):
            self._adv_accum = 0
            # from right-2 down to 0, move if next is empty
            for i in range(len(self.slots)-2, -1, -1):
                if self.slots[i] is not None and self.slots[i+1] is None:
                    self.slots[i+1] = self.slots[i]
                    self.slots[i] = None
        self._refresh_fills_from_boxes()
        self.update_sensor_visual()
        self._update_timer_text()

# --- BoxGenerator class (always-present, spawns boxes) ---
class BoxGenerator(QGraphicsRectItem):
    def __init__(self, x=10, y=10, w=180, h=70, label="Box Generator"):
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
        self.p_out = Port(self, w, h/2)
        # Interval (ms) and timer state
        self.interval_ms = 1500
        self.elapsed_ms = 0
        # Blocked state (UI hint when waiting for space downstream)
        self.blocked = False
        # Running flag (start/stop)
        self.running = True
        # Visual progress bar (bottom)
        self.pb_bg = QGraphicsRectItem(8, h-16, w-16, 8, self)
        self.pb_bg.setPen(QPen(Qt.black, 1))
        self.pb_bg.setBrush(QBrush(Qt.lightGray))
        self.pb_fg = QGraphicsRectItem(8, h-16, 0, 8, self)
        self.pb_fg.setPen(QPen(Qt.NoPen))
        self.pb_fg.setBrush(QBrush(Qt.green))

    def set_interval(self, ms: int):
        self.interval_ms = max(100, int(ms))
        self.elapsed_ms = 0

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def tick(self, dt_ms: int):
        if not self.running:
            # keep the progress bar as-is when stopped
            return
        # When blocked we hold the bar full and don't advance time
        if self.blocked:
            frac = 1.0
        else:
            self.elapsed_ms = min(self.elapsed_ms + dt_ms, int(self.interval_ms))
            frac = max(0.0, min(1.0, self.elapsed_ms / max(1, int(self.interval_ms))))
        w = self.rect().width() - 16
        self.pb_fg.setRect(8, self.rect().height()-16, w*frac, 8)

    def ready_to_spawn(self) -> bool:
        return self.elapsed_ms >= int(self.interval_ms)

class RubberLink(QGraphicsPathItem):
    def __init__(self, start_pos: QPointF):
        super().__init__()
        self.setPen(QPen(Qt.darkGreen, 2))
        self.start = start_pos
        self.update_to(start_pos)

    def update_to(self, end_pos: QPointF):
        path = QPainterPath(self.start)
        # eenvoudige boog
        mid = (self.start + end_pos) / 2
        ctrl = QPointF(mid.x(), self.start.y())
        path.cubicTo(ctrl, QPointF(mid.x(), end_pos.y()), end_pos)
        self.setPath(path)

def center_of(item: QGraphicsItem) -> QPointF:
    b = item.sceneBoundingRect()
    return b.center()

class View(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setRenderHints(self.renderHints() | self.renderHints().Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setSceneRect(0,0,1600,900)

        self.last_scene_pos = self.sceneRect().center()

        # Counters for IDs and numbering
        self.next_belt_id = 1
        self.next_belt_num = 1

        self.next_exit_id = 1
        self.next_exit_num = 1

        # demo belts
        self.b1 = self.add_belt(60, 60)
        self.b2 = self.add_belt(380, 180)
        self.b3 = self.add_belt(120, 300, 260, 60, "Band 3")

        self.rubber = None
        self.links = []   # lijst van (pathItem, srcPort, dstPort)
        self.links_data = []  # dicts with ids/roles for save/load
        self.downstream = []  # list of (src_obj, dst_belt)
        # react to selection changes (for link highlight + red-dot attach)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        # simulation speed multiplier (1.0 = real-time)
        self.sim_speed = 1.0

        # timer voor animatie
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

        self.link_src = None
        self.link_src_belt = None
        self.link_src_role = None

        # Always-present box generator
        self.generator = BoxGenerator(10, 10)
        self.scene.addItem(self.generator)
        # Active boxes
        self.boxes = []  # list of dicts: {"item": QGraphicsRectItem, "belt": Belt, "t": float}
        self.generator_blocked = False  # wait until downstream is free to spawn next box
    def belt_has_box(self, belt: Belt) -> bool:
        for bx in self.boxes:
            if bx["belt"] is belt:
                return True
        return False


    def add_belt(self, x: float = None, y: float = None, w: float = TICK_PX, h: float = 80, label: str = "Belt"):
        if x is None or y is None:
            p = self.last_scene_pos if hasattr(self, 'last_scene_pos') else self.sceneRect().center()
            x, y = p.x(), p.y()
        # default label if not provided
        if label == "Belt":
            label = f"Band {self.next_belt_num}"
            self.next_belt_num += 1
        b = Belt(x, y, w, h, label)
        b.resize_for_ticks(b.width_ticks)
        b.bid = self.next_belt_id
        self.next_belt_id += 1
        self.scene.addItem(b)
        # Ensure slot visuals are built after the item is in the scene
        if hasattr(b, "_rebuild_slots"):
            b._rebuild_slots()
        b.setSelected(True)
        return b
    
    def add_exit(self, x: float = None, y: float = None, w: float = 180, h: float = 80, label: str = "Exit"):
        if x is None or y is None:
            p = self.last_scene_pos if hasattr(self, 'last_scene_pos') else self.sceneRect().center()
            x, y = p.x(), p.y()
        if label == "Exit":
            label = f"Exit {self.next_exit_num}"
            self.next_exit_num += 1
        ex = ExitBlock(x, y, w, h, label)
        ex.xid = self.next_exit_id
        self.next_exit_id += 1
        self.scene.addItem(ex)
        # Ensure slot visuals are built after the item is in the scene
        if hasattr(ex, "_rebuild_slots"):
            ex._rebuild_slots()
            if hasattr(ex, "_refresh_fills_from_boxes"):
                ex._refresh_fills_from_boxes()
            if hasattr(ex, "_update_timer_text"):
                ex._update_timer_text()
        ex.setSelected(True)
        return ex

    def mousePressEvent(self, ev):
        if ev.button() == Qt.RightButton:
            item = self.itemAt(ev.pos())
            # propagate to parent item if we clicked on a child
            target = item
            while target is not None and not isinstance(target, (QGraphicsPathItem, Belt, ExitBlock, BoxGenerator)):
                target = target.parentItem()
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            act_del_link = None
            act_del_node = None
            if isinstance(target, QGraphicsPathItem):
                target.setSelected(True)
                act_del_link = menu.addAction("Verwijder verbinding")
            elif isinstance(target, (Belt, ExitBlock)):
                target.setSelected(True)
                act_del_node = menu.addAction("Verwijder onderdeel")
            if not menu.isEmpty():
                chosen = menu.exec(ev.globalPosition().toPoint())
                if chosen == act_del_link:
                    self.delete_selected_links()
                    ev.accept(); return
                if chosen == act_del_node:
                    self.delete_selected_nodes()
                    ev.accept(); return
        if ev.button() == Qt.LeftButton:
            item = self.itemAt(ev.pos())
            # Start link if we clicked on a Port
            if isinstance(item, Port):
                parent = item.parentItem()
                # Disallow starting a link from ExitBlock (it only has an input)
                if isinstance(parent, ExitBlock):
                    ev.accept();
                    return
                scene_p = item.scenePos()
                self.rubber = RubberLink(scene_p)
                self.scene.addItem(self.rubber)
                self.link_src = item
                # Determine parent and role
                self.link_src_belt = parent
                if isinstance(parent, Belt):
                    self.link_src_role = 'input' if (hasattr(parent, 'p_in') and item is parent.p_in) else 'output'
                elif isinstance(parent, BoxGenerator):
                    self.link_src_role = 'output'
                else:
                    self.link_src_role = 'output'
                ev.accept();
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        self.last_scene_pos = self.mapToScene(ev.pos())
        if self.rubber is not None:
            end_scene = self.mapToScene(ev.pos())
            self.rubber.update_to(end_scene)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self.rubber is not None:
            # Temporarily hide rubber so hit-test isn't blocked by it
            self.rubber.setVisible(False)
            scene_pos = self.mapToScene(ev.pos())

            # Try to find a Port under cursor; if not, accept releasing on a Belt/Exit body (snap to its input)
            end_item = None
            end_parent = None
            end_role = None
            for it in self.scene.items(scene_pos):
                if isinstance(it, Port) and it is not self.link_src:
                    end_item = it
                    end_parent = it.parentItem()
                    is_input = (isinstance(end_parent, (Belt, ExitBlock)) and hasattr(end_parent, 'p_in') and it is end_parent.p_in)
                    end_role = 'input' if is_input else 'output'
                    break
                # If user releases on a Belt/Exit (not exactly on the dot), snap to its input
                if isinstance(it, (Belt, ExitBlock)):
                    end_item = it.p_in
                    end_parent = it
                    end_role = 'input'
                    break
                # If it's a child of a Belt/Exit, also snap to that input
                par = it.parentItem()
                if isinstance(par, (Belt, ExitBlock)):
                    end_item = par.p_in
                    end_parent = par
                    end_role = 'input'
                    break

            # Restore rubber visibility for cleanup
            self.rubber.setVisible(True)

            if end_item is not None and end_parent is not None:
                # Start values
                src_obj = self.link_src_belt
                src_role = self.link_src_role
                dst_obj = end_parent
                dst_role = end_role
                # Swap if necessary so we always create output->input
                if src_role == 'input' and dst_role == 'output':
                    src_obj, dst_obj = dst_obj, src_obj
                    src_role, dst_role = dst_role, src_role
                # Only allow output->input, destination must be Belt or ExitBlock input
                if not (src_role == 'output' and dst_role == 'input' and isinstance(dst_obj, (Belt, ExitBlock))):
                    # invalid; discard rubber line
                    path_tmp = self.rubber
                    self.rubber = None
                    self.scene.removeItem(path_tmp)
                    ev.accept(); return
                # Compute path between correct ports
                s = src_obj.p_out.scenePos() if isinstance(src_obj, (Belt, BoxGenerator)) else scene_pos
                d = dst_obj.p_in.scenePos()
                p = QPainterPath(s)
                mid = (s + d) / 2
                ctrl = QPointF(mid.x(), s.y())
                p.cubicTo(ctrl, QPointF(mid.x(), d.y()), d)
                path = QGraphicsPathItem(p)
                path.setPen(QPen(Qt.darkGreen, 2))
                path.setFlag(QGraphicsItem.ItemIsSelectable, True)
                path.setFlag(QGraphicsItem.ItemIsFocusable, True)
                self.scene.addItem(path)
                # Store visual + logical link
                self.links.append((path, getattr(src_obj, 'p_out', None), dst_obj.p_in))
                self.links_data.append({
                    "pathItem": path,
                    "src_belt": src_obj,   # may be Belt or BoxGenerator
                    "src_port": 'output',
                    "dst_belt": dst_obj,
                    "dst_port": 'input'
                })
                path.setToolTip(f"{self._label_of(src_obj)} output -> {self._label_of(dst_obj)} input")
                # Rebuild downstream cache
                self._rebuild_downstream()
                self.refresh_link_tooltips()
                self.refresh_port_indicators()
                self.anim_path = path.path()
                self.anim_t = 0.0

            # Clean up rubber
            self.scene.removeItem(self.rubber)
            self.rubber = None
            ev.accept(); return
        super().mouseReleaseEvent(ev)
    def on_selection_changed(self):
        # Highlight selected links and attach red anim dot to the (last) selected link
        selected_paths = []
        for e in self.links_data:
            pathItem = e["pathItem"]
            if pathItem.isSelected():
                pathItem.setPen(QPen(Qt.blue, 3, Qt.DashLine))
                selected_paths.append(pathItem)
            else:
                pathItem.setPen(QPen(Qt.darkGreen, 2))
        # attach/redraw anim dot on last selected path (if any)
        if selected_paths:
            self.anim_path = selected_paths[-1].path()
            self.anim_t = 0.0
        else:
            self.anim_path = None

    def delete_selected_nodes(self):
        # collect selected belts/exits
        selected = [it for it in self.scene.selectedItems() if isinstance(it, (Belt, ExitBlock))]
        if not selected:
            return
        # remove any links connected to them
        to_remove_links = []
        for e in list(self.links_data):
            if e["src_belt"] in selected or e["dst_belt"] in selected:
                to_remove_links.append(e)
        for e in to_remove_links:
            if e["pathItem"] is not None:
                self.scene.removeItem(e["pathItem"])
            if e in self.links_data:
                self.links_data.remove(e)
        # remove boxes sitting on selected belts
        if hasattr(self, 'boxes'):
            self.boxes = [bx for bx in self.boxes if bx.get("belt") not in selected]
        # finally remove the nodes
        for it in selected:
            self.scene.removeItem(it)
        self._rebuild_downstream()
        self.refresh_link_tooltips()
        self.refresh_port_indicators()
        # update paths to be safe
        self.update_all_link_paths()
        to_remove = []
        for e in list(self.links_data):
            pathItem = e["pathItem"]
            if pathItem.isSelected():
                to_remove.append(e)
        if not to_remove:
            return
        # remove visuals and entries
        for e in to_remove:
            pathItem = e["pathItem"]
            if self.anim_path is not None and self.anim_path == pathItem.path():
                self.anim_path = None
            self.scene.removeItem(pathItem)
            if e in self.links_data:
                self.links_data.remove(e)
        # also prune from legacy self.links if present
        self.links = [t for t in self.links if t[0] not in [e["pathItem"] for e in to_remove]] if hasattr(self, 'links') else []
        self._rebuild_downstream()
        self.refresh_link_tooltips()
        self.refresh_port_indicators()

    def delete_selected_links(self):
        # collect selected link path items
        to_remove = []
        for e in list(self.links_data):
            pathItem = e["pathItem"]
            if pathItem.isSelected():
                to_remove.append(e)
        if not to_remove:
            return
        # remove visuals and entries
        for e in to_remove:
            pathItem = e["pathItem"]
            # detach any animation path reference
            if hasattr(self, 'anim_path') and self.anim_path is not None and hasattr(pathItem, 'path'):
                try:
                    if self.anim_path == pathItem.path():
                        self.anim_path = None
                except Exception:
                    pass
            if pathItem is not None:
                self.scene.removeItem(pathItem)
            if e in self.links_data:
                self.links_data.remove(e)
        # also prune from legacy self.links if present
        if hasattr(self, 'links'):
            dead_paths = {e["pathItem"] for e in to_remove}
            self.links = [t for t in self.links if t[0] not in dead_paths]
        # rebuild caches and visuals
        self._rebuild_downstream()
        self.refresh_link_tooltips()
        self.refresh_port_indicators()
        self.update_all_link_paths()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # delete links if any selected, otherwise delete nodes
            had_links = False
            for e in self.links_data:
                if e["pathItem"].isSelected():
                    had_links = True
                    break
            if had_links:
                self.delete_selected_links()
            else:
                self.delete_selected_nodes()
            ev.accept(); return
        super().keyPressEvent(ev)

    def update_all_link_paths(self):
        for entry in self.links_data:
            pathItem = entry["pathItem"]
            src_obj = entry["src_belt"]
            dst_obj = entry["dst_belt"]
            if src_obj is None or dst_obj is None:
                continue
            s = src_obj.p_out.scenePos() if hasattr(src_obj, 'p_out') else src_obj.p_in.scenePos()
            d = dst_obj.p_in.scenePos()
            p = QPainterPath(s)
            mid = (s + d) / 2
            ctrl = QPointF(mid.x(), s.y())
            p.cubicTo(ctrl, QPointF(mid.x(), d.y()), d)
            pathItem.setPath(p)
        self.downstream = []
        for e in self.links_data:
            self.downstream.append((e["src_belt"], e["dst_belt"]))

    def mouseDoubleClickEvent(self, ev):
        item = self.itemAt(ev.pos())
        # If the user double-clicks a child (title/port/progress bar),
        # climb to the logical parent (Belt or BoxGenerator)
        target = item
        while target is not None and not isinstance(target, (Belt, BoxGenerator)):
            target = target.parentItem()
        if target is not None:
            item = target
        if isinstance(item, Belt):
            # Build settings dialog
            dlg = QDialog(self)
            dlg.setWindowTitle("Band instellingen")
            lay = QVBoxLayout(dlg)

            # Title
            from PySide6.QtWidgets import QLineEdit, QSpinBox, QCheckBox, QLabel, QFormLayout, QDialogButtonBox, QPushButton
            form = QFormLayout()
            le_title = QLineEdit(item.label, dlg)
            sb_ticks = QSpinBox(dlg); sb_ticks.setRange(1, 100); sb_ticks.setValue(item.width_ticks)
            # variable inputs via MainWindow helpers (fallback to QLineEdit if absent)
            wnd = self.window()
            make_var_input = getattr(wnd, '_make_var_input', None)
            get_var_value = getattr(wnd, '_get_var_value', None)
            if callable(make_var_input):
                le_motor = make_var_input(dlg, item.motor_var)
            else:
                le_motor = QLineEdit(item.motor_var or "", dlg)
            cb_ft_in = QCheckBox("FT In aanwezig", dlg); cb_ft_in.setChecked(getattr(item, 'ft_in_enabled', False))
            if callable(make_var_input):
                le_ft_in = make_var_input(dlg, getattr(item, 'ft_in_var', '') or None)
            else:
                le_ft_in = QLineEdit(getattr(item, 'ft_in_var', '') or '', dlg)
            le_ft_in.setEnabled(cb_ft_in.isChecked())
            cb_ft_out = QCheckBox("FT Out aanwezig", dlg); cb_ft_out.setChecked(getattr(item, 'ft_out_enabled', False))
            if callable(make_var_input):
                le_ft_out = make_var_input(dlg, getattr(item, 'ft_out_var', '') or None)
            else:
                le_ft_out = QLineEdit(getattr(item, 'ft_out_var', '') or '', dlg)
            le_ft_out.setEnabled(cb_ft_out.isChecked())
            cb_ft_in.toggled.connect(lambda v: le_ft_in.setEnabled(v))
            cb_ft_out.toggled.connect(lambda v: le_ft_out.setEnabled(v))
            form.addRow(QLabel("Titel:"), le_title)
            form.addRow(QLabel("Breedte (ticks):"), sb_ticks)
            form.addRow(QLabel("Motor variabele:"), le_motor)
            form.addRow(cb_ft_in)
            form.addRow(QLabel("FT In variabele:"), le_ft_in)
            form.addRow(cb_ft_out)
            form.addRow(QLabel("FT Out variabele:"), le_ft_out)
            lay.addLayout(form)

            # Test sensor button (for FT In/Out, test both if enabled)
            btn_test = QPushButton("Test sensor puls", dlg)
            lay.addWidget(btn_test)

            # Buttons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
            lay.addWidget(buttons)

            def on_ok():
                item.set_label(le_title.text().strip() or item.label)
                item.resize_for_ticks(sb_ticks.value())
                if callable(get_var_value):
                    item.motor_var = get_var_value(le_motor)
                else:
                    item.motor_var = (le_motor.text().strip() or None)
                if item.motor_var and item.motor_var not in VARS:
                    VARS[item.motor_var] = False
                item.set_sensors_enabled(cb_ft_in.isChecked(), cb_ft_out.isChecked())
                if callable(get_var_value):
                    item.ft_in_var = get_var_value(le_ft_in)
                    item.ft_out_var = get_var_value(le_ft_out)
                else:
                    item.ft_in_var = (le_ft_in.text().strip() or None)
                    item.ft_out_var = (le_ft_out.text().strip() or None)
                for var in (item.ft_in_var, item.ft_out_var):
                    if var and var not in VARS:
                        VARS[var] = False
                item.update_sensor_visual()
                self.refresh_link_tooltips()
                self.refresh_port_indicators()
                dlg.accept()

            def on_cancel():
                dlg.reject()

            def on_test():
                # quick pulse for 300 ms for FT In and FT Out if enabled
                if item.ft_in_enabled:
                    item.ft_in_state = True
                    if item.ft_in_var:
                        VARS[item.ft_in_var] = True
                if item.ft_out_enabled:
                    item.ft_out_state = True
                    if item.ft_out_var:
                        VARS[item.ft_out_var] = True
                item.update_sensor_visual()
                QTimer.singleShot(300, lambda: _sensor_off_both(item))

            def _sensor_off_both(belt):
                if belt.ft_in_enabled:
                    belt.ft_in_state = False
                    if belt.ft_in_var:
                        VARS[belt.ft_in_var] = False
                if belt.ft_out_enabled:
                    belt.ft_out_state = False
                    if belt.ft_out_var:
                        VARS[belt.ft_out_var] = False
                belt.update_sensor_visual()

            btn_test.clicked.connect(on_test)
            buttons.accepted.connect(on_ok)
            buttons.rejected.connect(on_cancel)
            dlg.exec()
            ev.accept(); return
        elif isinstance(item, ExitBlock):
            dlg = QDialog(self)
            dlg.setWindowTitle("Exit instellingen")
            lay = QVBoxLayout(dlg)
            from PySide6.QtWidgets import QLineEdit, QSpinBox, QCheckBox, QLabel, QFormLayout, QDialogButtonBox
            form = QFormLayout()
            le_title = QLineEdit(item.label, dlg)
            sb_capacity = QSpinBox(dlg); sb_capacity.setRange(0, 999); sb_capacity.setValue(int(getattr(item, 'capacity', 3)))
            sb_dwell = QSpinBox(dlg); sb_dwell.setRange(0, 600000); sb_dwell.setSingleStep(100); sb_dwell.setSuffix(" ms"); sb_dwell.setValue(int(getattr(item, 'dwell_ms', 2000)))
            cb_ft_in = QCheckBox("FT In aanwezig", dlg); cb_ft_in.setChecked(getattr(item, 'ft_in_enabled', False))
            wnd = self.window()
            make_var_input = getattr(wnd, '_make_var_input', None)
            get_var_value = getattr(wnd, '_get_var_value', None)
            if callable(make_var_input):
                le_ft_in = make_var_input(dlg, getattr(item, 'ft_in_var', '') or None)
            else:
                le_ft_in = QLineEdit(getattr(item, 'ft_in_var', '') or '', dlg)
            le_ft_in.setEnabled(cb_ft_in.isChecked())
            cb_ft_out = QCheckBox("FT Out aanwezig", dlg); cb_ft_out.setChecked(getattr(item, 'ft_out_enabled', False))
            if callable(make_var_input):
                le_ft_out = make_var_input(dlg, getattr(item, 'ft_out_var', '') or None)
            else:
                le_ft_out = QLineEdit(getattr(item, 'ft_out_var', '') or '', dlg)
            le_ft_out.setEnabled(cb_ft_out.isChecked())
            cb_ft_in.toggled.connect(lambda v: le_ft_in.setEnabled(v))
            cb_ft_out.toggled.connect(lambda v: le_ft_out.setEnabled(v))
            form.addRow(QLabel("Titel:"), le_title)
            form.addRow(QLabel("Capaciteit:"), sb_capacity)
            form.addRow(QLabel("Dwell tijd:"), sb_dwell)
            form.addRow(cb_ft_in)
            form.addRow(QLabel("FT In variabele:"), le_ft_in)
            form.addRow(cb_ft_out)
            form.addRow(QLabel("FT Out variabele:"), le_ft_out)
            lay.addLayout(form)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
            lay.addWidget(buttons)
            def on_ok():
                item.set_label(le_title.text().strip() or item.label)
                item.apply_capacity(int(sb_capacity.value()))
                item.dwell_ms = int(sb_dwell.value())
                item._update_timer_text()
                item.set_sensors_enabled(cb_ft_in.isChecked(), cb_ft_out.isChecked())
                if callable(get_var_value):
                    item.ft_in_var = get_var_value(le_ft_in)
                    item.ft_out_var = get_var_value(le_ft_out)
                else:
                    item.ft_in_var = (le_ft_in.text().strip() or None)
                    item.ft_out_var = (le_ft_out.text().strip() or None)
                for var in (item.ft_in_var, item.ft_out_var):
                    if var and var not in VARS:
                        VARS[var] = False
                item.update_sensor_visual()
                self.refresh_link_tooltips()
                self.refresh_port_indicators()
                dlg.accept()
            def on_cancel():
                dlg.reject()
            buttons.accepted.connect(on_ok)
            buttons.rejected.connect(on_cancel)
            dlg.exec()
            ev.accept(); return
        super().mouseDoubleClickEvent(ev)

    def _sensor_off(self, item: Belt):
        item.sensor_state = False
        if item.sensor_var:
            VARS[item.sensor_var] = False
        item.update_sensor_visual()

    def tick(self):
        # Update generator timer and possibly spawn a single box only when downstream is free
        dt_ms = int(16 * self.sim_speed)
        if getattr(self, 'generator', None) is not None:
            # bepaal eerste downstream node vanaf de generator (Belt of ExitBlock)
            next_nodes = [dst for (src, dst) in self.downstream if src is self.generator]
            first_dst = next_nodes[0] if next_nodes else None

            # kun je nu spawnen?
            if isinstance(first_dst, Belt):
                can_spawn_now = not self.belt_has_box(first_dst)
            elif isinstance(first_dst, ExitBlock):
                can_spawn_now = first_dst.can_accept()
            else:
                can_spawn_now = False

            # UI: geblokkeerd = progressbar vol en timer pauzeert
            self.generator.blocked = self.generator_blocked or (not can_spawn_now and self.generator.ready_to_spawn())

            # voortgang bijwerken
            self.generator.tick(dt_ms)

            # spawn-momenten
            if self.generator_blocked and can_spawn_now:
                # eerder geblokkeerd, nu vrij -> spawn nu
                if isinstance(first_dst, Belt):
                    # Fill the cell visually: use dimensions matching the belt cell
                    cell_h = 80 - 28 - 20  # same as belt's inner band height
                    cell_w = TICK_PX - 16  # match one tick width minus margins
                    box_item = QGraphicsRectItem(0, 0, cell_w, cell_h)
                    box_item.setBrush(QBrush(Qt.blue))
                    box_item.setPen(QPen(Qt.black, 1))
                    self.scene.addItem(box_item)
                    self.boxes.append({"item": box_item, "belt": first_dst, "t": 0.0})
                elif isinstance(first_dst, ExitBlock):
                    box_item = QGraphicsRectItem(-7, -5, 14, 10)
                    box_item.setBrush(QBrush(Qt.blue))
                    box_item.setPen(QPen(Qt.black, 1))
                    # niet in self.boxes; exit beheert deze doos
                    first_dst.add_box(box_item)
                self.generator_blocked = False
                self.generator.blocked = False
                self.generator.elapsed_ms = 0

            elif not self.generator_blocked and self.generator.ready_to_spawn():
                if can_spawn_now:
                    if isinstance(first_dst, Belt):
                        cell_h = 80 - 28 - 20  # same as belt's inner band height
                        cell_w = TICK_PX - 16  # match one tick width minus margins
                        box_item = QGraphicsRectItem(0, 0, cell_w, cell_h)
                        box_item.setBrush(QBrush(Qt.blue))
                        box_item.setPen(QPen(Qt.black, 1))
                        self.scene.addItem(box_item)
                        self.boxes.append({"item": box_item, "belt": first_dst, "t": 0.0})
                        self.generator.elapsed_ms = 0
                    elif isinstance(first_dst, ExitBlock):
                        box_item = QGraphicsRectItem(-7, -5, 14, 10)
                        box_item.setBrush(QBrush(Qt.blue))
                        box_item.setPen(QPen(Qt.black, 1))
                        first_dst.add_box(box_item)
                        self.generator.elapsed_ms = 0
                else:
                    # kan nog niet -> blokkeren tot vrij
                    self.generator_blocked = True
                    self.generator.blocked = True

        # Move boxes across belts if motor is on
        speed_per_sec = 0.25 * self.sim_speed  # fraction of belt length per second
        dt = 0.016 * self.sim_speed
        for bx in list(self.boxes):
            belt = bx["belt"]
            motor_on = VARS.get(belt.motor_var, False) if belt.motor_var else False
            if motor_on:
                bx["t"] += speed_per_sec * dt
            # reached end?
            if bx["t"] >= 1.0:
                downs = [dst for (src, dst) in self.downstream if src is belt]
                if downs:
                    next_obj = downs[0]
                    if isinstance(next_obj, Belt):
                        if not self.belt_has_box(next_obj):
                            bx["belt"] = next_obj
                            bx["t"] = 0.0
                            belt = bx["belt"]
                        else:
                            bx["t"] = 0.999
                    elif isinstance(next_obj, ExitBlock):
                        if next_obj.can_accept():
                            next_obj.add_box(bx["item"])
                            self.boxes.remove(bx)
                            continue
                        else:
                            bx["t"] = 0.999
                    else:
                        self.scene.removeItem(bx["item"])
                        self.boxes.remove(bx)
                        continue
                else:
                    self.scene.removeItem(bx["item"])
                    self.boxes.remove(bx)
                    continue
            # snap visueel naar cellen (middenband)
            r = belt.rect()
            cell_w = (r.width() - 16) / max(1, belt.width_ticks)
            # middenband y tussen 28..(h-20)
            band_top = 28
            band_bottom = r.height() - 20
            t_clamped = max(0.0, min(0.999, bx["t"]))
            cell_idx = int(t_clamped * belt.width_ticks)
            # For full cell-filling blue box:
            px = belt.scenePos().x() + 8 + cell_idx * cell_w
            py = belt.scenePos().y() + band_top
            bx["item"].setRect(0, 0, cell_w, band_bottom - band_top)
            bx["item"].setPos(QPointF(px, py))
            # Update belt FT In/Out states based on current box position
            if hasattr(belt, 'width_ticks'):
                tick_idx = int(bx["t"] * belt.width_ticks)
                belt.ft_in_state = (tick_idx <= 0 and self.belt_has_box(belt))
                belt.ft_out_state = (tick_idx >= max(0, belt.width_ticks - 1))
                belt.update_sensor_visual()
        # Update occupancy indicators on all belts
        for sc_item in self.scene.items():
            if isinstance(sc_item, Belt):
                sc_item.has_box = self.belt_has_box(sc_item)
                sc_item.update_box_indicator()

        # Update exit blocks dwell timers
        for sc_item in self.scene.items():
            if isinstance(sc_item, ExitBlock):
                sc_item.tick(int(16 * self.sim_speed))

        # (removed old placeholder pulse for single sensor)

        # optioneel: links updaten als belts bewegen
        self.update_all_link_paths()

    @staticmethod
    def point_on_path(path: QPainterPath, t: float) -> QPointF:
        # benader via lengte
        length = path.length()
        pos = path.pointAtPercent(t) if length == 0 else path.pointAtPercent(t)
        return pos

    def _label_of(self, obj) -> str:
        if isinstance(obj, Belt):
            return obj.label
        if isinstance(obj, BoxGenerator):
            # Prefer the visible title text if present
            if hasattr(obj, 'title') and isinstance(obj.title, QGraphicsSimpleTextItem):
                return obj.title.text()
            return "Box Generator"
        # Fallback for any other object types
        return getattr(obj, 'label', str(obj))

    def refresh_link_tooltips(self):
        for entry in self.links_data:
            pathItem = entry["pathItem"]
            src = entry["src_belt"]
            dst = entry["dst_belt"]
            src_name = self._label_of(src)
            dst_name = self._label_of(dst)
            pathItem.setToolTip(f"{src_name} {entry['src_port']} -> {dst_name} {entry['dst_port']}")

    def refresh_port_indicators(self):
        # Reset ports and tooltips for Belts and Exits
        white = QBrush(Qt.white)
        green = QBrush(Qt.green)
        conn_map = {}
        for item in self.scene.items():
            if isinstance(item, Belt):
                conn_map[item] = {"input": [], "output": []}
                item.p_in.setBrush(white)
                item.p_out.setBrush(white)
                item.p_in.setToolTip("Input: niet verbonden")
                item.p_out.setToolTip("Output: niet verbonden")
            elif isinstance(item, ExitBlock):
                conn_map[item] = {"input": []}
                item.p_in.setBrush(white)
                item.p_in.setToolTip("Input: niet verbonden")
        # Fill connections from links_data
        for entry in self.links_data:
            sb = entry["src_belt"]; sp = entry["src_port"]
            db = entry["dst_belt"]; dp = entry["dst_port"]
            if sb in conn_map and sp in conn_map[sb]:
                conn_map[sb][sp].append(f"→ {self._label_of(db)} ({dp})")
            if db in conn_map and dp in conn_map[db]:
                conn_map[db][dp].append(f"← {self._label_of(sb)} ({sp})")
        # Apply visuals and tooltips
        for obj, ports in conn_map.items():
            if "input" in ports and ports["input"]:
                obj.p_in.setBrush(green)
                obj.p_in.setToolTip("Input: verbonden met\n" + "\n".join(ports["input"]))
            if isinstance(obj, Belt) and ports.get("output"):
                obj.p_out.setBrush(green)
                obj.p_out.setToolTip("Output: verbonden met\n" + "\n".join(ports["output"]))

    def _rebuild_downstream(self):
        """Rebuild cached downstream map (list of (src_obj, dst_obj)).
        This is safe to call after deletions; it skips entries whose path or
        endpoints have been removed.
        """
        ds = []
        for e in list(getattr(self, 'links_data', [])):
            src = e.get("src_belt")
            dst = e.get("dst_belt")
            pathItem = e.get("pathItem")
            # drop entries whose visuals were already deleted
            if pathItem is not None and pathItem.scene() is None:
                try:
                    self.links_data.remove(e)
                except ValueError:
                    pass
                continue
            if src is None or dst is None:
                continue
            ds.append((src, dst))
        self.downstream = ds

    def clear_line_boxes(self):
        # Remove all boxes that are currently on belts (not inside Exit blocks)
        if not hasattr(self, 'boxes') or not self.boxes:
            return
        for bx in list(self.boxes):
            itm = bx.get("item")
            if itm is not None:
                try:
                    self.scene.removeItem(itm)
                except Exception:
                    pass
            # remove from list
            try:
                self.boxes.remove(bx)
            except ValueError:
                pass
        # Update belt occupancy indicators
        for sc_item in self.scene.items():
            if isinstance(sc_item, Belt):
                sc_item.has_box = False
                sc_item.update_box_indicator()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Conveyor UI – drag, link, animate")
        central = QWidget(self)
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)

        # Top bar with a Toolbox button
        topbar = QHBoxLayout()
        self.btn_toolbox = QPushButton("Toolbox", self)
        self.btn_toolbox.clicked.connect(self.open_toolbox)
        topbar.addWidget(self.btn_toolbox)

        self.btn_new = QPushButton("Nieuw", self)
        self.btn_open = QPushButton("Open...", self)
        self.btn_save = QPushButton("Opslaan als...", self)
        self.btn_new.clicked.connect(self.new_project)
        self.btn_open.clicked.connect(self.open_project)
        self.btn_save.clicked.connect(self.save_project_as)
        topbar.addWidget(self.btn_new)
        topbar.addWidget(self.btn_open)
        topbar.addWidget(self.btn_save)
        self.current_path = None

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

        # PLC instellingen en verbinden
        self.btn_plc_settings = QPushButton("PLC instellingen", self)
        self.btn_plc_settings.clicked.connect(self.open_plc_settings)
        topbar.addWidget(self.btn_plc_settings)

        self.btn_connect = QPushButton("Verbind", self)
        self.btn_connect.clicked.connect(self.start_connection)
        topbar.addWidget(self.btn_connect)

        self.lbl_status = QLabel("Snap7: Not connected", self)
        topbar.addWidget(self.lbl_status)

        # Tick/simulation speed
        # imports moved to module scope to avoid shadowing names
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

        # --- DB / Snap7 state ---
        self.db_block = None  # type: ignore[assignment]
        self.db_definition_path: str | None = None
        self._db_dialog: QDialog | None = None
        self._db_tree: QTreeWidget | None = None
        self._snap_client = None
        self._snap_timer = QTimer(self)
        self._snap_timer.timeout.connect(self._poll_snap7)
        # PLC connection parameters
        self.plc_ip = "192.168.0.1"
        self.plc_rack = 0
        self.plc_slot = 1

    def all_belts_on(self):
        # Set all belts' motor_var to True (create var if needed)
        for item in self.view.scene.items():
            if isinstance(item, Belt) and item.motor_var:
                VARS[item.motor_var] = True

    def gen_start(self):
        if getattr(self.view, 'generator', None) is not None:
            self.view.generator.start()

    def gen_stop(self):
        if getattr(self.view, 'generator', None) is not None:
            self.view.generator.stop()

    def clear_all_boxes(self):
        # Remove all boxes on the conveyor line (moving between nodes)
        if hasattr(self, 'view') and hasattr(self.view, 'clear_line_boxes'):
            self.view.clear_line_boxes()

    def on_speed_changed(self, val: float):
        # Update simulation speed multiplier
        self.view.sim_speed = max(0.1, float(val))

    def open_toolbox(self):
        dlg = ToolboxDialog(self)
        if dlg.exec() == QDialog.Accepted:
            choice = dlg.selected_part()
            if choice == "Belt":
                self.view.add_belt()
                self.view.refresh_link_tooltips()
            elif choice == "Exit":
                self.view.add_exit()
                self.view.refresh_link_tooltips()

    # ---- Helpers: variable selector from DB ----
    def _make_var_input(self, parent, initial: str | None):
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
        if isinstance(widget, QComboBox):
            txt = widget.currentText().strip()
            return txt or None
        if isinstance(widget, QLineEdit):
            txt = widget.text().strip()
            return txt or None
        return None

    # ---- DB Viewer ----
    def open_db_viewer(self):
        if self._db_dialog is not None:
            try:
                if not self._db_dialog.isVisible():
                    self._db_dialog.show()
                self._db_dialog.raise_()
                self._db_dialog.activateWindow()
                self._refresh_db_view()
                return
            except Exception:
                self._db_dialog = None

        dlg = QDialog(self)
        dlg.setWindowTitle("DB Viewer")
        v = QVBoxLayout(dlg)
        row = QHBoxLayout()
        btn_load = QPushButton("DB laden...", dlg)
        btn_load.clicked.connect(self._choose_db_definition)
        btn_refresh = QPushButton("Refresh", dlg)
        btn_refresh.clicked.connect(self._refresh_db_view)
        row.addWidget(btn_load)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        v.addLayout(row)
        tree = QTreeWidget(dlg)
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Variable", "Value"])
        v.addWidget(tree)
        self._db_tree = tree
        self._db_dialog = dlg
        try:
            # Clear our handle when dialog is closed so it can be reopened cleanly
            dlg.finished.connect(lambda _=None: setattr(self, '_db_dialog', None))
        except Exception:
            pass
        self._refresh_db_view()
        dlg.resize(520, 500)
        dlg.show()

    def _choose_db_definition(self):
        path, _ = QFileDialog.getOpenFileName(self, "Kies TIA DB (.db)", "", "TIA DB (*.db)")
        if not path:
            return
        if TIA_S7DataBlock is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fout", "TIA_Db module niet beschikbaar")
            return
        try:
            # Default to DB1 unless you prefer a prompt
            dbn = 1
            self.db_block = TIA_S7DataBlock.from_definition_file(path=path, db_number=dbn, nesting_depth_to_skip=1)
            self.db_definition_path = path
            self._refresh_db_view()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fout", f"Kon DB niet laden:\n{e}")

    def _refresh_db_view(self):
        if self._db_tree is None or self.db_block is None:
            return
        self._db_tree.clear()
        names = list(getattr(self.db_block, 'data', {}).keys())
        for name in names:
            try:
                val = self.db_block[name]
            except Exception:
                val = "?"
            QTreeWidgetItem(self._db_tree, [name, self._fmt_val(val)])
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
        if isinstance(v, bool):
            return "True" if v else "False"
        if isinstance(v, float):
            return f"{v:.4g}"
        return str(v)

    # ---- PLC settings + connection ----
    def open_plc_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("PLC instellingen")
        v = QVBoxLayout(dlg)
        row_ip = QHBoxLayout(); v.addLayout(row_ip)
        row_ip.addWidget(QLabel("IP:", dlg))
        ip_edit = QLineEdit(self.plc_ip, dlg)
        row_ip.addWidget(ip_edit)
        row_rack = QHBoxLayout(); v.addLayout(row_rack)
        row_rack.addWidget(QLabel("Rack:", dlg))
        sp_rack = QSpinBox(dlg); sp_rack.setRange(0, 10); sp_rack.setValue(int(self.plc_rack))
        row_rack.addWidget(sp_rack)
        row_slot = QHBoxLayout(); v.addLayout(row_slot)
        row_slot.addWidget(QLabel("Slot:", dlg))
        sp_slot = QSpinBox(dlg); sp_slot.setRange(0, 10); sp_slot.setValue(int(self.plc_slot))
        row_slot.addWidget(sp_slot)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg)
        v.addWidget(buttons)
        def accept():
            self.plc_ip = ip_edit.text().strip() or self.plc_ip
            self.plc_rack = int(sp_rack.value())
            self.plc_slot = int(sp_slot.value())
            dlg.accept()
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def start_connection(self):
        # Explicit user-triggered connect
        if snap7 is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fout", "snap7 module niet beschikbaar")
            self.lbl_status.setText("Snap7: Not connected")
            return
        # create client if needed
        if self._snap_client is None:
            try:
                self._snap_client = snap7.client.Client()
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Fout", f"Kon snap7 client maken:\n{e}")
                self._snap_client = None
                self.lbl_status.setText("Snap7: Not connected")
                return
        # attempt connect once
        ok = False
        try:
            self._snap_client.connect(self.plc_ip, int(self.plc_rack), int(self.plc_slot))
            ok = bool(self._snap_client.get_connected())
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
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
        if self._snap_client is None or self.db_block is None:
            return
        try:
            if not self._snap_client.get_connected():
                # keep status updated and do nothing further
                self.lbl_status.setText("Snap7: Not connected")
                return
            self.lbl_status.setText("Snap7: Connected")
            if self._snap_client.get_connected():
                buf = self._snap_client.db_read(db_number=self.db_block.db_number, start=0, size=self.db_block.db_size)
                # Update buffer in place
                self.db_block.buffer = bytearray(buf)
                # live refresh if dialog open
                if self._db_dialog is not None and self._db_dialog.isVisible():
                    self._refresh_db_view()
        except Exception:
            # keep trying silently
            self.lbl_status.setText("Snap7: Not connected")

    def new_project(self):
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
        # Recreate always-present items (generator + anim dot)
        self.view.generator = BoxGenerator(10, 10)
        self.view.scene.addItem(self.view.generator)
        # Red anim dot
        self.view.dot = QGraphicsEllipseItem(-4, -4, 8, 8)
        self.view.dot.setBrush(QBrush(Qt.red))
        self.view.dot.setZValue(100)
        self.view.scene.addItem(self.view.dot)
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
        path, _ = QFileDialog.getSaveFileName(self, "Project opslaan", "", "Conveyor Project (*.json)")
        if not path:
            return
        self.save_to_path(path)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Project openen", "", "Conveyor Project (*.json)")
        if not path:
            return
        self.load_from_path(path)

    def save_to_path(self, path: str):
        # collect belts
        belts = []
        id_map = {}
        for item in self.view.scene.items():
            if isinstance(item, Belt):
                bid = getattr(item, 'bid', None)
                if bid is None:
                    continue
                id_map[item] = bid
                x = item.scenePos().x()
                y = item.scenePos().y()
                r = item.rect()
                belts.append({
                    "id": bid,
                    "label": item.label,
                    "x": x, "y": y,
                    "w": r.width(), "h": r.height(),
                    "width_ticks": getattr(item, 'width_ticks', 1),
                    "motor_var": getattr(item, 'motor_var', None),
                    "ft_in_enabled": getattr(item, 'ft_in_enabled', False),
                    "ft_in_var": getattr(item, 'ft_in_var', None),
                    "ft_out_enabled": getattr(item, 'ft_out_enabled', False),
                    "ft_out_var": getattr(item, 'ft_out_var', None),
                })
        # collect exits
        exits = []
        for item in self.view.scene.items():
            if isinstance(item, ExitBlock):
                xid = getattr(item, 'xid', None)
                if xid is None:
                    continue
                id_map[item] = xid
                x = item.scenePos().x()
                y = item.scenePos().y()
                r = item.rect()
                exits.append({
                    "id": xid,
                    "label": item.label,
                    "x": x, "y": y,
                    "w": r.width(), "h": r.height(),
                    "ft_in_enabled": getattr(item, 'ft_in_enabled', False),
                    "ft_in_var": getattr(item, 'ft_in_var', None),
                    "ft_out_enabled": getattr(item, 'ft_out_enabled', False),
                    "ft_out_var": getattr(item, 'ft_out_var', None),
                    "capacity": int(getattr(item, 'capacity', 3)),
                    "dwell_ms": int(getattr(item, 'dwell_ms', 2000))
                })
        # collect links
        links = []
        for entry in self.view.links_data:
            src_obj = entry["src_belt"]
            dst_obj = entry["dst_belt"]
            src_id = 0 if isinstance(src_obj, BoxGenerator) else id_map.get(src_obj)
            dst_id = id_map.get(dst_obj)
            links.append({
                "src_id": src_id,
                "src_port": entry["src_port"],
                "dst_id": dst_id,
                "dst_port": entry["dst_port"]
            })
        import json
        payload = {
            "belts": belts,
            "exits": exits,
            "links": links
        }
        # persist DB info if available
        try:
            if self.db_block is not None and self.db_definition_path:
                payload["db"] = {
                    "definition_path": self.db_definition_path,
                    "db_number": int(getattr(self.db_block, 'db_number', 0)),
                    "buffer": list(getattr(self.db_block, 'buffer', bytearray()))
                }
        except Exception:
            pass
        if getattr(self.view, 'generator', None) is not None:
            payload["generator"] = {
                "interval_ms": self.view.generator.interval_ms,
                "x": self.view.generator.scenePos().x(),
                "y": self.view.generator.scenePos().y(),
                "running": getattr(self.view.generator, 'running', True)
            }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        self.current_path = path
        self.setWindowTitle(f"Conveyor UI – {path}")
        self.view.refresh_port_indicators()

    def load_from_path(self, path: str):
        import json
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # reset
        self.view.scene.clear()
        self.view.links.clear()
        self.view.links_data.clear()
        self.view.next_belt_id = 1
        self.view.next_belt_num = 1
        self.view.generator_blocked = False
        # Recreate generator (scene.clear() already deleted old items)
        gen_data = data.get("generator")
        # Ensure we drop any stale Python reference
        self.view.generator = None
        if isinstance(gen_data, dict):
            gx = float(gen_data.get("x", 10.0)); gy = float(gen_data.get("y", 10.0))
            self.view.generator = BoxGenerator(gx, gy)
            self.view.generator.set_interval(int(gen_data.get("interval_ms", 1500)))
            if bool(gen_data.get("running", True)):
                self.view.generator.start()
            else:
                self.view.generator.stop()
            self.view.scene.addItem(self.view.generator)
        # recreate belts keeping ids
        id_to_belt = {}
        for b in data.get("belts", []):
            belt = Belt(b["x"], b["y"], b.get("w",TICK_PX), b.get("h",80), b.get("label","Band"))
            belt.resize_for_ticks(int(b.get("width_ticks", 1)))
            mv = b.get("motor_var")
            belt.motor_var = mv if mv else None
            belt.ft_in_enabled = bool(b.get("ft_in_enabled", False))
            belt.ft_in_var = b.get("ft_in_var") or None
            belt.ft_out_enabled = bool(b.get("ft_out_enabled", False))
            belt.ft_out_var = b.get("ft_out_var") or None
            belt.set_sensors_enabled(belt.ft_in_enabled, belt.ft_out_enabled)
            for var in (belt.ft_in_var, belt.ft_out_var):
                if var and var not in VARS:
                    VARS[var] = False
            if belt.motor_var and belt.motor_var not in VARS:
                VARS[belt.motor_var] = False
            belt.update_sensor_visual()
            belt.bid = b["id"]
            id_to_belt[belt.bid] = belt
            self.view.scene.addItem(belt)
            # Ensure slot visuals are built after the item is in the scene
            if hasattr(belt, "_rebuild_slots"):
                belt._rebuild_slots()
            # update counters so next created is higher
            self.view.next_belt_id = max(self.view.next_belt_id, belt.bid + 1)
            # try to parse number from label for numbering continuity
            try:
                if belt.label.lower().startswith("band "):
                    n = int(belt.label.split(" ")[1])
                    self.view.next_belt_num = max(self.view.next_belt_num, n + 1)
            except Exception:
                pass
        if getattr(self.view, 'generator', None) is not None:
            id_to_belt[0] = self.view.generator
        # recreate exits keeping ids
        # ensure belts already populated id_to_belt
        for item in self.view.scene.items():
            if isinstance(item, Belt):
                id_to_belt[getattr(item, 'bid', None)] = item
        for ex in data.get("exits", []):
            exitb = ExitBlock(ex["x"], ex["y"], ex.get("w",180), ex.get("h",80), ex.get("label","Exit"))
            exitb.ft_in_enabled = bool(ex.get("ft_in_enabled", False))
            exitb.ft_in_var = ex.get("ft_in_var") or None
            exitb.ft_out_enabled = bool(ex.get("ft_out_enabled", False))
            exitb.ft_out_var = ex.get("ft_out_var") or None
            exitb.set_sensors_enabled(exitb.ft_in_enabled, exitb.ft_out_enabled)
            for var in (exitb.ft_in_var, exitb.ft_out_var):
                if var and var not in VARS:
                    VARS[var] = False
            exitb.apply_capacity(int(ex.get("capacity", 3)))
            exitb.dwell_ms = int(ex.get("dwell_ms", 2000))
            exitb.xid = ex["id"]
            self.view.scene.addItem(exitb)
            # Ensure slot visuals are built after the item is in the scene
            if hasattr(exitb, "_rebuild_slots"):
                exitb._rebuild_slots()
                if hasattr(exitb, "_refresh_fills_from_boxes"):
                    exitb._refresh_fills_from_boxes()
                if hasattr(exitb, "_update_timer_text"):
                    exitb._update_timer_text()
            id_to_belt[exitb.xid] = exitb
            self.view.next_exit_id = max(self.view.next_exit_id, exitb.xid + 1)
            try:
                if exitb.label.lower().startswith("exit "):
                    n = int(exitb.label.split(" ")[1])
                    self.view.next_exit_num = max(self.view.next_exit_num, n + 1)
            except Exception:
                pass
        # recreate links
        for lk in data.get("links", []):
            src = id_to_belt.get(lk["src_id"])
            dst = id_to_belt.get(lk["dst_id"])
            if not src or not isinstance(dst, (Belt, ExitBlock)):
                continue
            s = src.p_out.scenePos()
            d = dst.p_in.scenePos()
            p = QPainterPath(s)
            mid = (s + d) / 2
            ctrl = QPointF(mid.x(), s.y())
            p.cubicTo(ctrl, QPointF(mid.x(), d.y()), d)
            pathItem = QGraphicsPathItem(p)
            pathItem.setPen(QPen(Qt.darkGreen, 2))
            pathItem.setFlag(QGraphicsItem.ItemIsSelectable, True)
            pathItem.setFlag(QGraphicsItem.ItemIsFocusable, True)
            src_name = self.view._label_of(src)
            dst_name = self.view._label_of(dst)
            pathItem.setToolTip(f"{src_name} {lk['src_port']} -> {dst_name} {lk['dst_port']}")
            self.view.scene.addItem(pathItem)
            self.view.links_data.append({
                "pathItem": pathItem,
                "src_belt": src,
                "src_port": lk["src_port"],
                "dst_belt": dst,
                "dst_port": lk["dst_port"]
            })
        self.current_path = path
        self.setWindowTitle(f"Conveyor UI – {path}")
        self.view.refresh_link_tooltips()
        self.view.refresh_port_indicators()
        self.view._rebuild_downstream()

        # Restore DB if present (does not auto-connect; user triggers connect)
        try:
            dbinfo = data.get("db")
            if dbinfo and TIA_S7DataBlock is not None:
                defp = dbinfo.get("definition_path")
                dbn = dbinfo.get("db_number")
                if defp and dbn is not None:
                    self.db_block = TIA_S7DataBlock.from_definition_file(path=defp, db_number=int(dbn), nesting_depth_to_skip=1)
                    self.db_definition_path = defp
                    buf = dbinfo.get("buffer")
                    if isinstance(buf, list):
                        self.db_block.buffer = bytearray(buf)
        except Exception:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())