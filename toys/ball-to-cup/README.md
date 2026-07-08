# Ball to cup

**Task:** "Move to the light blue ball, grab it, and move it to the tall black
cylinder."

▶ **[Watch it run](https://youtu.be/Tn7ImfhEiuk)**

The robot locates a small light-blue ball on the table, grasps it, carries it,
and drops it into a black cup. The trick is in the cup: it's modified so the
ball rolls back out onto the plate. That makes the environment **self-resetting
by mechanics alone** — and because the ball isn't perfectly round, it comes to
rest somewhere new after every attempt, so you get scene randomization for
free.

## Parts

| Part | Notes |
|---|---|
| 1× light-blue ball, ~4 cm | Soft/squishy grips far better than hard plastic. Matte light blue segments cleanly and is rare enough in a workspace not to false-positive. A slightly imperfect ball is a feature here: it rolls out to a different spot every time. |
| 1× modified cup | Printed below — open on top, shaped so a dropped ball rolls back out onto the plate. Fix it firmly to the table: the arm will hit it eventually. |

Placement: cup anchored on its plate, ball starting anywhere inside reach.

## Printed parts

[`stl/cup.stl`](stl/cup.stl) is the full assembly; [`stl/parts/`](stl/parts/)
has the individual pieces:

| Part | What it is |
|---|---|
| [`parts/cup.stl`](stl/parts/cup.stl) | the cup itself — print in black (or make it matte black) so the container mask segments cleanly |
| [`parts/plate.stl`](stl/parts/plate.stl) | base plate that anchors the cup in the workspace |
| [`parts/alignment.stl`](stl/parts/alignment.stl) | alignment piece that registers the plate at a repeatable spot (same part as the shelf toy's) |

## Success detection

Tracked from the fixed front camera. This toy needs **video mask tracking**
(we use SAM3-video seeded with pre-determined masks for the ball and the cup)
— re-prompting a per-image segmenter every frame was too slow to catch the
ball rolling through.

Success = the ball's mask **intersects the cup's mask and then comes to
rest**: the ball went in, rolled back out, and stopped. A ball merely carried
past the cup doesn't count, and neither does one still rolling.

**Failure:** 60 seconds with no success.

## Reset

Self-resetting — the cup returns the ball to the plate at a semi-random spot,
and the arm just homes between attempts. No recorded trajectories, no human in
the loop.
