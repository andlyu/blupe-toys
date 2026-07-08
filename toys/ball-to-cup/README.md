# Ball to cup

**TLDR:** an object that can roll is moved into a cup — and it rolls back
out, resetting itself.

**Task:** "Move to the light blue ball, grab it, and move it to the tall black
cylinder."

▶ **[Watch it run](https://youtu.be/Tn7ImfhEiuk)**

The robot locates the ball on the table, grasps it, carries it, and drops it
into a black cup. The trick is in the cup: it's modified so the ball rolls
back out onto the plate. That makes the environment **self-resetting by
mechanics alone** — and because the ball isn't perfectly round, it comes to
rest somewhere new after every attempt, so you get scene randomization for
free. For our ball we made a rubber band ball and put it inside a light-blue
balloon.

## Parts

| Part | Notes |
|---|---|
| 1× rolling object | Anything works as long as it rolls and is non-deterministic — it shouldn't settle in the same spot twice. Ours is a rubber band ball inside a light-blue balloon: grippy, slightly irregular, and the balloon gives a saturated, workspace-unique color to segment. |
| 1× modified cup | Printed below — open on top, shaped so a dropped ball rolls back out onto the plate. Fix it firmly to the table: the arm will hit it eventually. |

Placement: cup anchored on its plate, ball starting anywhere inside reach.

## Printed parts

[`stl/cup.stl`](stl/cup.stl) is the full assembly; [`stl/parts/`](stl/parts/)
has the individual pieces:

| Part | What it is |
|---|---|
| [`parts/cup.stl`](stl/parts/cup.stl) | the cup itself — print in black (or make it matte black) so the container mask segments cleanly |
| [`parts/plate.stl`](stl/parts/plate.stl) | base plate that anchors the cup in the workspace |
| [`parts/alignment.stl`](stl/parts/alignment.stl) | alignment piece that registers the plate at a repeatable spot relative to an SO-101 arm (same part as the shelf toy's) |

## Success detection

Evaluations run SAM3 on the fixed front camera, tracking the ball's location
throughout the episode, with the cup tracked alongside it to handle the
overlap between the two. Use the **video** variant (SAM3-video) seeded with
pre-determined masks — re-prompting a per-image segmenter every frame was too
slow to catch the ball rolling through.

Success = the ball's mask **intersects the cup's mask and then comes to
rest**: the ball went in, rolled back out, and stopped. A ball merely carried
past the cup doesn't count, and neither does one still rolling.

**Failure:** 60 seconds with no success.

## Reset

Self-resetting — the cup returns the ball to the plate at a semi-random spot,
and the arm just homes between attempts. No recorded trajectories, no human in
the loop.
