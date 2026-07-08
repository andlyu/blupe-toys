# Ball to cup

**Task:** "Move to the light blue ball, grab it, and move it to the tall black
cylinder."

The robot has to locate a small light-blue ball on the table, grasp it, carry
it, and release it into a tall black cylinder (the "cup"). It exercises the
full pick-and-place loop: visual search, a precise grasp on a curved object,
and a placement that only counts when the ball actually goes *in*.

*(photo coming soon)*

## Parts

| Part | Notes |
|---|---|
| 1× light-blue ball, ~4 cm | Soft/squishy grips far better than hard plastic. Matte light blue segments cleanly and is rare enough in a workspace not to false-positive. |
| 1× tall black cylinder, ~8–10 cm ⌀ | A matte black cup, tumbler, or a piece of black-taped PVC/cardboard tube. Tall enough that the ball can't bounce out, open on top. Matte black gives a crisp mask. |

Placement: ball and cylinder both inside the arm's reach, far enough apart
that the carry is nontrivial (we use ~15–20 cm). Vary both positions between
attempts if you want a distribution rather than a single layout.

## Printed parts

[`stl/cup.stl`](stl/cup.stl) — the full cup assembly, ready to print. Print in
black (or paint/tape it matte black) so the container mask segments cleanly.
Individual component STLs will be added.

## Success detection

Scored from the fixed front camera with two segmentation prompts:

- **Object prompt:** `light blue object`
- **Container prompt:** `black cylinder inside`

Success = the ball's mask **ends up overlapping** the container mask — i.e. the
ball disappears into the cylinder's interior region and stays there. A ball
merely held above or brushing past the rim doesn't count; the overlap has to be
where the ball comes to rest.

**Failure:** 60 seconds with no success.

## Reset

No automated reset yet — after a success the ball is inside the cup, so a human
(or a scripted arm motion, if you record one) has to return it to the table.
Between attempts the arm returns to its home pose. This is the one toy of the
three that still needs a human in the loop for long unattended runs; a
teleop-recorded "dump the cup and place the ball" replay is the planned fix.
