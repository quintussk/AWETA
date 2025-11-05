"""Project save/load functionality for AWETA application."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from TIA_Db.utlis import S7DataBlock as TIA_S7DataBlock
except ImportError:
    TIA_S7DataBlock = None  # type: ignore


class ProjectManager:
    """Manages project save/load operations."""
    
    def __init__(self):
        """Initialize project manager."""
        self.current_path: Optional[str] = None
    
    def save_project(self, view: Any, db_block: Optional[Any] = None, db_definition_path: Optional[str] = None) -> Dict[str, Any]:
        """Save project data to dictionary.
        
        Args:
            view: View containing belts, exits, links, etc.
            db_block: Optional DB block to save
            db_definition_path: Optional DB definition file path
            
        Returns:
            Dictionary containing project data
        """
        # Collect belts
        belts = []
        id_map = {}
        for item in view.scene.items():
            from aweta.tools.belt.belt_item import Belt
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
        
        # Collect exits
        exits = []
        for item in view.scene.items():
            from aweta.tools.belt.exit_item import ExitBlock
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
        
        # Collect links
        links = []
        for entry in getattr(view, 'links_data', []):
            src_obj = entry["src_belt"]
            dst_obj = entry["dst_belt"]
            from aweta.tools.belt.box_generator import BoxGenerator
            src_id = 0 if isinstance(src_obj, BoxGenerator) else id_map.get(src_obj)
            dst_id = id_map.get(dst_obj)
            links.append({
                "src_id": src_id,
                "src_port": entry["src_port"],
                "dst_id": dst_id,
                "dst_port": entry["dst_port"]
            })
        
        payload = {
            "belts": belts,
            "exits": exits,
            "links": links
        }
        
        # Persist DB info if available
        try:
            if db_block is not None and db_definition_path:
                payload["db"] = {
                    "definition_path": db_definition_path,
                    "db_number": int(getattr(db_block, 'db_number', 0)),
                    "buffer": list(getattr(db_block, 'buffer', bytearray()))
                }
        except Exception:
            pass
        
        # Generator info
        if hasattr(view, 'generator') and view.generator is not None:
            payload["generator"] = {
                "interval_ms": view.generator.interval_ms,
                "x": view.generator.scenePos().x(),
                "y": view.generator.scenePos().y(),
                "running": getattr(view.generator, 'running', True)
            }
        
        return payload
    
    def save_to_file(self, path: str, view: Any, db_block: Optional[Any] = None, db_definition_path: Optional[str] = None):
        """Save project to file.
        
        Args:
            path: File path to save to
            view: View containing belts, exits, links, etc.
            db_block: Optional DB block to save
            db_definition_path: Optional DB definition file path
        """
        payload = self.save_project(view, db_block, db_definition_path)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        self.current_path = path
    
    def load_from_file(self, path: str) -> Dict[str, Any]:
        """Load project from file.
        
        Args:
            path: File path to load from
            
        Returns:
            Dictionary containing project data
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.current_path = path
        return data
    
    def load_project(self, data: Dict[str, Any], view: Any) -> tuple[Optional[Any], Optional[str]]:
        """Load project data into view.
        
        Args:
            data: Project data dictionary
            view: View to load into
            
        Returns:
            Tuple of (db_block, db_definition_path) if DB info present
        """
        from aweta.tools.belt.belt_item import Belt
        from aweta.tools.belt.exit_item import ExitBlock
        from aweta.tools.belt.box_generator import BoxGenerator
        from aweta.core.constants import TICK_PX
        from aweta.core.variables import VARS
        
        # Reset
        view.scene.clear()
        view.links.clear()
        view.links_data.clear()
        view.next_belt_id = 1
        view.next_belt_num = 1
        view.next_exit_id = 1
        view.next_exit_num = 1
        view.generator_blocked = False
        
        # Recreate generator
        gen_data = data.get("generator")
        view.generator = None
        if isinstance(gen_data, dict):
            gx = float(gen_data.get("x", 10.0))
            gy = float(gen_data.get("y", 10.0))
            view.generator = BoxGenerator(gx, gy)
            view.generator.set_interval(int(gen_data.get("interval_ms", 1500)))
            if bool(gen_data.get("running", True)):
                view.generator.start()
            else:
                view.generator.stop()
            view.scene.addItem(view.generator)
        
        # Recreate belts keeping ids
        id_to_belt = {}
        for b in data.get("belts", []):
            belt = Belt(b["x"], b["y"], b.get("w", TICK_PX), b.get("h", 80), b.get("label", "Band"))
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
            view.scene.addItem(belt)
            if hasattr(belt, "_rebuild_slots"):
                belt._rebuild_slots()
            view.next_belt_id = max(view.next_belt_id, belt.bid + 1)
            try:
                if belt.label.lower().startswith("band "):
                    n = int(belt.label.split(" ")[1])
                    view.next_belt_num = max(view.next_belt_num, n + 1)
            except Exception:
                pass
        
        if hasattr(view, 'generator') and view.generator is not None:
            id_to_belt[0] = view.generator
        
        # Recreate exits keeping ids
        for ex in data.get("exits", []):
            exitb = ExitBlock(ex["x"], ex["y"], ex.get("w", 180), ex.get("h", 80), ex.get("label", "Exit"))
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
            view.scene.addItem(exitb)
            if hasattr(exitb, "_rebuild_slots"):
                exitb._rebuild_slots()
                if hasattr(exitb, "_refresh_fills_from_boxes"):
                    exitb._refresh_fills_from_boxes()
                if hasattr(exitb, "_update_timer_text"):
                    exitb._update_timer_text()
            id_to_belt[exitb.xid] = exitb
            view.next_exit_id = max(view.next_exit_id, exitb.xid + 1)
            try:
                if exitb.label.lower().startswith("exit "):
                    n = int(exitb.label.split(" ")[1])
                    view.next_exit_num = max(view.next_exit_num, n + 1)
            except Exception:
                pass
        
        # Recreate links
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPen, QPainterPath
        from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem
        
        for lk in data.get("links", []):
            src = id_to_belt.get(lk["src_id"])
            dst = id_to_belt.get(lk["dst_id"])
            if not src or not isinstance(dst, (Belt, ExitBlock)):
                continue
            s = src.p_out.scenePos()
            d = dst.p_in.scenePos()
            from PySide6.QtCore import QPointF
            p = QPainterPath(s)
            mid = (s + d) / 2
            p.cubicTo(QPointF(mid.x(), s.y()), QPointF(mid.x(), d.y()), d)
            pathItem = QGraphicsPathItem(p)
            pathItem.setPen(QPen(Qt.darkGreen, 2))
            pathItem.setFlag(QGraphicsItem.ItemIsSelectable, True)
            pathItem.setFlag(QGraphicsItem.ItemIsFocusable, True)
            view.scene.addItem(pathItem)
            view.links_data.append({
                "pathItem": pathItem,
                "src_belt": src,
                "src_port": lk["src_port"],
                "dst_belt": dst,
                "dst_port": lk["dst_port"]
            })
        
        view.refresh_link_tooltips()
        view.refresh_port_indicators()
        view._rebuild_downstream()
        
        # Restore DB if present
        db_block = None
        db_definition_path = None
        try:
            dbinfo = data.get("db")
            if dbinfo and TIA_S7DataBlock is not None:
                defp = dbinfo.get("definition_path")
                dbn = dbinfo.get("db_number")
                if defp and dbn is not None:
                    db_block = TIA_S7DataBlock.from_definition_file(
                        path=defp,
                        db_number=int(dbn),
                        nesting_depth_to_skip=1
                    )
                    db_definition_path = defp
                    buf = dbinfo.get("buffer")
                    if isinstance(buf, list):
                        db_block.buffer = bytearray(buf)
        except Exception:
            pass
        
        return db_block, db_definition_path

