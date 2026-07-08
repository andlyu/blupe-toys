#!/usr/bin/env python3
"""Button rig: a 2-servo SCARA arm that moves a pushbutton around the table.

The rig is a planar two-link arm (link1 = shoulder->elbow, link2 =
elbow->button) driven by two Feetech STS3215 servos on a Waveshare serial-bus
driver board. A single-key USB keypad at the end effector types "1" when
pressed; that keystroke is the task's success signal.

Setup flow (see README.md for the full walkthrough):
  python3 button_rig.py scan                    # A) find servos on the bus
  python3 button_rig.py setup-id --id 1         # (shoulder alone on the bus)
  python3 button_rig.py setup-id --id 2         # (elbow alone on the bus)
  python3 button_rig.py calibrate               # B) zero/sign/range calibration
  python3 button_rig.py ui                      # C) web UI: draw the button's
                                                #    box, test moves, toy mode

Requires: feetech-servo-sdk (scservo_sdk), pynput for the press listener.
Set BUTTON_RIG_PORT (or pass --port) to the driver board's serial device,
e.g. /dev/cu.usbserial-XXXX on macOS, /dev/ttyUSB0 or /dev/ttyACM0 on Linux.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

RIG_DIR = Path(__file__).resolve().parent
CONFIG_DIR = Path(os.environ.get("BUTTON_RIG_CONFIG_DIR", RIG_DIR / "config"))
CALIBRATION_PATH = CONFIG_DIR / "calibration.json"
GRID_PATH = CONFIG_DIR / "grid.json"
LOG_DIR = Path(os.environ.get("BUTTON_RIG_LOG_DIR", RIG_DIR / "logs"))

DEFAULT_PORT = os.environ.get("BUTTON_RIG_PORT", "")
DEFAULT_BAUD = int(os.environ.get("BUTTON_RIG_BAUD", "1000000"))

# Defaults for the printed assembly in stl/button.stl; calibration stores the
# values actually used, so a rebuilt rig only needs these edited once.
LINK1_MM = 162.0  # shoulder axis -> elbow axis
LINK2_MM = 150.0  # elbow axis -> button center
TICKS_PER_TURN = 4096
DEG_PER_TICK = 360.0 / TICKS_PER_TURN
BUTTON_KEY = "1"

# On a dedicated driver board the servos are simply 1 and 2. If the rig shares
# a bus with an arm, override with env vars to IDs the arm doesn't use.
MOTOR_IDS = {
    "shoulder": int(os.environ.get("BUTTON_RIG_SHOULDER_ID", "1")),
    "elbow": int(os.environ.get("BUTTON_RIG_ELBOW_ID", "2")),
}


# ---------------------------------------------------------------------------
# Kinematics (pure functions; angles in degrees, distances in mm).
# Frame: origin at the shoulder axis. theta1 = link1 angle from +X, CCW
# positive; theta2 = elbow bend relative to link1, CCW positive. Fully
# extended along +X is theta1 = theta2 = 0 (the calibration zero pose).
# ---------------------------------------------------------------------------


def forward_kinematics(
    theta1_deg: float, theta2_deg: float, l1: float = LINK1_MM, l2: float = LINK2_MM
) -> tuple[float, float]:
    t1 = math.radians(theta1_deg)
    t12 = t1 + math.radians(theta2_deg)
    return (l1 * math.cos(t1) + l2 * math.cos(t12), l1 * math.sin(t1) + l2 * math.sin(t12))


def inverse_kinematics(
    x: float, y: float, l1: float = LINK1_MM, l2: float = LINK2_MM, elbow: str = "up"
) -> tuple[float, float]:
    """Return (theta1_deg, theta2_deg) reaching (x, y), or raise ValueError."""
    r = math.hypot(x, y)
    if r > l1 + l2 + 1e-9 or r < abs(l1 - l2) - 1e-9:
        raise ValueError(
            f"target ({x:.1f}, {y:.1f}) mm is out of reach: r={r:.1f}, "
            f"reachable annulus is [{abs(l1 - l2):.1f}, {l1 + l2:.1f}] mm"
        )
    cos_t2 = (r * r - l1 * l1 - l2 * l2) / (2 * l1 * l2)
    cos_t2 = max(-1.0, min(1.0, cos_t2))
    t2 = math.acos(cos_t2)
    if elbow == "down":
        t2 = -t2
    t1 = math.atan2(y, x) - math.atan2(l2 * math.sin(t2), l1 + l2 * math.cos(t2))
    return math.degrees(t1), math.degrees(t2)


def wrap_tick_delta(delta: int) -> int:
    """Map a raw tick difference to the shortest signed distance on the ring."""
    return (delta + TICKS_PER_TURN // 2) % TICKS_PER_TURN - TICKS_PER_TURN // 2


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


@dataclass
class JointCalibration:
    id: int
    zero_tick: int
    sign: int  # +1 if increasing ticks == CCW joint motion
    min_deg: float
    max_deg: float

    def tick_to_deg(self, tick: int) -> float:
        return self.sign * wrap_tick_delta(tick - self.zero_tick) * DEG_PER_TICK

    def deg_to_tick(self, deg: float) -> int:
        return (self.zero_tick + self.sign * round(deg / DEG_PER_TICK)) % TICKS_PER_TURN

    def clamp_deg(self, deg: float) -> float:
        return max(self.min_deg, min(self.max_deg, deg))


@dataclass
class RigCalibration:
    port: str
    joints: dict[str, JointCalibration] = field(default_factory=dict)
    link1_mm: float = LINK1_MM
    link2_mm: float = LINK2_MM

    def save(self, path: Path = CALIBRATION_PATH) -> None:
        payload = {
            "port": self.port,
            "link1_mm": self.link1_mm,
            "link2_mm": self.link2_mm,
            "joints": {name: vars(j) for name, j in self.joints.items()},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n")

    @classmethod
    def load(cls, path: Path = CALIBRATION_PATH) -> "RigCalibration":
        data = json.loads(path.read_text())
        return cls(
            port=data["port"],
            link1_mm=data.get("link1_mm", LINK1_MM),
            link2_mm=data.get("link2_mm", LINK2_MM),
            joints={name: JointCalibration(**j) for name, j in data["joints"].items()},
        )


# ---------------------------------------------------------------------------
# Bus wrapper (raw ticks; normalization handled by JointCalibration)
# ---------------------------------------------------------------------------


class RigBus:
    def __init__(self, port: str, baudrate: int = DEFAULT_BAUD):
        import scservo_sdk as scs

        self._scs = scs
        self.port = port
        self.port_handler = scs.PortHandler(port)
        self.packet_handler = scs.PacketHandler(0)
        if not self.port_handler.openPort():
            raise ConnectionError(f"could not open {port}")
        self.port_handler.setBaudRate(baudrate)

    def close(self) -> None:
        self.port_handler.closePort()

    # -- low level -----------------------------------------------------
    def ping(self, motor_id: int) -> int | None:
        model, comm, _ = self.packet_handler.ping(self.port_handler, motor_id)
        return model if comm == self._scs.COMM_SUCCESS else None

    def _write1(self, motor_id: int, addr: int, value: int) -> None:
        comm, err = self.packet_handler.write1ByteTxRx(self.port_handler, motor_id, addr, value)
        self._check(motor_id, addr, comm, err)

    def _write2(self, motor_id: int, addr: int, value: int) -> None:
        comm, err = self.packet_handler.write2ByteTxRx(self.port_handler, motor_id, addr, value)
        self._check(motor_id, addr, comm, err)

    def _read2(self, motor_id: int, addr: int) -> int:
        value, comm, err = self.packet_handler.read2ByteTxRx(self.port_handler, motor_id, addr)
        self._check(motor_id, addr, comm, err)
        return value

    def _check(self, motor_id: int, addr: int, comm: int, err: int) -> None:
        if comm != self._scs.COMM_SUCCESS:
            raise ConnectionError(
                f"id={motor_id} addr={addr}: {self.packet_handler.getTxRxResult(comm)}"
            )
        if err != 0:
            raise RuntimeError(
                f"id={motor_id} addr={addr}: {self.packet_handler.getRxPacketError(err)}"
            )

    # -- registers (STS3215 control table) ------------------------------
    ADDR_ID = 5
    ADDR_LOCK = 55
    ADDR_TORQUE_ENABLE = 40
    ADDR_ACCELERATION = 41
    ADDR_GOAL_POSITION = 42
    ADDR_GOAL_VELOCITY = 46
    ADDR_PRESENT_POSITION = 56

    def set_id(self, current_id: int, new_id: int) -> None:
        self._write1(current_id, self.ADDR_LOCK, 0)
        self._write1(current_id, self.ADDR_ID, new_id)
        self._write1(new_id, self.ADDR_LOCK, 1)

    def torque(self, motor_id: int, enabled: bool) -> None:
        self._write1(motor_id, self.ADDR_TORQUE_ENABLE, 1 if enabled else 0)

    def read_position(self, motor_id: int) -> int:
        return self._read2(motor_id, self.ADDR_PRESENT_POSITION) % TICKS_PER_TURN

    def move_to(self, motor_id: int, tick: int, velocity: int = 400, acceleration: int = 40) -> None:
        self._write1(motor_id, self.ADDR_ACCELERATION, acceleration)
        self._write2(motor_id, self.ADDR_GOAL_VELOCITY, velocity)
        self._write2(motor_id, self.ADDR_GOAL_POSITION, tick % TICKS_PER_TURN)

    def wait_until_reached(
        self, motor_id: int, tick: int, tolerance: int = 20, timeout_s: float = 6.0
    ) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if abs(wrap_tick_delta(self.read_position(motor_id) - tick)) <= tolerance:
                return True
            time.sleep(0.02)
        return False


# ---------------------------------------------------------------------------
# Rig: calibrated motion
# ---------------------------------------------------------------------------


class Rig:
    def __init__(self, bus: RigBus, calibration: RigCalibration):
        self.bus = bus
        self.cal = calibration

    def read_angles(self) -> dict[str, float]:
        return {
            name: j.tick_to_deg(self.bus.read_position(j.id)) for name, j in self.cal.joints.items()
        }

    def read_xy(self) -> tuple[float, float]:
        a = self.read_angles()
        return forward_kinematics(a["shoulder"], a["elbow"], self.cal.link1_mm, self.cal.link2_mm)

    def goto_angles(self, theta1: float, theta2: float, velocity: int = 400) -> bool:
        targets = {"shoulder": theta1, "elbow": theta2}
        ok = True
        ticks: dict[str, int] = {}
        for name, deg in targets.items():
            j = self.cal.joints[name]
            clamped = j.clamp_deg(deg)
            if abs(clamped - deg) > 0.5:
                print(f"  {name}: {deg:.1f} deg clamped to {clamped:.1f} (limit)", file=sys.stderr)
            ticks[name] = j.deg_to_tick(clamped)
        for name, tick in ticks.items():
            j = self.cal.joints[name]
            self.bus.torque(j.id, True)
            self.bus.move_to(j.id, tick, velocity=velocity)
        for name, tick in ticks.items():
            ok = self.bus.wait_until_reached(self.cal.joints[name].id, tick) and ok
        return ok

    def solve_xy(self, x: float, y: float, elbow: str = "up") -> tuple[float, float]:
        """IK solution satisfying joint limits (tries both elbow branches)."""
        last_error: ValueError | None = None
        for branch in (elbow, "down" if elbow == "up" else "up"):
            t1, t2 = inverse_kinematics(x, y, self.cal.link1_mm, self.cal.link2_mm, branch)
            j1, j2 = self.cal.joints["shoulder"], self.cal.joints["elbow"]
            if (
                j1.min_deg - 0.5 <= t1 <= j1.max_deg + 0.5
                and j2.min_deg - 0.5 <= t2 <= j2.max_deg + 0.5
            ):
                return t1, t2
            last_error = ValueError(
                f"({x:.0f}, {y:.0f}) mm: elbow-{branch} solution "
                f"(theta1={t1:.1f}, theta2={t2:.1f}) violates joint limits"
            )
        raise last_error if last_error else ValueError("unreachable")

    def goto_xy(self, x: float, y: float, elbow: str = "up", velocity: int = 400) -> bool:
        t1, t2 = self.solve_xy(x, y, elbow)
        return self.goto_angles(t1, t2, velocity=velocity)

    def torque_off(self) -> None:
        for j in self.cal.joints.values():
            self.bus.torque(j.id, False)


# ---------------------------------------------------------------------------
# Button listener (USB keypad types "1")
# ---------------------------------------------------------------------------


class ButtonListener:
    """Global keyboard listener; queues timestamps of BUTTON_KEY presses."""

    def __init__(self) -> None:
        from pynput import keyboard

        self.presses: "queue.Queue[float]" = queue.Queue()

        def on_press(key: object) -> None:
            if getattr(key, "char", None) == BUTTON_KEY:
                self.presses.put(time.monotonic())

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.start()

    def clear(self) -> None:
        while not self.presses.empty():
            try:
                self.presses.get_nowait()
            except queue.Empty:
                break

    def wait_for_press(self, timeout_s: float) -> float | None:
        try:
            return self.presses.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._listener.stop()


# ---------------------------------------------------------------------------
# Grid: the box the button is allowed to visit
# ---------------------------------------------------------------------------

GRID_CORNERS = ("c00", "c10", "c11", "c01")  # (u,v) = (0,0), (1,0), (1,1), (0,1)


def grid_to_xy(corners: dict[str, dict[str, float]], u: float, v: float) -> tuple[float, float]:
    """Bilinear map from unit-square (u, v) to the captured corner quad (mm)."""
    a, b, c, d = (corners[k] for k in GRID_CORNERS)
    x = (1 - u) * (1 - v) * a["x"] + u * (1 - v) * b["x"] + u * v * c["x"] + (1 - u) * v * d["x"]
    y = (1 - u) * (1 - v) * a["y"] + u * (1 - v) * b["y"] + u * v * c["y"] + (1 - u) * v * d["y"]
    return x, y


def save_grid(grid: dict[str, dict[str, float]]) -> None:
    GRID_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRID_PATH.write_text(json.dumps(grid, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _require_port(args: argparse.Namespace) -> str:
    if not args.port:
        raise SystemExit(
            "no serial port: pass --port or set BUTTON_RIG_PORT\n"
            "  macOS: ls /dev/cu.usbserial-* /dev/cu.usbmodem*\n"
            "  Linux: ls /dev/ttyUSB* /dev/ttyACM*"
        )
    return args.port


def cmd_scan(args: argparse.Namespace) -> int:
    import scservo_sdk as scs

    port_name = _require_port(args)
    port = scs.PortHandler(port_name)
    if not port.openPort():
        print(f"could not open {port_name}", file=sys.stderr)
        return 1
    ph = scs.PacketHandler(0)
    found_any = False
    for baud in (1000000, 500000, 250000, 128000, 115200, 57600, 38400, 19200, 9600, 4800):
        port.setBaudRate(baud)
        hits = []
        for motor_id in range(0, 254):
            model, comm, _ = ph.ping(port, motor_id)
            if comm == scs.COMM_SUCCESS:
                hits.append((motor_id, model))
        if hits:
            found_any = True
            for motor_id, model in hits:
                print(f"baud={baud} id={motor_id} model={model}")
    port.closePort()
    if not found_any:
        print("no servos found (check the 12V supply and the 3-pin servo cable)")
        return 1
    return 0


def cmd_setup_id(args: argparse.Namespace) -> int:
    bus = RigBus(_require_port(args))
    try:
        hits = [motor_id for motor_id in range(0, 254) if bus.ping(motor_id) is not None]
        if len(hits) != 1:
            print(
                f"expected exactly ONE servo on the bus, found {hits or 'none'}; "
                "disconnect the other servo and retry",
                file=sys.stderr,
            )
            return 1
        current = hits[0]
        if current == args.id:
            print(f"servo already has id={args.id}")
            return 0
        bus.set_id(current, args.id)
        ok = bus.ping(args.id) is not None
        print(f"id {current} -> {args.id}: {'ok' if ok else 'FAILED'}")
        return 0 if ok else 1
    finally:
        bus.close()


def cmd_read(args: argparse.Namespace) -> int:
    bus = RigBus(_require_port(args))
    try:
        cal = RigCalibration.load() if CALIBRATION_PATH.exists() else None
        for name, motor_id in MOTOR_IDS.items():
            if bus.ping(motor_id) is None:
                print(f"{name} (id={motor_id}): not responding")
                continue
            tick = bus.read_position(motor_id)
            line = f"{name} (id={motor_id}): tick={tick}"
            if cal and name in cal.joints:
                line += f" angle={cal.joints[name].tick_to_deg(tick):.1f} deg"
            print(line)
        if cal and len(cal.joints) == 2:
            rig = Rig(bus, cal)
            x, y = rig.read_xy()
            print(f"button XY: ({x:.1f}, {y:.1f}) mm")
        return 0
    finally:
        bus.close()


def _capture(bus: RigBus, prompt: str) -> dict[str, int]:
    input(prompt + "  [Enter] ")
    return {name: bus.read_position(motor_id) for name, motor_id in MOTOR_IDS.items()}


def _record_ranges_until_enter(bus: RigBus, zero: dict[str, int]) -> dict[str, list[int]]:
    """Live min/max display while the joints are swept by hand; Enter to finish."""
    import select

    extremes = {name: [0, 0] for name in MOTOR_IDS}  # tick deltas vs zero
    while True:
        for name, motor_id in MOTOR_IDS.items():
            delta = wrap_tick_delta(bus.read_position(motor_id) - zero[name])
            lo, hi = extremes[name]
            extremes[name] = [min(lo, delta), max(hi, delta)]
        line = "   ".join(
            f"{name}: [{lo * DEG_PER_TICK:+7.1f}, {hi * DEG_PER_TICK:+7.1f}] deg"
            for name, (lo, hi) in extremes.items()
        )
        print("\r  " + line + "   (Enter to finish) ", end="", flush=True)
        if select.select([sys.stdin], [], [], 0.02)[0]:
            sys.stdin.readline()
            print()
            return extremes


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Start from the MIDDLE pose, then sweep both joints to their extremes."""
    bus = RigBus(_require_port(args))
    try:
        for name, motor_id in MOTOR_IDS.items():
            if bus.ping(motor_id) is None:
                print(f"{name} (id={motor_id}) not responding; run scan/setup-id first", file=sys.stderr)
                return 1
            bus.torque(motor_id, False)
        print("Torque is OFF; move the arm by hand.\n")

        zero = _capture(
            bus,
            "1/4  Move the arm to its MIDDLE pose: both links in a straight line\n"
            "     along the +X reference direction, roughly centered in each\n"
            "     joint's travel. This pose becomes theta1 = theta2 = 0.",
        )

        moved1 = _capture(
            bus,
            "2/4  Rotate the SHOULDER (base) joint ~45 deg COUNTERCLOCKWISE\n"
            "     (viewed from above), keeping the elbow straight.",
        )
        moved2 = _capture(
            bus,
            "3/4  Now bend the ELBOW ~45 deg COUNTERCLOCKWISE as well.",
        )
        d1 = wrap_tick_delta(moved1["shoulder"] - zero["shoulder"])
        d2 = wrap_tick_delta(moved2["elbow"] - moved1["elbow"])
        if abs(d1) < 100 or abs(d2) < 100:
            print(f"joint motion too small to determine direction (d1={d1}, d2={d2})", file=sys.stderr)
            return 1
        signs = {"shoulder": 1 if d1 > 0 else -1, "elbow": 1 if d2 > 0 else -1}

        print(
            "4/4  Sweep BOTH joints all the way LEFT and all the way RIGHT\n"
            "     (gently to the physical limits, a couple of times)."
        )
        extremes = _record_ranges_until_enter(bus, zero)

        joints = {}
        for name, motor_id in MOTOR_IDS.items():
            sign = signs[name]
            bounds = sorted((extremes[name][0] * sign * DEG_PER_TICK,
                             extremes[name][1] * sign * DEG_PER_TICK))
            if bounds[0] > -5 or bounds[1] < 5:
                print(f"warning: {name} range {bounds} barely spans the middle pose — "
                      "was the sweep done from the middle?", file=sys.stderr)
            joints[name] = JointCalibration(
                id=motor_id, zero_tick=zero[name], sign=sign,
                min_deg=round(bounds[0], 2), max_deg=round(bounds[1], 2),
            )
            print(f"{name} (id={motor_id}): zero_tick={zero[name]} sign={sign:+d} "
                  f"range=[{bounds[0]:.1f}, {bounds[1]:.1f}] deg")

        cal = RigCalibration(port=args.port, joints=joints)
        cal.save()
        print(f"saved {CALIBRATION_PATH}")
        print("Verify with: button_rig.py read   (move the arm by hand and watch XY)")
        return 0
    finally:
        bus.close()


def _make_rig(args: argparse.Namespace) -> tuple[RigBus, Rig]:
    if not CALIBRATION_PATH.exists():
        raise SystemExit(f"no calibration at {CALIBRATION_PATH}; run calibrate first")
    cal = RigCalibration.load()
    bus = RigBus(args.port or cal.port)
    return bus, Rig(bus, cal)


def cmd_goto(args: argparse.Namespace) -> int:
    bus, rig = _make_rig(args)
    try:
        if args.u is not None and args.v is not None:
            if not GRID_PATH.exists():
                print(f"no grid at {GRID_PATH}; draw the box in the web UI first", file=sys.stderr)
                return 1
            grid = json.loads(GRID_PATH.read_text())
            missing = [k for k in GRID_CORNERS if k not in grid]
            if missing:
                print(f"grid incomplete, missing corners {missing}", file=sys.stderr)
                return 1
            u = max(0.0, min(1.0, args.u))
            v = max(0.0, min(1.0, args.v))
            x, y = grid_to_xy(grid, u, v)
        else:
            x, y = args.x, args.y
        ok = rig.goto_xy(x, y, elbow=args.elbow, velocity=args.velocity)
        cx, cy = rig.read_xy()
        print(f"target=({x:.1f}, {y:.1f}) reached=({cx:.1f}, {cy:.1f}) mm ok={ok}")
        return 0 if ok else 1
    finally:
        bus.close()


def cmd_listen(args: argparse.Namespace) -> int:
    listener = ButtonListener()
    print(
        f"listening for '{BUTTON_KEY}' presses (Ctrl-C to stop); if nothing arrives,\n"
        "check the keypad is programmed to type '1' and, on macOS, grant\n"
        "Input Monitoring to your terminal in System Settings"
    )
    try:
        while True:
            if listener.wait_for_press(timeout_s=1.0) is not None:
                print(f"press at {time.strftime('%H:%M:%S')}")
    except KeyboardInterrupt:
        listener.stop()
        return 0


# ---------------------------------------------------------------------------
# Web UI: draw the button's box, test moves, run toy mode
# ---------------------------------------------------------------------------

RIG_UI_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Button Rig</title>
<style>
  body { font-family: -apple-system, sans-serif; margin: 24px; background: #14161a; color: #e8e8e8; }
  h2 { margin: 0 0 4px; font-weight: 600; }
  p.hint { margin: 0 0 12px; color: #9ab; font-size: 13px; }
  .row { display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }
  canvas { background: #1d2026; border-radius: 8px; cursor: crosshair; }
  .panel { min-width: 280px; display: flex; flex-direction: column; gap: 10px; }
  button { background: #2b303a; color: #e8e8e8; border: 1px solid #444; border-radius: 6px;
           padding: 8px 12px; cursor: pointer; font-size: 14px; }
  button:hover { background: #39404d; }
  button.armed { background: #7c3a3a; }
  .corner-done { color: #7dc87d; }
  #status { font-family: ui-monospace, monospace; font-size: 13px; white-space: pre; color: #9ab; }
  .cap { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
</style></head><body>
<h2>Button Rig</h2>
<p class="hint">Left canvas: the workspace — <b>drag to draw the box</b> the button may visit;
click to send the button somewhere. Right canvas: the box in (u, v) — click to test a spot.</p>
<div class="row">
  <canvas id="arm" width="440" height="440"></canvas>
  <canvas id="grid" width="440" height="440"></canvas>
  <div class="panel">
    <div id="status">connecting...</div>
    <button id="torque">Torque OFF (hand-place)</button>
    <button id="toy">Toy mode: OFF</button>
    <div><b>Or capture corners physically</b> (torque off, hand-place the button, click):</div>
    <div class="cap">
      <button data-corner="c00">A &rarr; (0,0)</button>
      <button data-corner="c10">B &rarr; (1,0)</button>
      <button data-corner="c01">D &rarr; (0,1)</button>
      <button data-corner="c11">C &rarr; (1,1)</button>
    </div>
    <div id="corners"></div>
    <div><b>Go to (u, v)</b>:</div>
    <div style="display:flex;gap:6px">
      <input id="u" type="number" min="0" max="1" step="0.05" value="0.5" style="width:70px">
      <input id="v" type="number" min="0" max="1" step="0.05" value="0.5" style="width:70px">
      <button id="gouv">Go</button>
      <button id="gorand">Random</button>
    </div>
    <div id="log" style="color:#c9a; font-size:13px"></div>
  </div>
</div>
<script>
let st = {};
async function api(path, body) {
  const res = await fetch(path, body ? {method:'POST', body: JSON.stringify(body)} : {});
  return res.json();
}
function logMsg(m) { document.getElementById('log').textContent = m; }

// ---- grid (u,v) canvas ----
const cv = document.getElementById('grid'), ctx = cv.getContext('2d');
const M = 30, W = cv.width - 2*M;
function uvToPx(u, v) { return [M + u*W, M + v*W]; }
function drawGrid() {
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.strokeStyle = '#39404d'; ctx.lineWidth = 1;
  for (let i = 0; i <= 10; i++) {
    const t = i / 10;
    ctx.beginPath(); ctx.moveTo(...uvToPx(t,0)); ctx.lineTo(...uvToPx(t,1)); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(...uvToPx(0,t)); ctx.lineTo(...uvToPx(1,t)); ctx.stroke();
  }
  ctx.strokeStyle = '#5b8dd9'; ctx.lineWidth = 2;
  ctx.strokeRect(M, M, W, W);
  ctx.fillStyle = '#9ab'; ctx.font = '12px sans-serif';
  ctx.fillText('(0,0)', M - 14, M - 8);
  ctx.fillText('(1,1)', cv.width - M - 10, cv.height - M + 18);
  if (st.last_uv) {
    const [px, py] = uvToPx(st.last_uv[0], st.last_uv[1]);
    ctx.fillStyle = '#e8b04a'; ctx.beginPath(); ctx.arc(px, py, 7, 0, 7); ctx.fill();
  }
}
cv.onclick = async (e) => {
  const r = cv.getBoundingClientRect();
  const u = Math.min(1, Math.max(0, (e.clientX - r.left - M) / W));
  const v = Math.min(1, Math.max(0, ((e.clientY - r.top) - M) / W));
  await go(u, v);
};
async function go(u, v) {
  logMsg(`moving to (${u.toFixed(2)}, ${v.toFixed(2)})...`);
  const r = await api('/api/goto_uv', {u, v});
  logMsg(r.error ? ('error: ' + r.error)
    : `at (${u.toFixed(2)}, ${v.toFixed(2)}) = (${r.x.toFixed(0)}, ${r.y.toFixed(0)}) mm, reached (${r.reached_x.toFixed(0)}, ${r.reached_y.toFixed(0)})`);
  refresh();
}
document.getElementById('gouv').onclick = () =>
  go(parseFloat(document.getElementById('u').value), parseFloat(document.getElementById('v').value));
document.getElementById('gorand').onclick = () => go(Math.random(), Math.random());
document.getElementById('torque').onclick = async () => { await api('/api/torque', {on: false}); refresh(); };
document.getElementById('toy').onclick = async () => {
  const r = await api('/api/toy', {on: !((st.toy || {}).on)});
  if (r.error) logMsg('error: ' + r.error);
  refresh();
};
document.querySelectorAll('[data-corner]').forEach(b => b.onclick = async () => {
  await api('/api/capture_corner', {corner: b.dataset.corner}); refresh();
});

// ---- workspace canvas (draw the box here) ----
const av = document.getElementById('arm'), atx = av.getContext('2d');
function scaleInfo() {
  const L1 = st.link1_mm || 162, L2 = st.link2_mm || 150, R = L1 + L2 + 30;
  const s = (Math.min(av.width, av.height)) / (2 * R);
  return {L1, L2, s, ox: av.width / 2, oy: av.height / 2};
}
// rotated so the calibrated center pose (+X) points UP; +Y points left
function mmToPx(x, y) { const {s, ox, oy} = scaleInfo(); return [ox - y * s, oy - x * s]; }
function pxToMm(px, py) { const {s, ox, oy} = scaleInfo(); return [(oy - py) / s, (ox - px) / s]; }
let dragStart = null, dragNow = null;
function drawArm() {
  const {L1, L2, s, ox, oy} = scaleInfo();
  atx.clearRect(0, 0, av.width, av.height);
  atx.strokeStyle = '#39404d'; atx.lineWidth = 1;
  atx.beginPath(); atx.arc(ox, oy, (L1 + L2) * s, 0, 7); atx.stroke();
  atx.beginPath(); atx.arc(ox, oy, Math.abs(L1 - L2) * s, 0, 7); atx.stroke();
  const ks = ['c00','c10','c11','c01'];
  if (ks.every(k => (st.corners || {})[k])) {
    atx.strokeStyle = '#5b8dd9'; atx.lineWidth = 2; atx.beginPath();
    ks.forEach((k, i) => { const c = st.corners[k]; const [px, py] = mmToPx(c.x, c.y);
      i ? atx.lineTo(px, py) : atx.moveTo(px, py); });
    atx.closePath(); atx.stroke(); atx.lineWidth = 1;
  }
  if (dragStart && dragNow) {
    atx.strokeStyle = '#e8b04a'; atx.setLineDash([6, 4]);
    atx.strokeRect(Math.min(dragStart[0], dragNow[0]), Math.min(dragStart[1], dragNow[1]),
                   Math.abs(dragNow[0] - dragStart[0]), Math.abs(dragNow[1] - dragStart[1]));
    atx.setLineDash([]);
  }
  const a = st.angles || {shoulder: 0, elbow: 0};
  const t1 = a.shoulder * Math.PI / 180, t12 = t1 + a.elbow * Math.PI / 180;
  const ex = L1 * Math.cos(t1), ey = L1 * Math.sin(t1);
  const bx = ex + L2 * Math.cos(t12), by = ey + L2 * Math.sin(t12);
  atx.strokeStyle = '#e8e8e8'; atx.lineWidth = 4; atx.lineCap = 'round';
  atx.beginPath(); atx.moveTo(...mmToPx(0, 0)); atx.lineTo(...mmToPx(ex, ey)); atx.lineTo(...mmToPx(bx, by)); atx.stroke();
  atx.lineWidth = 1;
  atx.fillStyle = '#7dc87d';
  [[0, 0], [ex, ey]].forEach(([x, y]) => {
    const [px, py] = mmToPx(x, y); atx.beginPath(); atx.arc(px, py, 5, 0, 7); atx.fill(); });
  const [px, py] = mmToPx(bx, by);
  atx.fillStyle = '#e8b04a'; atx.beginPath(); atx.arc(px, py, 7, 0, 7); atx.fill();
  atx.fillStyle = '#9ab'; atx.font = '12px sans-serif';
  atx.fillText(`shoulder ${(a.shoulder ?? 0).toFixed(1)}°  elbow ${(a.elbow ?? 0).toFixed(1)}°  button (${bx.toFixed(0)}, ${by.toFixed(0)}) mm`, 10, 16);
}
av.onmousedown = (e) => {
  const r = av.getBoundingClientRect();
  dragStart = dragNow = [e.clientX - r.left, e.clientY - r.top];
};
av.onmousemove = (e) => {
  if (!dragStart) return;
  const r = av.getBoundingClientRect();
  dragNow = [e.clientX - r.left, e.clientY - r.top];
  drawArm();
};
av.onmouseup = async (e) => {
  const r = av.getBoundingClientRect();
  const end = [e.clientX - r.left, e.clientY - r.top];
  const start = dragStart;
  dragStart = dragNow = null;
  const dx = Math.abs(end[0] - start[0]), dy = Math.abs(end[1] - start[1]);
  if (dx < 8 && dy < 8) {  // a click: send the button there
    const [x, y] = pxToMm(end[0], end[1]);
    logMsg(`moving to (${x.toFixed(0)}, ${y.toFixed(0)}) mm...`);
    const res = await api('/api/goto_xy', {x, y});
    logMsg(res.error ? ('error: ' + res.error)
      : `reached (${res.reached_x.toFixed(0)}, ${res.reached_y.toFixed(0)}) mm`);
    refresh();
    return;
  }
  // a drag: the box. Canvas corners -> mm; keep the quad order c00,c10,c11,c01.
  const left = Math.min(start[0], end[0]), right = Math.max(start[0], end[0]);
  const top = Math.min(start[1], end[1]), bottom = Math.max(start[1], end[1]);
  const corners = {
    c00: pxToMm(left, top), c10: pxToMm(right, top),
    c11: pxToMm(right, bottom), c01: pxToMm(left, bottom),
  };
  const payload = {};
  for (const [k, [x, y]] of Object.entries(corners)) payload[k] = {x, y};
  const res = await api('/api/set_corners', payload);
  logMsg(res.error ? ('error: ' + res.error) : 'box saved');
  refresh();
};

async function refresh() {
  st = await api('/api/status');
  const a = st.angles || {};
  document.getElementById('status').textContent =
    `shoulder ${((a.shoulder ?? 0)).toFixed(1)} deg   elbow ${((a.elbow ?? 0)).toFixed(1)} deg\n` +
    `button XY (${(st.x ?? 0).toFixed(1)}, ${(st.y ?? 0).toFixed(1)}) mm`;
  const toy = st.toy || {};
  const tb = document.getElementById('toy');
  tb.textContent = `Toy mode: ${toy.on ? 'ON' : 'OFF'} — ${toy.successes || 0} pressed / ${toy.failures || 0} timed out`;
  tb.classList.toggle('armed', !!toy.on);
  document.getElementById('corners').innerHTML = ['c00','c10','c11','c01'].map(k => {
    const c = (st.corners || {})[k];
    return c ? `<span class="corner-done">${k}: (${c.x.toFixed(0)}, ${c.y.toFixed(0)})</span>` : `${k}: &mdash;`;
  }).join('<br>');
  drawGrid(); drawArm();
}
refresh(); setInterval(refresh, 500);
</script></body></html>"""


def cmd_ui(args: argparse.Namespace) -> int:
    import random
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    bus, rig = _make_rig(args)
    lock = threading.Lock()
    grid: dict[str, dict[str, float]] = {}
    if GRID_PATH.exists():
        grid = json.loads(GRID_PATH.read_text())
    last_uv: list[float] | None = None

    # Toy mode: each press of the rig's own button sends it to a random
    # location in the box; no press within the timeout also relocates it.
    toy: dict[str, object] = {"on": False, "successes": 0, "failures": 0,
                              "timeout_s": args.timeout_s, "error": None}
    listener_box: dict[str, ButtonListener | None] = {"l": None}

    def _ensure_listener() -> ButtonListener | None:
        if listener_box["l"] is None:
            try:
                listener_box["l"] = ButtonListener()
                toy["error"] = None
            except BaseException as exc:  # noqa: BLE001 - pynput/permission issues
                toy["error"] = f"{type(exc).__name__}: {exc}"
        return listener_box["l"]

    toy_log_path = LOG_DIR / f"toy_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"

    def _toy_relocate() -> None:
        nonlocal last_uv
        u, v = random.random(), random.random()
        x, y = grid_to_xy(grid, u, v)
        with lock:
            rig.goto_xy(x, y)
        last_uv = [u, v]

    def _toy_loop() -> None:
        window_start: float | None = None
        while True:
            listener = listener_box["l"]
            if listener is None or not toy["on"]:
                window_start = None
                time.sleep(0.2)
                continue
            if any(k not in grid for k in GRID_CORNERS):
                time.sleep(0.5)
                continue
            if window_start is None:
                listener.clear()
                window_start = time.monotonic()
            press = listener.wait_for_press(timeout_s=0.5)
            elapsed = time.monotonic() - window_start
            timeout_s = float(toy.get("timeout_s") or 60.0)
            if press is None and elapsed < timeout_s:
                continue
            success = press is not None
            record = {
                "uv": last_uv,
                "success": success,
                "time_to_press_s": round(elapsed, 2) if success else None,
                "timeout_s": timeout_s,
                "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            toy_log_path.parent.mkdir(parents=True, exist_ok=True)
            with toy_log_path.open("a") as f:
                f.write(json.dumps(record) + "\n")
            key = "successes" if success else "failures"
            toy[key] = int(toy.get(key) or 0) + 1
            try:
                _toy_relocate()
            except ValueError:
                pass
            if listener_box["l"] is not None:
                listener_box["l"].clear()
            window_start = None

    threading.Thread(target=_toy_loop, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:
            pass

        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                body = RIG_UI_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/status":
                with lock:
                    angles = rig.read_angles()
                    x, y = forward_kinematics(
                        angles["shoulder"], angles["elbow"], rig.cal.link1_mm, rig.cal.link2_mm
                    )
                self._json(200, {"angles": angles, "x": x, "y": y, "corners": grid,
                                 "last_uv": last_uv, "toy": toy,
                                 "link1_mm": rig.cal.link1_mm, "link2_mm": rig.cal.link2_mm})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            nonlocal last_uv
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length) or b"{}")
            try:
                if self.path == "/api/torque":
                    with lock:
                        for j in rig.cal.joints.values():
                            rig.bus.torque(j.id, bool(req.get("on")))
                    self._json(200, {"ok": True})
                elif self.path == "/api/capture_corner":
                    corner = req.get("corner")
                    if corner not in GRID_CORNERS:
                        self._json(400, {"error": f"corner must be one of {GRID_CORNERS}"})
                        return
                    with lock:
                        x, y = rig.read_xy()
                    grid[corner] = {"x": round(x, 1), "y": round(y, 1)}
                    save_grid(grid)
                    self._json(200, {"ok": True, "corner": corner, "x": x, "y": y})
                elif self.path == "/api/set_corners":
                    corners = {k: req.get(k) for k in GRID_CORNERS}
                    missing = [k for k, c in corners.items() if not isinstance(c, dict)]
                    if missing:
                        self._json(400, {"error": f"missing corners {missing}"})
                        return
                    bad = []
                    for k, c in corners.items():
                        try:
                            rig.solve_xy(float(c["x"]), float(c["y"]))
                        except ValueError as exc:
                            bad.append(f"{k}: {exc}")
                    if bad:
                        self._json(400, {"error": "box leaves the reachable workspace — "
                                         + "; ".join(bad)})
                        return
                    grid.clear()
                    for k, c in corners.items():
                        grid[k] = {"x": round(float(c["x"]), 1), "y": round(float(c["y"]), 1)}
                    save_grid(grid)
                    self._json(200, {"ok": True, "corners": grid})
                elif self.path == "/api/toy":
                    want_on = bool(req.get("on"))
                    if want_on:
                        if _ensure_listener() is None:
                            self._json(500, {"error": f"button listener failed: {toy['error']}; "
                                             "on macOS grant Input Monitoring to the terminal"})
                            return
                        missing = [k for k in GRID_CORNERS if k not in grid]
                        if missing:
                            self._json(400, {"error": f"draw the box first (missing {missing})"})
                            return
                    toy["on"] = want_on
                    self._json(200, {"ok": True, "toy": toy})
                elif self.path == "/api/goto_uv":
                    missing = [k for k in GRID_CORNERS if k not in grid]
                    if missing:
                        self._json(400, {"error": f"draw the box first (missing {missing})"})
                        return
                    u = max(0.0, min(1.0, float(req.get("u", 0.5))))
                    v = max(0.0, min(1.0, float(req.get("v", 0.5))))
                    x, y = grid_to_xy(grid, u, v)
                    with lock:
                        rig.goto_xy(x, y, velocity=int(req.get("velocity", 400)))
                        rx, ry = rig.read_xy()
                    last_uv = [u, v]
                    self._json(200, {"ok": True, "u": u, "v": v, "x": x, "y": y,
                                     "reached_x": rx, "reached_y": ry})
                elif self.path == "/api/goto_xy":
                    x, y = float(req.get("x")), float(req.get("y"))
                    with lock:
                        rig.goto_xy(x, y, velocity=int(req.get("velocity", 400)))
                        rx, ry = rig.read_xy()
                    last_uv = None
                    self._json(200, {"ok": True, "x": x, "y": y,
                                     "reached_x": rx, "reached_y": ry})
                else:
                    self._json(404, {"error": "not found"})
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except BaseException as exc:  # noqa: BLE001 - surface bus errors to the UI
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    server = ThreadingHTTPServer(("0.0.0.0", args.ui_port), Handler)
    print(f"button rig UI: http://localhost:{args.ui_port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        rig.torque_off()
        bus.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--port", default=DEFAULT_PORT,
                        help="serial device of the servo driver board (or set BUTTON_RIG_PORT)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="find servos on the bus").set_defaults(func=cmd_scan)

    p = sub.add_parser("setup-id", help="assign an ID to the one servo on the bus")
    p.add_argument("--id", type=int, required=True, choices=sorted(MOTOR_IDS.values()))
    p.set_defaults(func=cmd_setup_id)

    sub.add_parser("read", help="print joint angles and button XY").set_defaults(func=cmd_read)

    sub.add_parser("calibrate", help="interactive zero/sign/range calibration").set_defaults(
        func=cmd_calibrate
    )

    p = sub.add_parser("goto", help="move the button to --x/--y mm or --u/--v in the box")
    p.add_argument("--x", type=float)
    p.add_argument("--y", type=float)
    p.add_argument("--u", type=float, help="box coordinate 0-1")
    p.add_argument("--v", type=float, help="box coordinate 0-1")
    p.add_argument("--elbow", choices=("up", "down"), default="up")
    p.add_argument("--velocity", type=int, default=400)
    p.set_defaults(func=cmd_goto)

    sub.add_parser("listen", help="print button presses as they arrive").set_defaults(
        func=cmd_listen
    )

    p = sub.add_parser("ui", help="web UI: draw the box, test moves, toy mode")
    p.add_argument("--ui-port", type=int, default=int(os.environ.get("BUTTON_RIG_UI_PORT", "8095")))
    p.add_argument("--timeout-s", type=float, default=60.0,
                   help="toy mode: relocate after this long without a press")
    p.set_defaults(func=cmd_ui)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "goto" and (args.x is None or args.y is None) and (
        args.u is None or args.v is None
    ):
        print("goto needs both --x/--y (mm) or both --u/--v (box 0-1)", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
