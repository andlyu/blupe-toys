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

## DAgger-style intervention datasets

We improved MolmoAct on this task by running autonomous evaluations, taking
over with a leader arm when the policy drifted or got stuck, and saving the
human correction. We also recorded targeted demonstrations for failure modes
noticed in rollout replays. The resulting batches were aggregated with the
earlier data before each round of fine-tuning — a DAgger-style loop because
the new data focuses on states visited by the current policy.

The seven curated intervention batches are hosted as LeRobot datasets on
Hugging Face:

| Batch | Dataset | Episodes |
|---|---|---:|
| 1 | [`so101-ball-cup-intervene-edited_v21`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_v21) | 17 |
| 2 | [`so101-ball-cup-intervene-edited_2_v21`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_2_v21) | 17 |
| 3 | [`so101-ball-cup-intervene-edited_3_v21`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_3_v21) | 19 |
| 4 | [`so101-ball-cup-intervene-edited_4`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_4) | 53 |
| 5 | [`so101-ball-cup-intervene-edited_5`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_5) | 39 |
| 6 | [`so101-ball-cup-intervene-edited_6_v21`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_6_v21) | 18 |
| 7 | [`so101-ball-cup-intervene-edited_7_v21`](https://huggingface.co/datasets/andlyu/so101-ball-cup-intervene-edited_7_v21) | 25 |

Together they contain 188 episodes. Our training split uses 160 episodes and
holds out the final four episodes from every batch for validation.

Each episode contains front and wrist video at 30 fps, six SO-101 joint-state
values, and the corresponding six expert joint actions. The `_v21` suffix
means the state and action values were converted to the MolmoAct2 v2.1
SO100/SO101 joint convention; these are converted copies, not additional
collection rounds. The public source-format datasets are linked for batches 4
and 5 because their `_v21` conversions are not currently public.

## Non-DAgger ball-play datasets

These longer ball-play recordings are separate from the intervention batches
above. Together they contain 17 episodes and 114,800 frames (about 64 minutes
at 30 fps):

| Dataset | Episodes | Frames |
|---|---:|---:|
| [`play_with_blue_ball_20260711_020657`](https://huggingface.co/datasets/andlyu/play_with_blue_ball_20260711_020657) | 5 | 8,857 |
| [`play_with_blue_ball_20260711_022527`](https://huggingface.co/datasets/andlyu/play_with_blue_ball_20260711_022527) | 6 | 53,211 |
| [`play_with_blue_ball_20260711_031803`](https://huggingface.co/datasets/andlyu/play_with_blue_ball_20260711_031803) | 6 | 52,732 |

Each dataset contains six joint-state values, six corresponding actions, and
front, side, and wrist video.
