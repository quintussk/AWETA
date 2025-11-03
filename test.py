# file: belts_demo.py
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog, QListWidget, QDialogButtonBox, QFileDialog, QInputDialog, QGraphicsSimpleTextItem
import sys, math

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
    def __init__(self, x, y, w=220, h=60, label="Belt"):
        super().__init__(0, 0, w, h)
        self.setPos(x, y)
        self.setBrush(QBrush(Qt.lightGray))
        self.setPen(QPen(Qt.black, 2))
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable
        )
        # Ports (links/rechts)
        self.p_in  = Port(self, 0,  h/2)
        self.p_out = Port(self, w, h/2)
        self.label = label

        # Configurable properties
        self.width_ticks = 1  # default 1 tick breed
        self.motor_var: str | None = None
        self.sensor_enabled: bool = False
        self.sensor_var: str | None = None
        self.sensor_state: bool = False

        # Sensor indicator (top-right)
        self.sensor_item = QGraphicsEllipseItem(-5, -5, 10, 10, self)
        self.sensor_item.setBrush(QBrush(Qt.gray))
        self.sensor_item.setPen(QPen(Qt.black, 1))
        self.sensor_item.setVisible(False)

        # Ensure sizing/ports consistent with ticks
        self.resize_for_ticks(self.width_ticks)

        # Title label as child item
        self.title_item = QGraphicsSimpleTextItem(self)
        self.title_item.setText(self.label)
        self.title_item.setPos(8, 6)

    def set_label(self, text: str):
        self.label = text
        if hasattr(self, 'title_item') and self.title_item is not None:
            self.title_item.setText(self.label)

    def resize_for_ticks(self, ticks: int):
        self.width_ticks = max(1, int(ticks))
        # update rect size to ticks * TICK_PX keeping height
        r = self.rect()
        new_w = self.width_ticks * TICK_PX
        self.setRect(0, 0, new_w, r.height())
        # reposition ports and sensor
        h = r.height()
        self.p_in.setPos(0, h/2)
        self.p_out.setPos(new_w, h/2)
        self.sensor_item.setPos(new_w - 10, 8)

    def set_sensor_enabled(self, enabled: bool):
        self.sensor_enabled = bool(enabled)
        self.sensor_item.setVisible(self.sensor_enabled)
        self.update_sensor_visual()

    def update_sensor_visual(self):
        if not self.sensor_enabled:
            self.sensor_item.setVisible(False)
            return
        self.sensor_item.setVisible(True)
        self.sensor_item.setBrush(QBrush(Qt.green if self.sensor_state else Qt.gray))


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
        self.elapsed_ms = (self.elapsed_ms + dt_ms) % max(1, int(self.interval_ms))
        frac = max(0.0, min(1.0, self.elapsed_ms / self.interval_ms))
        w = self.rect().width() - 16
        self.pb_fg.setRect(8, self.rect().height()-16, w*frac, 8)

    def ready_to_spawn(self) -> bool:
        return self.elapsed_ms >= self.interval_ms - 1

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

        # demo belts
        self.b1 = self.add_belt(60, 60)
        self.b2 = self.add_belt(380, 180)
        self.b3 = self.add_belt(120, 300, 260, 60, "Band 3")

        self.rubber = None
        self.links = []   # lijst van (pathItem, srcPort, dstPort)
        self.links_data = []  # dicts with ids/roles for save/load
        self.downstream = []  # list of (src_obj, dst_belt)
        self.dot = QGraphicsEllipseItem(-4,-4,8,8)
        self.dot.setBrush(QBrush(Qt.red))
        self.dot.setZValue(100)
        self.scene.addItem(self.dot)
        self.anim_path = None
        self.anim_t = 0.0
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

    def add_belt(self, x: float = None, y: float = None, w: float = 220, h: float = 60, label: str = "Belt"):
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
        b.setSelected(True)
        return b

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            item = self.itemAt(ev.pos())
            # Start link if we clicked on a Port
            if isinstance(item, Port):
                scene_p = item.scenePos()
                self.rubber = RubberLink(scene_p)
                self.scene.addItem(self.rubber)
                self.link_src = item
                # Determine parent and role
                parent = item.parentItem()
                self.link_src_belt = parent
                if isinstance(parent, Belt):
                    self.link_src_role = 'input' if (hasattr(parent, 'p_in') and item is parent.p_in) else 'output'
                elif isinstance(parent, BoxGenerator):
                    self.link_src_role = 'output'
                else:
                    self.link_src_role = 'output'
                ev.accept()
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

            # Try to find a Port under cursor; if not, accept releasing on a Belt body (snap to its input)
            end_item = None
            end_parent = None
            end_role = None
            for it in self.scene.items(scene_pos):
                if isinstance(it, Port) and it is not self.link_src:
                    end_item = it
                    end_parent = it.parentItem()
                    end_role = 'input' if (isinstance(end_parent, Belt) and hasattr(end_parent, 'p_in') and it is end_parent.p_in) else 'output'
                    break
                # If user releases on a Belt (not exactly on the dot), snap to its input
                if isinstance(it, Belt):
                    end_item = it.p_in
                    end_parent = it
                    end_role = 'input'
                    break
                # If it's a child of a Belt, also snap to that Belt input
                par = it.parentItem()
                if isinstance(par, Belt):
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
                # Only allow output->input, destination must be Belt input
                if not (src_role == 'output' and dst_role == 'input' and isinstance(dst_obj, Belt)):
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
                path.setToolTip(f"{getattr(src_obj,'label','Generator')} output -> {dst_obj.label} input")
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
    def _rebuild_downstream(self):
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
            le_motor = QLineEdit(item.motor_var or "", dlg)
            cb_sensor = QCheckBox("Sensor aanwezig", dlg); cb_sensor.setChecked(item.sensor_enabled)
            le_sensor = QLineEdit(item.sensor_var or "", dlg); le_sensor.setEnabled(cb_sensor.isChecked())
            def _en():
                le_sensor.setEnabled(cb_sensor.isChecked())
            cb_sensor.toggled.connect(_en)
            form.addRow(QLabel("Titel:"), le_title)
            form.addRow(QLabel("Breedte (ticks):"), sb_ticks)
            form.addRow(QLabel("Motor variabele:"), le_motor)
            form.addRow(cb_sensor)
            form.addRow(QLabel("Sensor variabele:"), le_sensor)
            lay.addLayout(form)

            # Test sensor button
            btn_test = QPushButton("Test sensor puls", dlg)
            lay.addWidget(btn_test)

            # Buttons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
            lay.addWidget(buttons)

            def on_ok():
                item.set_label(le_title.text().strip() or item.label)
                item.resize_for_ticks(sb_ticks.value())
                mv = le_motor.text().strip()
                item.motor_var = mv or None
                if item.motor_var and item.motor_var not in VARS:
                    VARS[item.motor_var] = False
                item.set_sensor_enabled(cb_sensor.isChecked())
                sv = le_sensor.text().strip()
                item.sensor_var = sv or None
                if item.sensor_var and item.sensor_var not in VARS:
                    VARS[item.sensor_var] = False
                self.refresh_link_tooltips()
                self.refresh_port_indicators()
                dlg.accept()

            def on_cancel():
                dlg.reject()

            def on_test():
                # quick pulse for 300 ms
                if not item.sensor_enabled:
                    return
                item.sensor_state = True
                if item.sensor_var:
                    VARS[item.sensor_var] = True
                item.update_sensor_visual()
                QTimer.singleShot(300, lambda: self._sensor_off(item))

            btn_test.clicked.connect(on_test)
            buttons.accepted.connect(on_ok)
            buttons.rejected.connect(on_cancel)
            dlg.exec()
            ev.accept(); return
        elif isinstance(item, BoxGenerator):
            # Settings dialog for Box Generator (interval)
            dlg = QDialog(self)
            dlg.setWindowTitle("Box Generator instellingen")
            lay = QVBoxLayout(dlg)
            from PySide6.QtWidgets import QLineEdit, QSpinBox, QLabel, QFormLayout, QDialogButtonBox
            form = QFormLayout()
            le_title = QLineEdit(item.title.text() if hasattr(item, 'title') else "Box Generator", dlg)
            sb_interval = QSpinBox(dlg)
            sb_interval.setRange(100, 600000)  # 0.1s .. 10min
            sb_interval.setSingleStep(100)
            sb_interval.setSuffix(" ms")
            sb_interval.setValue(int(getattr(item, 'interval_ms', 1500)))
            form.addRow(QLabel("Titel:"), le_title)
            form.addRow(QLabel("Interval:"), sb_interval)
            lay.addLayout(form)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
            lay.addWidget(buttons)

            def on_ok():
                # apply title and interval
                new_title = le_title.text().strip() or "Box Generator"
                if hasattr(item, 'title') and isinstance(item.title, QGraphicsSimpleTextItem):
                    item.title.setText(new_title)
                val = int(sb_interval.value())
                item.set_interval(val)
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
        # update animatiedot over gekozen link (als die bestaat)
        if self.anim_path is not None:
            self.anim_t = (self.anim_t + 0.005 * self.sim_speed) % 1.0
            point = self.point_on_path(self.anim_path, self.anim_t)
            self.dot.setPos(point - QPointF(0,0))

        # Update generator timer and possibly spawn a box
        dt_ms = int(16 * self.sim_speed)
        if getattr(self, 'generator', None) is not None:
            self.generator.tick(dt_ms)
            if self.generator.ready_to_spawn():
                # find a downstream belt from generator
                next_belts = [dst for (src, dst) in self.downstream if src is self.generator]
                if next_belts:
                    b = next_belts[0]
                    # create visual box
                    box_item = QGraphicsRectItem(-7, -5, 14, 10)
                    box_item.setBrush(QBrush(Qt.blue))
                    box_item.setPen(QPen(Qt.black, 1))
                    self.scene.addItem(box_item)
                    # start at t=0 on the destination belt
                    self.boxes.append({"item": box_item, "belt": b, "t": 0.0})
                # reset generator elapsed to avoid multiple spawns same frame
                self.generator.elapsed_ms = 0

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
                # route to downstream belt, else remove
                downs = [dst for (src, dst) in self.downstream if src is belt]
                if downs:
                    bx["belt"] = downs[0]
                    bx["t"] = 0.0
                    belt = bx["belt"]
                else:
                    # remove
                    self.scene.removeItem(bx["item"])
                    self.boxes.remove(bx)
                    continue
            # update visual position on the belt
            r = belt.rect()
            px = belt.scenePos().x() + bx["t"] * r.width()
            py = belt.scenePos().y() + r.height()/2
            bx["item"].setPos(QPointF(px, py))
            # sensor trigger when box in last tick segment
            if belt.sensor_enabled and belt.sensor_var:
                tick_idx = int(bx["t"] * belt.width_ticks)
                if tick_idx >= max(0, belt.width_ticks - 1) and not belt.sensor_state:
                    belt.sensor_state = True
                    VARS[belt.sensor_var] = True
                    belt.update_sensor_visual()
                    QTimer.singleShot(200, lambda it=belt: self._sensor_off(it))

        # Placeholder: if a belt has motor_var True and sensor enabled, briefly pulse sensor periodically
        for sc_item in self.scene.items():
            if isinstance(sc_item, Belt) and sc_item.sensor_enabled and sc_item.sensor_var:
                motor_on = VARS.get(sc_item.motor_var, False) if sc_item.motor_var else False
                if motor_on and not sc_item.sensor_state:
                    # very lightweight demo pulse to visualize behavior (can be replaced by real box detection later)
                    sc_item.sensor_state = True
                    VARS[sc_item.sensor_var] = True
                    sc_item.update_sensor_visual()
                    QTimer.singleShot(200, lambda it=sc_item: self._sensor_off(it))

        # optioneel: links updaten als belts bewegen
        for entry in self.links_data:
            pathItem = entry["pathItem"]
            s = entry["src_belt"].p_out.scenePos() if entry["src_port"] == "output" else entry["src_belt"].p_in.scenePos()
            d = entry["dst_belt"].p_in.scenePos() if entry["dst_port"] == "input" else entry["dst_belt"].p_out.scenePos()
            p = QPainterPath(s)
            mid = (s + d) / 2
            ctrl = QPointF(mid.x(), s.y())
            p.cubicTo(ctrl, QPointF(mid.x(), d.y()), d)
            pathItem.setPath(p)

    @staticmethod
    def point_on_path(path: QPainterPath, t: float) -> QPointF:
        # benader via lengte
        length = path.length()
        pos = path.pointAtPercent(t) if length == 0 else path.pointAtPercent(t)
        return pos

    def refresh_link_tooltips(self):
        for entry in self.links_data:
            pathItem = entry["pathItem"]
            src = entry["src_belt"]
            dst = entry["dst_belt"]
            pathItem.setToolTip(f"{src.label} {entry['src_port']} -> {dst.label} {entry['dst_port']}")

    def refresh_port_indicators(self):
        # Reset all belts' port colors and tooltips
        white = QBrush(Qt.white)
        green = QBrush(Qt.green)
        # Build connection map per belt/port
        conn_map = {}
        for item in self.scene.items():
            if isinstance(item, Belt):
                conn_map[item] = {"input": [], "output": []}
                item.p_in.setBrush(white)
                item.p_out.setBrush(white)
                item.p_in.setToolTip("Input: niet verbonden")
                item.p_out.setToolTip("Output: niet verbonden")
        # Fill connections from links_data
        for entry in self.links_data:
            sb = entry["src_belt"]; sp = entry["src_port"]
            db = entry["dst_belt"]; dp = entry["dst_port"]
            if sb in conn_map:
                conn_map[sb][sp].append(f"→ {db.label} ({dp})")
            if db in conn_map:
                conn_map[db][dp].append(f"← {sb.label} ({sp})")
        # Apply visuals and tooltips
        for belt, ports in conn_map.items():
            if ports["input"]:
                belt.p_in.setBrush(green)
                belt.p_in.setToolTip("Input: verbonden met\n" + "\n".join(ports["input"]))
            if ports["output"]:
                belt.p_out.setBrush(green)
                belt.p_out.setToolTip("Output: verbonden met\n" + "\n".join(ports["output"]))

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

        # Tick/simulation speed
        from PySide6.QtWidgets import QLabel, QDoubleSpinBox
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
                    "sensor_enabled": getattr(item, 'sensor_enabled', False),
                    "sensor_var": getattr(item, 'sensor_var', None)
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
            "links": links
        }
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
            belt = Belt(b["x"], b["y"], b.get("w",220), b.get("h",60), b.get("label","Band"))
            belt.resize_for_ticks(int(b.get("width_ticks", 1)))
            mv = b.get("motor_var")
            belt.motor_var = mv if mv else None
            se = bool(b.get("sensor_enabled", False))
            belt.set_sensor_enabled(se)
            sv = b.get("sensor_var")
            belt.sensor_var = sv if sv else None
            if belt.motor_var and belt.motor_var not in VARS:
                VARS[belt.motor_var] = False
            if belt.sensor_var and belt.sensor_var not in VARS:
                VARS[belt.sensor_var] = False
            belt.update_sensor_visual()
            belt.bid = b["id"]
            id_to_belt[belt.bid] = belt
            self.view.scene.addItem(belt)
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
        # recreate links
        for lk in data.get("links", []):
            src = id_to_belt.get(lk["src_id"])
            dst = id_to_belt.get(lk["dst_id"])
            if not src or not isinstance(dst, Belt):
                continue
            s = src.p_out.scenePos()
            d = dst.p_in.scenePos()
            p = QPainterPath(s)
            mid = (s + d) / 2
            ctrl = QPointF(mid.x(), s.y())
            p.cubicTo(ctrl, QPointF(mid.x(), d.y()), d)
            pathItem = QGraphicsPathItem(p)
            pathItem.setPen(QPen(Qt.darkGreen, 2))
            pathItem.setToolTip(f"{getattr(src,'label','Generator')} {lk['src_port']} -> {dst.label} {lk['dst_port']}")
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec())