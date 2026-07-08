# Press the button

**Task:** "Reach to the red button and press it."

The simplest task, with the most interesting rig. The button is a real USB
keyboard key, so success is an electrical event — no vision, no ambiguity, no
tuning. And the button never stays put: a small 2-servo SCARA arm slides it to
a new random spot after every press, so the policy can't memorize one position
and an eval can run unattended forever.

*(photo coming soon)*

## Parts

| Part | ~Cost | Notes |
|---|---|---|
| 1× SayoDevice 1×1P key | ~$10 | A single-key USB "keyboard". When pressed it types a character (`1`) on the host. Any programmable USB macro key works. |
| 2× Feetech STS3215 servos | ~$15 ea | The same serial-bus servos the SO-101 uses, so they can share the follower arm's bus/controller board — just give them IDs outside the arm's 1–6. |
| 2 links + a base | printed/scrap | A planar two-link arm: shoulder→elbow 162 mm, elbow→button 150 mm in our build. Exact lengths don't matter; they're calibration inputs. |
| Red button cap | — | Make the key look like "the red button" from the front camera. |

## Printed parts

[`stl/button.stl`](stl/button.stl) — the full button-rig assembly (base, both
links, and the key mount), ready to print. Individual component STLs will be
added.

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

The rig driver (scan/calibrate/goto/poses/listen subcommands, FK/IK, the
press-listener) is a single Python file in our research stack and will be
published here. Until then the spec above is everything you need to reimplement
it: two bus servos, two-link IK, a corner-calibrated grid, and a USB key.
