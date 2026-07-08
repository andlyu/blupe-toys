# Shelf

**TLDR:** an interesting use case for how a replayed trajectory can reset a
task. Once an object reaches the shelf, all the reset needs to do is hit the
lever. The task lends itself to more complex variants — shelving, stacking,
or even construction, if the parts come apart on their own when they fall.

**Task:** "Place the object on the shelf in front."

▶ **[Watch it run](https://youtu.be/QhoUHm92rZE)** — in the video the pickup is
teleoperated and the reset runs autonomously.

The robot picks an object off the table and places it on a small raised shelf.
Grasping plus a placement above the table plane — and the rig resets *itself*:
the shelf is hinged, so after every attempt a recorded flip motion tips the
object back onto the table.

Any graspable object works — pick one and set the success prompt to match. In
our example runs the object was a rolled red sock: deformable, so it's
forgiving to grasp but hard to place tidily, and saturated red segments
cleanly. The same rig also extends past pick-and-place: sorting, stacking, or
even insertion can be tested with whatever you put on the table.

## Parts

| Part | Notes |
|---|---|
| 1× small shelf on a hinge | A platform ~10–15 cm above the table at the front edge of the workspace, mounted so it can tip forward and dump its contents. Ours is flipped by the arm itself replaying a recorded motion; a hobby servo on the hinge works just as well. |
| 1× object to place | Your choice. Something with a saturated, workspace-unique color makes the success mask trivial. |

Placement: shelf at the front of the workspace, object starting anywhere on
the table inside reach.

## Printed parts

[`stl/shelf.stl`](stl/shelf.stl) is the full assembly; [`stl/parts/`](stl/parts/)
has the individual pieces:

| Part | What it is |
|---|---|
| [`parts/shelf.stl`](stl/parts/shelf.stl) | the main shelf body with the hinge |
| [`parts/shelf_left.stl`](stl/parts/shelf_left.stl) / [`parts/shelf_right.stl`](stl/parts/shelf_right.stl) | the two halves of the tipping platform |
| [`parts/handle.stl`](stl/parts/handle.stl) | handle the arm pushes to flip the shelf |
| [`parts/plate.stl`](stl/parts/plate.stl) | base plate that anchors the shelf in the workspace |
| [`parts/alignment.stl`](stl/parts/alignment.stl) | alignment piece that registers the plate at a repeatable spot relative to an SO-101 arm (same part as the cup toy's) |

## Success detection

Scored from the fixed front camera with one segmentation prompt describing
your object (we used `red fabric` for the sock).

Success = the **bottom edge** of the object's mask sits above the shelf line
for at least **5 consecutive frames**, *and* the arm's end effector has
retreated from the shelf (end-effector x ≤ 0.21 m in our arm frame — tune to
your rig). The retreat condition stops the check from firing while the gripper
is still holding the object up there: it has to stay on the shelf on its own.

**Failure:** 60 seconds with no success.

## Reset

Fully automatic. After every attempt (success or failure) a pre-recorded
trajectory flips the shelf, dumping the object back into the workspace, then
the arm returns home. Record the flip once via teleoperation and replay it —
the rig needs no extra actuators if the arm itself does the flipping.

One sharp edge we hit: give each toy its **own** reset recording. An early bug
pointed the ball-to-cup task at the shelf-flip replay, and the arm dutifully
flipped an empty shelf between ball attempts.
