"""View class for conveyor belt simulation canvas."""

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QGraphicsEllipseItem,
    QMenu,
)

from aweta.core.constants import TICK_PX
from aweta.core.variables import VARS
from aweta.tools.belt.belt_item import Belt
from aweta.tools.belt.exit_item import ExitBlock
from aweta.tools.belt.box_generator import BoxGenerator
from aweta.tools.belt.port import Port as BeltPort
from aweta.tools.belt.link import RubberLink
from aweta.ui.dialogs.belt_settings_dialog import BeltSettingsDialog
from aweta.ui.dialogs.exit_settings_dialog import ExitSettingsDialog


class View(QGraphicsView):
    """Graphics view for conveyor belt simulation."""
    
    def __init__(self):
        """Initialize the view."""
        super().__init__()
        self.setRenderHints(self.renderHints() | self.renderHints().Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setSceneRect(0, 0, 1600, 900)
        
        self.last_scene_pos = self.sceneRect().center()
        
        # Counters for IDs and numbering
        self.next_belt_id = 1
        self.next_belt_num = 1
        self.next_exit_id = 1
        self.next_exit_num = 1
        
        # Demo belts (optional - can be removed)
        self.b1 = self.add_belt(60, 60)
        self.b2 = self.add_belt(380, 180)
        self.b3 = self.add_belt(120, 300, 260, 60, "Band 3")
        
        self.rubber = None
        self.links = []  # List of (pathItem, srcPort, dstPort)
        self.links_data = []  # Dicts with ids/roles for save/load
        self.downstream = []  # List of (src_obj, dst_belt)
        
        # React to selection changes (for link highlight + red-dot attach)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        
        # Simulation speed multiplier (1.0 = real-time)
        self.sim_speed = 1.0
        
        # Timer for animation
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
        self.boxes = []  # List of dicts: {"item": QGraphicsRectItem, "belt": Belt, "t": float}
        self.generator_blocked = False  # Wait until downstream is free to spawn next box
        
        # Animation state
        self.anim_path = None
        self.anim_t = 0.0
    
    def belt_has_box(self, belt: Belt) -> bool:
        """Check if belt has any boxes on it.
        
        Args:
            belt: Belt to check
            
        Returns:
            True if belt has boxes, False otherwise
        """
        for bx in self.boxes:
            if bx["belt"] is belt:
                return True
        return False
    
    def cell_occupied(self, belt: Belt, idx: int) -> bool:
        """Check if the given belt cell index is occupied by any active box.
        
        Args:
            belt: Belt to check
            idx: Cell index to check
            
        Returns:
            True if cell is occupied, False otherwise
        """
        try:
            for bx in self.boxes:
                if bx.get("belt") is belt:
                    t_clamped = max(0.0, min(0.999, float(bx.get("t", 0.0))))
                    cell_idx = int(t_clamped * max(1, getattr(belt, 'width_ticks', 1)))
                    if cell_idx == int(idx):
                        return True
        except Exception:
            pass
        return False
    
    def add_belt(self, x: float = None, y: float = None, w: float = TICK_PX, h: float = 80, label: str = "Belt"):
        """Add a belt to the scene.
        
        Args:
            x: X position (None = use last position)
            y: Y position (None = use last position)
            w: Width in pixels
            h: Height in pixels
            label: Display label
            
        Returns:
            Created Belt instance
        """
        if x is None or y is None:
            p = self.last_scene_pos if hasattr(self, 'last_scene_pos') else self.sceneRect().center()
            x, y = p.x(), p.y()
        
        # Default label if not provided
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
        """Add an exit block to the scene.
        
        Args:
            x: X position (None = use last position)
            y: Y position (None = use last position)
            w: Width in pixels
            h: Height in pixels
            label: Display label
            
        Returns:
            Created ExitBlock instance
        """
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
        """Handle mouse press events."""
        if ev.button() == Qt.RightButton:
            item = self.itemAt(ev.pos())
            # Propagate to parent item if we clicked on a child
            target = item
            while target is not None and not isinstance(target, (QGraphicsPathItem, Belt, ExitBlock, BoxGenerator)):
                target = target.parentItem()
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
                    ev.accept()
                    return
                if chosen == act_del_node:
                    self.delete_selected_nodes()
                    ev.accept()
                    return
        if ev.button() == Qt.LeftButton:
            item = self.itemAt(ev.pos())
            # Start link if we clicked on a Port
            if isinstance(item, BeltPort):
                parent = item.parentItem()
                # Disallow starting a link from ExitBlock (it only has an input)
                if isinstance(parent, ExitBlock):
                    ev.accept()
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
                ev.accept()
                return
        super().mousePressEvent(ev)
    
    def mouseMoveEvent(self, ev):
        """Handle mouse move events."""
        self.last_scene_pos = self.mapToScene(ev.pos())
        if self.rubber is not None:
            end_scene = self.mapToScene(ev.pos())
            self.rubber.update_to(end_scene)
            ev.accept()
            return
        super().mouseMoveEvent(ev)
    
    def mouseReleaseEvent(self, ev):
        """Handle mouse release events."""
        if self.rubber is not None:
            # Temporarily hide rubber so hit-test isn't blocked by it
            self.rubber.setVisible(False)
            scene_pos = self.mapToScene(ev.pos())
            
            # Try to find a Port under cursor; if not, accept releasing on a Belt/Exit body (snap to its input)
            end_item = None
            end_parent = None
            end_role = None
            for it in self.scene.items(scene_pos):
                if isinstance(it, BeltPort) and it is not self.link_src:
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
                    # Invalid; discard rubber line
                    path_tmp = self.rubber
                    self.rubber = None
                    self.scene.removeItem(path_tmp)
                    ev.accept()
                    return
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
                    "src_belt": src_obj,  # may be Belt or BoxGenerator
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
            ev.accept()
            return
        super().mouseReleaseEvent(ev)
    
    def mouseDoubleClickEvent(self, ev):
        """Handle mouse double-click events."""
        item = self.itemAt(ev.pos())
        # If the user double-clicks a child (title/port/progress bar),
        # climb to the logical parent (Belt or BoxGenerator)
        target = item
        while target is not None and not isinstance(target, (Belt, BoxGenerator)):
            target = target.parentItem()
        if target is not None:
            item = target
        if isinstance(item, Belt):
            # Open settings dialog
            dlg = BeltSettingsDialog(self, item)
            if dlg.exec() == dlg.Accepted:
                self.refresh_link_tooltips()
                self.refresh_port_indicators()
            ev.accept()
            return
        elif isinstance(item, ExitBlock):
            # Open settings dialog
            dlg = ExitSettingsDialog(self, item)
            if dlg.exec() == dlg.Accepted:
                self.refresh_link_tooltips()
                self.refresh_port_indicators()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)
    
    def on_selection_changed(self):
        """Handle selection changes."""
        # Highlight selected links
        selected_paths = []
        for e in self.links_data:
            pathItem = e["pathItem"]
            if pathItem.isSelected():
                pathItem.setPen(QPen(Qt.blue, 3, Qt.DashLine))
                selected_paths.append(pathItem)
            else:
                pathItem.setPen(QPen(Qt.darkGreen, 2))
        # Attach/redraw anim dot on last selected path (if any)
        if selected_paths:
            self.anim_path = selected_paths[-1].path()
            self.anim_t = 0.0
        else:
            self.anim_path = None
    
    def delete_selected_nodes(self):
        """Delete selected nodes (belts/exits)."""
        # Collect selected belts/exits
        selected = [it for it in self.scene.selectedItems() if isinstance(it, (Belt, ExitBlock))]
        if not selected:
            return
        # Remove any links connected to them
        to_remove_links = []
        for e in list(self.links_data):
            if e["src_belt"] in selected or e["dst_belt"] in selected:
                to_remove_links.append(e)
        for e in to_remove_links:
            if e["pathItem"] is not None:
                self.scene.removeItem(e["pathItem"])
            if e in self.links_data:
                self.links_data.remove(e)
        # Remove boxes sitting on selected belts
        if hasattr(self, 'boxes'):
            self.boxes = [bx for bx in self.boxes if bx.get("belt") not in selected]
        # Finally remove the nodes
        for it in selected:
            self.scene.removeItem(it)
        self._rebuild_downstream()
        self.refresh_link_tooltips()
        self.refresh_port_indicators()
        # Update paths to be safe
        self.update_all_link_paths()
    
    def delete_selected_links(self):
        """Delete selected links."""
        # Collect selected link path items
        to_remove = []
        for e in list(self.links_data):
            pathItem = e["pathItem"]
            if pathItem.isSelected():
                to_remove.append(e)
        if not to_remove:
            return
        # Remove visuals and entries
        for e in to_remove:
            pathItem = e["pathItem"]
            # Detach any animation path reference
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
        # Also prune from legacy self.links if present
        if hasattr(self, 'links'):
            dead_paths = {e["pathItem"] for e in to_remove}
            self.links = [t for t in self.links if t[0] not in dead_paths]
        # Rebuild caches and visuals
        self._rebuild_downstream()
        self.refresh_link_tooltips()
        self.refresh_port_indicators()
        self.update_all_link_paths()
    
    def keyPressEvent(self, ev):
        """Handle key press events."""
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            # Delete links if any selected, otherwise delete nodes
            had_links = False
            for e in self.links_data:
                if e["pathItem"].isSelected():
                    had_links = True
                    break
            if had_links:
                self.delete_selected_links()
            else:
                self.delete_selected_nodes()
            ev.accept()
            return
        super().keyPressEvent(ev)
    
    def update_all_link_paths(self):
        """Update all link paths."""
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
    
    @staticmethod
    def point_on_path(path: QPainterPath, t: float) -> QPointF:
        """Get a point on a path at parameter t.
        
        Args:
            path: Path to evaluate
            t: Parameter value (0.0 to 1.0)
            
        Returns:
            Point on path
        """
        length = path.length()
        pos = path.pointAtPercent(t) if length == 0 else path.pointAtPercent(t)
        return pos
    
    def _label_of(self, obj) -> str:
        """Get label for an object.
        
        Args:
            obj: Object to get label for
            
        Returns:
            Label string
        """
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
        """Refresh tooltips for all links."""
        for entry in self.links_data:
            pathItem = entry["pathItem"]
            src = entry["src_belt"]
            dst = entry["dst_belt"]
            src_name = self._label_of(src)
            dst_name = self._label_of(dst)
            pathItem.setToolTip(f"{src_name} {entry['src_port']} -> {dst_name} {entry['dst_port']}")
    
    def refresh_port_indicators(self):
        """Refresh port indicators (connected/disconnected state)."""
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
            sb = entry["src_belt"]
            sp = entry["src_port"]
            db = entry["dst_belt"]
            dp = entry["dst_port"]
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
            # Drop entries whose visuals were already deleted
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
        """Remove all boxes that are currently on belts (not inside Exit blocks)."""
        if not hasattr(self, 'boxes') or not self.boxes:
            return
        for bx in list(self.boxes):
            itm = bx.get("item")
            if itm is not None:
                try:
                    self.scene.removeItem(itm)
                except Exception:
                    pass
            # Remove from list
            try:
                self.boxes.remove(bx)
            except ValueError:
                pass
        # Update belt occupancy indicators
        for sc_item in self.scene.items():
            if isinstance(sc_item, Belt):
                sc_item.has_box = False
                sc_item.update_box_indicator()
    
    def tick(self):
        """Update simulation state (called by timer)."""
        # Update generator timer and possibly spawn a single box only when downstream is free
        dt_ms = int(16 * self.sim_speed)
        if getattr(self, 'generator', None) is not None:
            # Determine first downstream node from generator (Belt or ExitBlock)
            next_nodes = [dst for (src, dst) in self.downstream if src is self.generator]
            first_dst = next_nodes[0] if next_nodes else None
            
            # Can we spawn now? (allow multiple boxes on a belt but not in the same cell)
            if isinstance(first_dst, Belt):
                # Only spawn if the first cell (index 0) is free
                can_spawn_now = not self.cell_occupied(first_dst, 0)
            elif isinstance(first_dst, ExitBlock):
                can_spawn_now = first_dst.can_accept()
            else:
                can_spawn_now = False
            
            # UI: blocked = progressbar full and timer pauses
            self.generator.blocked = self.generator_blocked or (not can_spawn_now and self.generator.ready_to_spawn())
            
            # Update progress
            self.generator.tick(dt_ms)
            
            # Spawn moments
            if self.generator_blocked and can_spawn_now:
                # Previously blocked, now free -> spawn now
                if isinstance(first_dst, Belt):
                    # Fill the cell visually: use dimensions matching the belt cell
                    cell_h = 80 - 28 - 20  # Same as belt's inner band height
                    cell_w = TICK_PX - 16  # Match one tick width minus margins
                    box_item = QGraphicsRectItem(0, 0, cell_w, cell_h)
                    box_item.setBrush(QBrush(Qt.blue))
                    box_item.setPen(QPen(Qt.black, 1))
                    self.scene.addItem(box_item)
                    self.boxes.append({"item": box_item, "belt": first_dst, "t": 0.0})
                elif isinstance(first_dst, ExitBlock):
                    box_item = QGraphicsRectItem(-7, -5, 14, 10)
                    box_item.setBrush(QBrush(Qt.blue))
                    box_item.setPen(QPen(Qt.black, 1))
                    # Not in self.boxes; exit manages this box
                    first_dst.add_box(box_item)
                self.generator_blocked = False
                self.generator.blocked = False
                self.generator.elapsed_ms = 0
            
            elif not self.generator_blocked and self.generator.ready_to_spawn():
                if can_spawn_now:
                    if isinstance(first_dst, Belt):
                        cell_h = 80 - 28 - 20  # Same as belt's inner band height
                        cell_w = TICK_PX - 16  # Match one tick width minus margins
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
                    # Can't yet -> block until free
                    self.generator_blocked = True
                    self.generator.blocked = True
        
        # Move boxes across belts if motor is on
        speed_per_sec = 0.25 * self.sim_speed  # Fraction of belt length per second
        dt = 0.016 * self.sim_speed
        for bx in list(self.boxes):
            belt = bx["belt"]
            motor_on = VARS.get(belt.motor_var, False) if belt.motor_var else False
            # Visual indicator + debug log: only update on state change
            try:
                prev = getattr(belt, '_motor_on_state', False)
                if motor_on != prev:
                    # White when ON, dark gray when OFF
                    belt.setBrush(QBrush(Qt.white if motor_on else Qt.darkGray))
                    belt._motor_on_state = motor_on
            except Exception:
                pass
            if motor_on:
                try:
                    # Prevent moving into an occupied cell: compute current and next cell
                    width_ticks = max(1, getattr(belt, 'width_ticks', 1))
                    cur_t = float(bx.get("t", 0.0))
                    cur_cell = int(max(0.0, min(0.999, cur_t)) * width_ticks)
                    new_t = cur_t + speed_per_sec * dt
                    new_cell = int(max(0.0, min(0.999, new_t)) * width_ticks)
                    if new_cell != cur_cell:
                        # Moving into a new cell: only advance if that cell is free
                        if not self.cell_occupied(belt, new_cell):
                            bx["t"] = new_t
                        # Else wait in current cell (do nothing)
                    else:
                        # Still in same cell: advance normally
                        bx["t"] = new_t
                except Exception:
                    # Fallback: safe increment
                    bx["t"] += speed_per_sec * dt
            # Reached end?
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
                        # Unknown destination: hold the box at the end of the belt
                        bx["t"] = 0.999
                        continue
                else:
                    # No downstream configured: hold the box at the end of the belt
                    bx["t"] = 0.999
                    continue
            # Snap visually to cells (middle band)
            r = belt.rect()
            cell_w = (r.width() - 16) / max(1, belt.width_ticks)
            # Middle band y between 28..(h-20)
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
        
        # Optionally: update links as belts move
        self.update_all_link_paths()

