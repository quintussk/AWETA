#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conveyor simulation (Tkinter GUI) + Snap7 I/O mapping (DB1)
Robuuste stationsconfig: per station (cellen + DB-base) in één structuur.
 
DB1 mapping (per station op db_base = 4,6,8,10,12):
  .0 I_FT_Pusher          (top sensor bij pusher)      <-- sim schrijft
  .1 I_FT_Outlet_full     (sensor in uitloop)          <-- sim schrijft
  .2 O_Clamp              (clamp)                      --> sim leest
  .3 O_Stop_Down          (stopper-ALLOW uit PLC)      --> sim leest (sim: stop_active = not allow)
  .4 O_Pusher_FW          (pusher)                     --> sim leest
 
Globaal:
  14.0 O_M_BCK_Roller     (hoofdtransport motor)       --> sim leest
  14.1 BCK_Infed_Roller_Full (infeed vol)              <-- sim schrijft (uit-comment in code)
"""
 
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
 
import tkinter as tk
 
STATIONS_BYTE_BASE = 0
BYTES_PER_PAIR     = 2   # i.p.v. 9-bits doortellen: elke BCK[n] is 2 bytes
 
# Relatieve bitindexen binnen BCK_IO_type (0-based binnen de 2 bytes)
BIT_I_ROLLER_BEFORE = 0      # 0.0  (optioneel, als je deze gebruikt)
BIT_I_PUSH1         = 1      # 0.1
BIT_I_PUSH2         = 2      # 0.2
BIT_I_FULL1         = 3      # 0.3
BIT_I_FULL2         = 4      # 0.4
BIT_O_CLAMP         = 5      # 0.5
BIT_O_STOP1         = 6      # 0.6
BIT_O_STOP2         = 7      # 0.7
BIT_O_PUSH1         = 8      # 1.0
BIT_O_PUSH2         = 9      # 1.1
 
def _pair_bit_addr(pair_idx: int, rel_bit: int) -> tuple[int,int]:
    base = STATIONS_BYTE_BASE + pair_idx * BYTES_PER_PAIR
    return (base + (rel_bit // 8), rel_bit % 8)
 
def get_pair_bool(buf: bytearray, pair_idx: int, rel_bit: int) -> bool:
    from snap7.util import get_bool
    b, bit = _pair_bit_addr(pair_idx, rel_bit)
    return get_bool(buf, b, bit)
 
def set_pair_bool(buf: bytearray, pair_idx: int, rel_bit: int, val: bool):
    b, bit = _pair_bit_addr(pair_idx, rel_bit)
    buf[b] = set_bit_into(buf[b], bit, val)
 
# ------------- PLC CONFIG -------------
PLC_IP   = "192.168.241.191"
PLC_RACK = 0
PLC_SLOT = 1
DB_NUM   = 1
DB_SIZE  = 15   # bytes (0..15)
 
# ------------- SIM LAYOUT -------------
CELL_SIZE   = 38
MARGIN_L    = 10
BELT_Y      = 120
BELT_HEIGHT = 44
TICK_MS     = 800
AUTO_MS     = 4000
 
NUM_CELLS = 48
 
# Verticale uitloop
EXIT_LANE_H = int(BELT_HEIGHT * 3)
EXIT_LANE_W = int(CELL_SIZE * 0.8)
EXIT_GAP    = 8
 
# Snelheden
DROP_SPEED = 0.24
EXIT_SPEED = 0.01
 
MOTOR_BYTE = 12
MOTOR_BIT = 0
 
# Hoeveel dozen in de uitloop voordat we "vol" (rood) tonen?
OUTLET_FULL_COUNT = 2
 
# ---- GENERAL INPUTS (DB1) ----
GENERAL_BYTE   = 14   # <== beginbyte van 'General' struct in DB1
BIT_BT_EN_ON   = 1    # I_BT_EN_ON   (start puls)     False->True->False
BIT_BT_EN_OFF  = 2    # I_BT_EN_OFF  (stop puls)      True->False->True
BIT_AIR_OK     = 6    # I_AirPressureOK  (hold)
BIT_SAFETY_OK  = 7    # I_KAG_SafetyOK   (hold)
 
# --------- ROBUUSTE STATIONSCONFIG (visueel ↔ DB) ----------
@dataclass
class StationCfg:
    cells: Tuple[int, int, int]   # (clamp_cell, pusher_cell, stopper_cell) voor het UI-tekenen
    pair: int                     # index in DB Stations[1..N] -> 0..N-1
    lane: int                     # 0 = outlet 1, 1 = outlet 2 (binnen hetzelfde pair)
    has_clamp: bool   = True      # alleen tekenen op de eerste van het paar
    has_pusher: bool  = True
    has_stopper: bool = True
 
# 12 uitlopen = 6 paren
STATIONS_CFG: List[StationCfg] = [
    StationCfg((4, 5, 6),    pair=0, lane=0, has_clamp=True),
    StationCfg((6, 7, 8),    pair=0, lane=1, has_clamp=False),
 
    StationCfg((12, 13, 14), pair=1, lane=0, has_clamp=True),
    StationCfg((14, 15, 16), pair=1, lane=1, has_clamp=False),
 
    StationCfg((20, 21, 22), pair=2, lane=0, has_clamp=True),
    StationCfg((22, 23, 24), pair=2, lane=1, has_clamp=False),
 
    StationCfg((28, 29, 30), pair=3, lane=0, has_clamp=True),
    StationCfg((30, 31, 32), pair=3, lane=1, has_clamp=False),
 
    StationCfg((36, 37, 38), pair=4, lane=0, has_clamp=True),
    StationCfg((38, 39, 40), pair=4, lane=1, has_clamp=False),
 
    StationCfg((44, 45, 46), pair=5, lane=0, has_clamp=True),
    StationCfg((46, 47, 48), pair=5, lane=1, has_clamp=False),
]
 
# ---- Vrij te plaatsen band-sensoren ----
# Formaat per item: (pos_op_band, db_nummer, byte, bit)
EXTRA_SENSORS_CFG = [
    (1,  1, 0, 0),
    (10,  1, 2, 0),
    (18,  1, 4, 0),
    (26,  1, 6, 0),
    (34,  1, 8, 0),
    (42,  1, 10, 0),
]
# Let op: DB_SIZE moet groot genoeg zijn voor de hoogste 'byte'
assert DB_SIZE > max([b for (_,_,b,_) in EXTRA_SENSORS_CFG] + [0]), \
    "DB_SIZE te klein voor EXTRA_SENSORS_CFG"
 
# ------------- DATA CLASSES -------------
@dataclass
class Box:
    cell: int
    state: str = "main"            # "main" | "dropping" | "exit"
    t: float = 0.0                 # animatie-progress (0..1)
    station_index: Optional[int] = None
 
@dataclass
class Station:
    clamp_on: bool = False
    pusher_on: bool = False
    stopper_on: bool = False       # in sim: True = STOP actief
    stopper_allow: bool = False    # direct PLC-bit (O_Stop_Down)
    exits: List[Box] = None
    top_sensor: bool = False
    bottom_sensor: bool = False
    was_full: bool = False        # vorige status (len(exits) >= OUTLET_FULL_COUNT)
    full_count: int = 0           # aantal keer 'vol' geworden
    def __post_init__(self):
        if self.exits is None:
            self.exits = []
 
@dataclass
class ExtraSensor:
    pos: int
    db: int
    byte: int
    bit: int
    on: bool = False  # runtime state
 
# ------------- UTIL (bits) -------------
def set_bit_into(byte_val: int, bit_index: int, value: bool) -> int:
    return (byte_val | (1 << bit_index)) if value else (byte_val & ~(1 << bit_index))
 
# ------------- SNAP7 WORKER -------------
class Snap7Worker(threading.Thread):
    def __init__(self, app, ip: str, rack: int, slot: int, db_num: int, db_size: int, period: float = 0.10):
        super().__init__(daemon=True)
        self.app = app
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.db_num = db_num
        self.db_size = db_size
        self.period = period
        self.running = True
        self.status = "Disconnected"
        self.client = None
        self.snap7_ok = True
        try:
            import snap7  # type: ignore
            self.snap7 = snap7
        except Exception as e:
            self.snap7_ok = False
            self.status = f"snap7 not available: {e}"
 
    def run(self):
        if not self.snap7_ok:
            return
        import snap7
        from snap7.util import get_bool
 
        self.client = snap7.client.Client()
        while self.running:
            try:
                if not self.client.get_connected():
                    self.client.connect(self.ip, self.rack, self.slot)
                    if self.client.get_connected():
                        # print("Connected")
                        self.status = "Connected"
 
                if self.client.get_connected():
                    data = bytearray(self.client.db_read(self.db_num, 0, self.db_size))
 
                    # --- Outputs lezen (PLC -> sim) ---
                    motor = get_bool(data, MOTOR_BYTE, MOTOR_BIT)   # zie §4 voor deze 2 constants
                    with self.app.state_lock:
                        self.app.motor_on = motor
 
                        for ui_idx, cfg in enumerate(STATIONS_CFG):
                            st  = self.app.stations[ui_idx]
                            pr  = cfg.pair
                            ln  = cfg.lane  # 0 of 1
 
                            # clamp is gedeeld binnen het paar
                            clamp = get_pair_bool(data, pr, BIT_O_CLAMP) if cfg.has_clamp else False
 
                            if ln == 0:
                                allow = get_pair_bool(data, pr, BIT_O_STOP1)
                                push  = get_pair_bool(data, pr, BIT_O_PUSH1)
                            else:
                                allow = get_pair_bool(data, pr, BIT_O_STOP2)
                                push  = get_pair_bool(data, pr, BIT_O_PUSH2)
 
                            st.clamp_on      = clamp if cfg.has_clamp else False
                            st.stopper_allow = allow
                            st.stopper_on    = not allow     # in de sim: True = STOP
                            st.pusher_on     = push if cfg.has_pusher else False
 
                        # sensoren uit sim berekenen
                        self.app._compute_sensors_locked()
 
                        # --- Inputs schrijven (sim -> PLC) ---
                        for ui_idx, cfg in enumerate(STATIONS_CFG):
                            st  = self.app.stations[ui_idx]
                            pr  = cfg.pair
                            ln  = cfg.lane
                            if ln == 0:
                                set_pair_bool(data, pr, BIT_I_PUSH1, st.top_sensor)
                                set_pair_bool(data, pr, BIT_I_FULL1, st.bottom_sensor)
                            else:
                                set_pair_bool(data, pr, BIT_I_PUSH2, st.top_sensor)
                                set_pair_bool(data, pr, BIT_I_FULL2, st.bottom_sensor)
 
                    # --- GENERAL (DB1.16) schrijven ---
                    with self.app.state_lock:
                        # Pulslogica: start = True zolang ticks>0, stop = False zolang ticks>0 (active-low)
                        start_one_shot = self.app.start_pulse_ticks > 0
                        stop_low_pulse = self.app.stop_pulse_ticks  > 0
                        if self.app.start_pulse_ticks > 0:
                            self.app.start_pulse_ticks -= 1
                        if self.app.stop_pulse_ticks > 0:
                            self.app.stop_pulse_ticks  -= 1
 
                        air_ok     = self.app.air_ok
                        safety_ok  = self.app.safety_ok
 
                        # Start: False->True->False
                        data[GENERAL_BYTE] = set_bit_into(data[GENERAL_BYTE], BIT_BT_EN_ON,  start_one_shot)
                        # Stop: True->False->True  (dus default True wanneer geen puls)
                        data[GENERAL_BYTE] = set_bit_into(data[GENERAL_BYTE], BIT_BT_EN_OFF, not stop_low_pulse)
 
                        # Permanente toggles
                        data[GENERAL_BYTE] = set_bit_into(data[GENERAL_BYTE], BIT_AIR_OK,    air_ok)
                        data[GENERAL_BYTE] = set_bit_into(data[GENERAL_BYTE], BIT_SAFETY_OK, safety_ok)
 
                    # --- EXTRA SENSOREN: schrijf per DB de bits ---
                    # 1) Buffers per DB verzamelen (bestaande DB_NUM-buffer hergebruiken)
                    db_buffers = { self.db_num: data }
 
                    # Als er sensoren in andere DB's zitten, maak (lees) daar ook buffers voor
                    other_dbs = sorted({xs.db for xs in self.app.extra_sensors if xs.db != self.db_num})
                    for dbn in other_dbs:
                        try:
                            db_buffers[dbn] = bytearray(self.client.db_read(dbn, 0, self.db_size))
                        except Exception:
                            # als lezen mislukt, maak lege buffer zodat set_bit_into niet crasht
                            db_buffers[dbn] = bytearray(self.db_size)
 
                    # Bits zetten op basis van de actuele sim-state
                    with self.app.state_lock:
                        for xs in self.app.extra_sensors:
                            buf = db_buffers.get(xs.db)
                            if buf is None or xs.byte >= len(buf):
                                continue
                            buf[xs.byte] = set_bit_into(buf[xs.byte], xs.bit, xs.on)
 
                    # 2) Buffers wegschrijven: eerst de hoofd-DB (zoals altijd)...
                    self.client.db_write(self.db_num, 0, db_buffers[self.db_num])
                    # ...en eventuele extra DB's ook
                    for dbn in other_dbs:
                        self.client.db_write(dbn, 0, db_buffers[dbn])
 
                    # print(f"{self.db_num},0, {data}")
                    self.client.db_write(self.db_num, 0, data)
                    self.status = "OK"
                else:
                    self.status = "Connecting..."
            except Exception as e:
                self.status = f"Error: {e}"
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                time.sleep(0.5)
            time.sleep(self.period)
 
    def stop(self):
        self.running = False
        try:
            if self.client and self.client.get_connected():
                self.client.disconnect()
        except Exception:
            pass
 
# ------------- APP (Tk + Sim) -------------
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Lege Fust BCK SIM (Agricola El Rosal (63657))")
        self.canvas_w = MARGIN_L*2 + NUM_CELLS*CELL_SIZE
        self.canvas_h = 400
        self.canvas = tk.Canvas(root, width=self.canvas_w, height=self.canvas_h, bg="white")
        self.canvas.grid(row=0, column=0, columnspan=12, sticky="nsew", padx=6, pady=6)
 
        self.state_lock = threading.RLock()  # re-entrant, voorkomt deadlocks
        self.motor_on = True
        self.auto_on = False
        self.auto_acc = 0
        self.exit_motor_on = True
 
        self.boxes: List[Box] = []
        self.stations: List[Station] = [Station() for _ in STATIONS_CFG]
 
        self.extra_sensors: List[ExtraSensor] = [
            ExtraSensor(pos, db, byte, bit) for (pos, db, byte, bit) in EXTRA_SENSORS_CFG
        ]
 
        self._build_controls()
        self._bind_keys()
 
        self.snap7_lbl = tk.Label(root, text="Snap7: Disconnected", anchor="w", fg="#555")
        self.snap7_lbl.grid(row=3, column=0, columnspan=12, sticky="w", padx=6, pady=(0,6))
 
        self.worker = Snap7Worker(self, PLC_IP, PLC_RACK, PLC_SLOT, DB_NUM, DB_SIZE, period=0.10)
        self.worker.start()
 
        # --- General (DB1.16) sim states ---
        self.start_pulse_ticks = 0   # 2 ticks = ~0.2s puls
        self.stop_pulse_ticks  = 0   # 2 ticks = ~0.2s puls (active low)
        self.air_ok            = True
        self.safety_ok         = True
 
        self._tick()
 
    # --- UI ---
    def _build_controls(self):
        # Start / Stop pulses
        self.start_btn = tk.Button(self.root, text="Start (S)", width=12, command=self.do_start_pulse)
        self.start_btn.grid(row=1, column=0, sticky="w", padx=6, pady=(0,6))
 
        self.stop_btn  = tk.Button(self.root, text="Stop (T)", width=12, command=self.do_stop_pulse)
        self.stop_btn.grid(row=1, column=1, sticky="w", padx=6, pady=(0,6))
 
        # Air OK & Safety OK toggles
        self.air_btn = tk.Button(self.root, text="Air OK: ON", width=12, command=self.toggle_air_ok, bg="#d9ffd9")
        self.air_btn.grid(row=1, column=2, sticky="w", padx=6, pady=(0,6))
 
        self.safety_btn = tk.Button(self.root, text="Safety OK: ON", width=14, command=self.toggle_safety_ok, bg="#d9ffd9")
        self.safety_btn.grid(row=1, column=3, sticky="w", padx=6, pady=(0,6))
 
        # Rest zoals je had:
        tk.Button(self.root, text="Nieuwe doos (N)", command=self.spawn_box).grid(row=1, column=4, sticky="w", padx=6, pady=(0,6))
        self.auto_btn = tk.Button(self.root, text="Auto feed: OFF (A)", command=self.toggle_auto)
        self.auto_btn.grid(row=1, column=5, sticky="w", padx=6, pady=(0,6))
        self.reset_btn = tk.Button(self.root, text="Reset", command=self.reset_all)
        self.reset_btn.grid(row=1, column=7, sticky="w", padx=6, pady=(0,6))
 
        legend = ("N: nieuwe doos | S: start puls | T: stop puls | A: auto | Q: quit\n" )
        tk.Label(self.root, text=legend, anchor="w", justify="left").grid(row=2, column=0, columnspan=12, sticky="w", padx=6)
 
        self.canvas.bind("<Button-1>", self._on_click)
 
    def reset_all(self):
        with self.state_lock:
            self.boxes.clear()
            for st in self.stations:
                st.exits.clear()
                st.top_sensor = False
                st.bottom_sensor = False
                st.clamp_on = False
                st.stopper_on = False
                st.stopper_allow = False
                st.pusher_on = False
                st.was_full = False
                st.full_count = 0
            self.auto_acc = 0
 
    def _bind_keys(self):
        self.root.bind("<KeyPress>", self._on_key)
 
    def _on_key(self, e: tk.Event):
        k = e.keysym.lower()
        if k == "q": self.root.destroy(); return
        if k == "n": self.spawn_box(); return
        if k == "s": self.do_start_pulse(); return
        if k == "t": self.do_stop_pulse(); return
        if k == "a": self.toggle_auto(); return
        if k == "o": self.toggle_outlet(); return
 
    def _on_click(self, e: tk.Event):
        x, y = e.x, e.y
        with self.state_lock:
            for idx, cfg in enumerate(STATIONS_CFG):
                cfg = STATIONS_CFG[idx]
                c_cell, p_cell, s_cell = cfg.cells
 
                # Clamp
                if cfg.has_clamp:
                    cx1, cx2 = self._x(c_cell), self._x(c_cell+1)
                    cy1, cy2 = BELT_Y - BELT_HEIGHT*1.2, BELT_Y - BELT_HEIGHT*0.2
                    if cx1 <= x <= cx2 and cy1 <= y <= cy2:
                        self.stations[idx].clamp_on = not self.stations[idx].clamp_on; return
 
                # Pusher
                if cfg.has_pusher:
                    px1, px2 = self._x(p_cell), self._x(p_cell+1)
                    py1, py2 = BELT_Y - BELT_HEIGHT*1.2, BELT_Y - BELT_HEIGHT*0.2
                    if px1 <= x <= px2 and py1 <= y <= py2:
                        self.stations[idx].pusher_on = not self.stations[idx].pusher_on; return
 
                # Stopper
                if cfg.has_stopper:
                    sx1, sx2 = self._x(s_cell), self._x(s_cell+1)
                    sy1, sy2 = BELT_Y, BELT_Y + BELT_HEIGHT
                    if sx1 <= x <= sx2 and sy1 <= y <= sy2:
                        st = self.stations[idx]
                        st.stopper_allow = not st.stopper_allow
                        st.stopper_on    = not st.stopper_allow
                        return
 
    def do_start_pulse(self):
        # False -> True -> False
        with self.state_lock:
            self.start_pulse_ticks = 2   # ~2 * worker.period
 
    def do_stop_pulse(self):
        # True -> False -> True (active-low)
        with self.state_lock:
            self.stop_pulse_ticks = 2
 
    def toggle_air_ok(self):
        with self.state_lock:
            self.air_ok = not self.air_ok
        self.air_btn.config(text=f"Air OK: {'ON' if self.air_ok else 'OFF'}",
                            bg=("#d9ffd9" if self.air_ok else "#ffd9d9"))
 
    def toggle_safety_ok(self):
        with self.state_lock:
            self.safety_ok = not self.safety_ok
        self.safety_btn.config(text=f"Safety OK: {'ON' if self.safety_ok else 'OFF'}",
                            bg=("#d9ffd9" if self.safety_ok else "#ffd9d9"))
 
    def toggle_motor(self):
        with self.state_lock:
            self.motor_on = not self.motor_on
        self.motor_btn.config(text=f"Motor: {'ON' if self.motor_on else 'OFF'}",
                              bg=("#d9ffd9" if self.motor_on else "#ffd9d9"))
 
    def toggle_auto(self):
        with self.state_lock:
            self.auto_on = not self.auto_on
            self.auto_acc = 0
        self.auto_btn.config(text=f"Auto feed: {'ON' if self.auto_on else 'OFF'} (A)",
                             bg=("#d9ffd9" if self.auto_on else None))
 
    def spawn_box(self):
        with self.state_lock:
            if any(b.state == "main" and b.cell == 0 for b in self.boxes):
                return
            self.boxes.append(Box(cell=0))
 
    # --- Loop ---
    def _tick(self):
        self.snap7_lbl.config(text=f"Snap7: {self.worker.status}")
 
        should_spawn = False
        with self.state_lock:
            if self.auto_on:
                self.auto_acc += TICK_MS
                if self.auto_acc >= AUTO_MS:
                    self.auto_acc = 0
                    should_spawn = True
        if should_spawn:
            self.root.after(0, self.spawn_box)
 
        self._advance()
        self._draw()
        self.root.after(TICK_MS, self._tick)
 
    def _advance(self):
        with self.state_lock:
            occ = {b.cell for b in self.boxes if b.state == "main"}
            next_boxes: List[Box] = []
 
            for b in self.boxes:
                if b.state == "dropping":
                    b.t += DROP_SPEED
                    if b.t >= 1.0:
                        si = b.station_index
                        if si is not None:
                            self.stations[si].exits.append(Box(cell=0, state="exit", t=0.0, station_index=si))
                    else:
                        next_boxes.append(b)
                    continue
 
                if b.state == "main":
                    cur = b.cell
                    next_cell = cur + 1
                    st_idx = self._station_by_cell(cur)
                    if st_idx is not None:
                        c_cell, p_cell, s_cell = STATIONS_CFG[st_idx].cells
                        cfg = STATIONS_CFG[st_idx]
 
                        # Clamp
                        if cfg.has_clamp and cur == c_cell and self.stations[st_idx].clamp_on:
                            next_boxes.append(b); continue
 
                        # Pusher
                        if cfg.has_pusher and cur == p_cell and self.stations[st_idx].pusher_on:
                            b.state = "dropping"; b.station_index = st_idx; b.t = 0.0
                            next_boxes.append(b); continue
 
                        # Stopper als grens
                        if cfg.has_stopper and cur == s_cell - 1:
                            if self.stations[st_idx].stopper_on:
                                next_boxes.append(b); continue
                            else:
                                target = s_cell + 1
                                if self.motor_on and target < NUM_CELLS and target not in occ:
                                    b.cell = target
                                next_boxes.append(b); continue
 
                        # Veiligheid: niet parkeren op s_cell (alleen als er überhaupt een stopper bestaat)
                        if cfg.has_stopper and cur == s_cell:
                            target = s_cell + 1
                            if not self.stations[st_idx].stopper_on and self.motor_on and target < NUM_CELLS and target not in occ:
                                b.cell = target
                            next_boxes.append(b); continue
 
                    if self.motor_on and next_cell < NUM_CELLS and next_cell not in occ:
                        b.cell = next_cell
                        next_boxes.append(b)
                    else:
                        if next_cell < NUM_CELLS:
                            next_boxes.append(b)
                        # anders valt hij vanzelf van de band (verdwijnen)
 
            self.boxes = next_boxes
 
            # Exit lanes
            if self.exit_motor_on:
                for st in self.stations:
                    for eb in st.exits:
                        eb.t += EXIT_SPEED
                    st.exits = [eb for eb in st.exits if eb.t < 1.0]
                for st in self.stations:
                    now_full = len(st.exits) >= OUTLET_FULL_COUNT
                    if now_full and not st.was_full:
                        st.full_count += 1        # telt alleen bij overgang naar vol
                    st.was_full = now_full
 
    def _draw_extra_sensors(self):
        # cirkel midden onder het betreffende vakje
        for xs in self.extra_sensors:
            cx = self._x(xs.pos) + CELL_SIZE // 2
            cy = BELT_Y + BELT_HEIGHT + 6
            r  = 10
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    fill=("#7bd97b" if xs.on else "white"),
                                    outline="black", width=2)
            self.canvas.create_text(cx, cy+18, text="s", font=("Arial", 10))
 
    def _compute_sensors_locked(self):
        # top-sensor: doos bij pusher; bottom-sensor: iets in de uitloop
        for si, cfg in enumerate(STATIONS_CFG):
            c_cell, p_cell, s_cell = cfg.cells
            top = any((b.cell == p_cell and b.state in ("main","dropping")) for b in self.boxes)
            bottom = len(self.stations[si].exits) > 0
            self.stations[si].top_sensor = top
            self.stations[si].bottom_sensor = bottom
 
        # Vrije band-sensoren: 'on' als er een doos MAIN in dat vakje staat
        occ_cells = {b.cell for b in self.boxes if b.state == "main"}
        for xs in self.extra_sensors:
            xs.on = (xs.pos in occ_cells)
 
    def _station_by_cell(self, cell: int) -> Optional[int]:
        for i, cfg in enumerate(STATIONS_CFG):
            if cell in cfg.cells:
                return i
        return None
 
    # --- Draw ---
    def _x(self, cell: int) -> int:
        return MARGIN_L + cell*CELL_SIZE
 
    def _draw(self):
        self.canvas.delete("all")
        self._draw_belt()
        self._draw_stations()
        self._draw_boxes()
        self._draw_status()
        self._draw_extra_sensors()
 
    def _draw_belt(self):
        y1, y2 = BELT_Y, BELT_Y+BELT_HEIGHT
        for i in range(NUM_CELLS):
            x1, x2 = self._x(i), self._x(i+1)
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="black", width=2)
 
    def _draw_stations(self):
        with self.state_lock:
            self._compute_sensors_locked()
 
            for idx, cfg in enumerate(STATIONS_CFG):
                c_cell, p_cell, s_cell = cfg.cells
                st = self.stations[idx]
 
                # Clamp
                if cfg.has_clamp:
                    cx1, cx2 = self._x(c_cell), self._x(c_cell+1)
                    cy1, cy2 = BELT_Y - BELT_HEIGHT*1.2, BELT_Y - BELT_HEIGHT*0.2
                    self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                                fill=("#7bd97b" if st.clamp_on else "#eeeeee"),
                                                outline="black", width=2)
                    self.canvas.create_text((cx1+cx2)//2, (cy1+cy2)//2, text="C", font=("Arial", 14))
 
                # Pusher
                if cfg.has_pusher:
                    px1, px2 = self._x(p_cell), self._x(p_cell+1)
                    py1, py2 = BELT_Y - BELT_HEIGHT*1.2, BELT_Y - BELT_HEIGHT*0.2
                    self.canvas.create_rectangle(px1, py1, px2, py2,
                                                fill=("#7bd97b"if st.pusher_on else "white"),
                                                outline=("green" if st.pusher_on else "black"),
                                                width=3)
                    self.canvas.create_text((px1+px2)//2, (py1+py2)//2, text="p", font=("Arial", 14))
 
                # Top sensor
                sx = (px1+px2)//2 + int(CELL_SIZE*0.4)
                sy = py2 + 4
                r = 10
                self.canvas.create_oval(sx-r, sy-r, sx+r, sy+r,
                                        fill=("#7bd97b" if st.top_sensor else "white"),
                                        outline="black", width=2)
                self.canvas.create_text(sx, sy+18, text="s", font=("Arial", 11))
 
                # Stopper-tegel (half zo breed, indicatie)
                if cfg.has_stopper:
                    sx1, sx2 = self._x(s_cell), self._x(s_cell+1)
                    sy1, sy2 = BELT_Y, BELT_Y + BELT_HEIGHT
                    half_w = CELL_SIZE // 2
                    mx = (sx1 + sx2) // 2
                    rx1, rx2 = mx - half_w // 2, mx + half_w // 2
                    self.canvas.create_rectangle(
                        rx1, sy1, rx2, sy2,
                        fill=("#7bd97b" if st.stopper_allow else "#eb3e3e"),
                        outline="black", width=2
                    )
                    self.canvas.create_text((sx1+sx2)//2, (sy1+sy2)//2, text="S",
                                            font=("Arial", 16, "bold"))
 
                # Verticale uitloop (bij de pusher)
                if cfg.has_pusher:
                    lane_x1 = self._x(p_cell) + (CELL_SIZE - EXIT_LANE_W)//2
                    lane_x2 = lane_x1 + EXIT_LANE_W
                    lane_y1 = BELT_Y + BELT_HEIGHT + EXIT_GAP
                    lane_y2 = lane_y1 + EXIT_LANE_H
 
                    # Rood als er ≥ OUTLET_FULL_COUNT dozen in de uitloop staan
                    outlet_count = len(st.exits)
                    is_full = outlet_count >= OUTLET_FULL_COUNT
                    lane_fill = "#eb3e3e" if is_full else "white"
                    lane_outline = "red" if is_full else "black"
 
                    self.canvas.create_rectangle(
                        lane_x1, lane_y1, lane_x2, lane_y2,
                        outline=lane_outline, fill=lane_fill, width=2
                    )
 
                # Dozen in uitloop (omlaag)
                for eb in st.exits:
                    box_w = EXIT_LANE_W - 12
                    box_h = BELT_HEIGHT - 12
                    x_left = lane_x1 + (EXIT_LANE_W - box_w)//2
                    path_len = max(8, (lane_y2 - lane_y1) - box_h - 10)
                    y_top = lane_y1 + 6 + int(path_len * eb.t)
                    self.canvas.create_rectangle(x_left, y_top, x_left + box_w, y_top + box_h,
                                                 fill="#3b7bff", outline="black", width=2)
 
                # Bottom sensor rechts naast uitloop
                sen_x = lane_x2 + 12
                sen_y = (lane_y1 + lane_y2)//2
                self.canvas.create_oval(sen_x-11, sen_y-11, sen_x+11, sen_y+11,
                                        fill=("#7bd97b" if st.bottom_sensor else "white"),
                                        outline="black", width=2)
                self.canvas.create_text(sen_x, sen_y+20, text="s", font=("Arial", 11))
 
    def _draw_boxes(self):
        with self.state_lock:
            for b in self.boxes:
                if b.state == "main":
                    x1, x2 = self._x(b.cell)+4, self._x(b.cell+1)-4
                    y1, y2 = BELT_Y+4, BELT_Y+BELT_HEIGHT-4
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill="#3b7bff", outline="black", width=2)
                elif b.state == "dropping":
                    si = b.station_index
                    if si is None:
                        continue
                    c_cell, p_cell, s_cell = STATIONS_CFG[si].cells
                    sx1, sx2 = self._x(p_cell)+4, self._x(p_cell+1)-4
                    sy1, sy2 = BELT_Y+4, BELT_Y+BELT_HEIGHT-4
                    lane_x1 = self._x(p_cell) + (CELL_SIZE - EXIT_LANE_W)//2
                    lane_y1 = BELT_Y + BELT_HEIGHT + EXIT_GAP
                    dx1 = lane_x1 + (EXIT_LANE_W - (sx2 - sx1))//2
                    dx2 = dx1 + (sx2 - sx1)
                    dy1 = lane_y1 + 10
                    dy2 = dy1 + (sy2 - sy1)
                    t = max(0.0, min(1.0, b.t))
                    x1 = sx1*(1-t) + dx1*t
                    x2 = sx2*(1-t) + dx2*t
                    y1 = sy1*(1-t) + dy1*t
                    y2 = sy2*(1-t) + dy2*t
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill="#3b7bff", outline="black", width=2)
 
    def _draw_status(self):
        with self.state_lock:
            on_belt = sum(1 for b in self.boxes if b.state == "main")
            status = (f"Motor: {'ON' if self.motor_on else 'OFF'} | "
                      f"Auto box infeed: {'ON' if self.auto_on else 'OFF'} | "
                      f"Boxes on belt: {on_belt}")
        counts = " | ".join(f"S{idx+1}:{st.full_count}" for idx, st in enumerate(self.stations))
        self.canvas.create_text(10, self.canvas_h-12, text=f"Outlets vol: {counts}",
                                anchor="w", fill="#444")
 
# # --- helpers ---
# def STATIONS_CFG(idx):  # type: ignore
#     """Truc om accidental tuple-call te vermijden in _advance(); niets functioneels."""
#     return None
 
def main():
    root = tk.Tk()
    root.rowconfigure(0, weight=1); root.columnconfigure(0, weight=1)
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.worker.stop(), root.destroy()))
    root.mainloop()
 
if __name__ == "__main__":
    main()
 
 