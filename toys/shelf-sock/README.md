# Sock on shelf

**Task:** "Place the red sock on the shelf in front."

The robot picks a red sock off the table and places it on a small raised shelf.
Deformable-object grasping plus a placement above the table plane — and the
rig resets *itself*: the shelf is hinged, so after every attempt a recorded
flip motion tips the sock back onto the table.

## Parts

| Part | Notes |
|---|---|
| 1× small shelf on a hinge | A platform ~10–15 cm above the table at the front edge of the workspace, mounted so it can tip forward and dump its contents. Ours is flipped by the arm itself replaying a recorded motion; a hobby servo on the hinge works just as well. |

Placement: shelf at the front of the workspace, sock starting anywhere on the
table inside reach.

## Printed parts

[`stl/shelf.stl`](stl/shelf.stl) is the full assembly; [`stl/parts/`](stl/parts/)
has the individual pieces:

| Part | Size (mm) | What it is |
|---|---|---|
| [`parts/shelf.stl`](stl/parts/shelf.stl) | 200 × 135 × 170 | the main shelf body with the hinge |
| [`parts/shelf_left.stl`](stl/parts/shelf_left.stl) / [`parts/shelf_right.stl`](stl/parts/shelf_right.stl) | ~100 × 92 × 7 each | the two halves of the tipping platform |
| [`parts/handle.stl`](stl/parts/handle.stl) | 25 × 39 × 39 | handle the arm pushes to flip the shelf |
| [`parts/plate.stl`](stl/parts/plate.stl) | 200 × 225 × 14 | base plate that anchors the shelf in the workspace |
| [`parts/alignment.stl`](stl/parts/alignment.stl) | 210 × 80 × 15 | alignment piece that registers the plate at a repeatable spot (same part as the cup toy's) |

## Success detection

Scored from the fixed front camera with one segmentation prompt:

- **Object prompt:** `red fabric`

Success = the **bottom edge** of the sock's mask sits above the shelf line for
at least **5 consecutive frames**, *and* the arm's end effector has retreated
from the shelf (end-effector x ≤ 0.21 m in our arm frame — tune to your rig).
The retreat condition stops the check from firing while the gripper is still
holding the sock up there: it has to stay on the shelf on its own.

**Failure:** 60 seconds with no success.

## Reset

Fully automatic. After every attempt (success or failure) a pre-recorded
trajectory flips the shelf, dumping the sock back into the workspace, then the
arm returns home. Record the flip once via teleoperation and replay it — the
rig needs no extra actuators if the arm itself does the flipping.

One sharp edge we hit: give each toy its **own** reset recording. An early bug
pointed the ball-to-cup task at the shelf-flip replay, and the arm dutifully
flipped an empty shelf between ball attempts.
