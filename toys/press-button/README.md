# Press the button

**Task:** "Reach to the red button and press it."

▶ **[Watch it run](https://youtu.be/fBEsYfOkB0k)**

The simplest task, with the most interesting rig. The button is a real USB
keyboard key, so success is an electrical event — no vision, no ambiguity, no
tuning. And the button never stays put: a small 2-servo SCARA arm slides it to
a new random spot after every press, so the policy can't memorize one position
and an eval can run unattended forever. The same rig extends to plugging and
unplugging tasks — think datacenter cabling.

## Bill of materials

| Qty | Part | Link | Notes |
|---|---|---|---|
| 2 | Feetech STS3215 serial bus servo | [Feetech](https://www.feetechrc.com/en/2020-05-13_56655.html) / widely resold | Shoulder + elbow of the SCARA rig. Same servo the SO-101 uses. |
| 1 | Waveshare ST/SC Serial Bus Servo Driver Board | [Amazon B0CJBKQ8LJ](https://www.amazon.com/dp/B0CJBKQ8LJ) | USB↔serial-bus adapter that powers and drives both servos. If you're already running an SO-101, you can instead hang the rig's servos off the arm's existing bus (give them IDs outside the arm's 1–6). |
| 1 | Single-key programmable USB keypad | [Amazon B0D7GXV5LD](https://www.amazon.com/dp/B0D7GXV5LD) | The button itself — a one-key USB "keyboard". Program it to type `1`; that keystroke is the success signal. Any programmable macro key (e.g. SayoDevice 1×1P) works. |
| 1 | 9–12 V DC power supply, 5.5×2.1 mm barrel | — | Powers the driver board and servos (skip if sharing the SO-101 bus). |
| 1 | Printed parts: base, two links, key mount | [`stl/button.stl`](stl/button.stl) | Shoulder→elbow 162 mm, elbow→button 150 mm in our build. Exact lengths don't matter; they're calibration inputs. |
| 1 | Red button cap | — | Make the key look like "the red button" from the front camera. Paint or a printed cap both work. |

## Printed parts

[`stl/button.stl`](stl/button.stl) is the full assembly; [`stl/parts/`](stl/parts/)
has the individual pieces:

| Part | What it is |
|---|---|
| [`parts/base.stl`](stl/parts/base.stl) | the rig's base |
| [`parts/base_servo_holder.stl`](stl/parts/base_servo_holder.stl) | shoulder-servo holder that mounts into the base |
| [`parts/lower_arm.stl`](stl/parts/lower_arm.stl) | link 1 (shoulder → elbow) |
| [`parts/upper_arm.stl`](stl/parts/upper_arm.stl) | link 2 (elbow → button) |
| [`parts/mounting_plate.stl`](stl/parts/mounting_plate.stl) | mount for the USB key at the end effector |

## Setup

Everything runs from [`button_rig.py`](button_rig.py) in this folder.

```bash
pip install feetech-servo-sdk pynput
export BUTTON_RIG_PORT=/dev/cu.usbserial-XXXX   # your driver board's serial device
                                                # (Linux: /dev/ttyUSB0 or /dev/ttyACM0)
```

**0. Assign servo IDs** (once, fresh servos all ship as ID 1). With only the
shoulder servo plugged into the board, then only the elbow:

```bash
python3 button_rig.py setup-id --id 1   # shoulder alone on the bus
python3 button_rig.py setup-id --id 2   # elbow alone on the bus
```

**A. Scan** — connect both servos and confirm the bus sees them:

```bash
python3 button_rig.py scan
# baud=1000000 id=1 model=...
# baud=1000000 id=2 model=...
```

If nothing shows up, check the 12 V supply and the 3-pin servo cable.

**B. Calibrate** — an interactive pass with torque off; you move the arm by
hand through four prompts (middle pose, two direction checks, then a sweep of
both joints to their limits). Writes `config/calibration.json`.

```bash
python3 button_rig.py calibrate
python3 button_rig.py read      # verify: move the arm by hand, watch XY track
```

**C. Draw the box** — open the web UI and drag a rectangle on the workspace
canvas to define where the button is allowed to go. The UI shows the reachable
annulus and the live arm pose; corners that leave the workspace are rejected.
You can also capture corners physically: torque off, hand-place the button at
each corner, click the corner buttons. Saved to `config/grid.json`.

```bash
python3 button_rig.py ui        # http://localhost:8095
```

Then flip on **Toy mode** in the UI: every press of the button (and every
60 s timeout without one) slides it to a new random spot in the box, and each
attempt is logged to `logs/*.jsonl`. Test the keystroke path first with
`python3 button_rig.py listen` — on macOS the terminal needs Input Monitoring
permission (System Settings → Privacy & Security).

## How the rig works

The two servos form a planar SCARA arm with the button at the end effector.
Two-link forward/inverse kinematics turn (shoulder, elbow) angles into a
button (x, y) on the table and back. One interactive calibration pass
establishes each servo's zero, sign, and range, plus the four corners of the
reachable **grid square** the button is allowed to visit; after that,
"move the button to a random spot" is one IK call with `x, y ∈ [0, 1]` mapped
into that square.

## Success detection

- **Mode:** external (electrical), no vision.
- Success = the host receives a `1` keystroke from the button. That's it — a
  press is a press, whether it happens mid-rollout or during a human
  intervention.

**Failure:** 60 seconds with no press.

## Reset

Fully automatic, and unlike the other toys the arm **never homes** between
attempts — the policy keeps rolling from wherever it is, like a real
button-pressing job:

1. Two seconds after any counted press, the SCARA rig slides the button to a
   uniformly random spot inside the calibrated grid square.
2. Every fresh eval also starts with a random slide, so a run never inherits
   the button position the previous session ended on.
3. If the rig fails to move, the eval aborts loudly rather than silently
   grinding against a stuck button.

## Software

[`button_rig.py`](button_rig.py) is the whole driver: scan / setup-id /
calibrate / read / goto / listen subcommands, the two-link FK/IK, the press
listener, and the web UI with toy mode. It only needs `feetech-servo-sdk` and
`pynput`. Machine-local state (calibration, the box) lands in `config/` and
attempt logs in `logs/`, both untracked.
