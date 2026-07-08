# Sock on shelf

**Task:** "Place the red sock on the shelf in front."

The robot picks a red sock off the table and places it on a small raised shelf.
Deformable-object grasping plus a placement above the table plane — and the
rig resets *itself*: the shelf is hinged, so after every attempt a recorded
flip motion tips the sock back onto the table.

*(photo coming soon)*

## Parts

| Part | Notes |
|---|---|
| 1× red sock | A rolled or balled sock, saturated red so it segments cleanly. Deformable = forgiving to grasp but hard to place tidily, which is the point. |
| 1× small shelf on a hinge | A platform ~10–15 cm above the table at the front edge of the workspace, mounted so it can tip forward and dump its contents. Ours is flipped by the arm itself replaying a recorded motion; a hobby servo on the hinge works just as well. |

Placement: shelf at the front of the workspace, sock starting anywhere on the
table inside reach.

## Printed parts

[`stl/shelf.stl`](stl/shelf.stl) — the full hinged-shelf assembly, ready to
print. Individual component STLs will be added.

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
