# blupe-toys

Cheap, reproducible tabletop tasks for evaluating robot manipulation policies.

Most robot policy evals stall on the boring parts: how do you *score* an attempt
without a human watching, and how do you *reset* the scene so the robot can try
again all night? Each toy here is a small physical rig that answers both
questions — a task with an unambiguous success signal, and a story for getting
the scene back to a startable state between attempts.

The toys were built around the [SO-101](https://github.com/TheRobotStudio/SO-ARM100)
arm (a ~$120 3D-printable 6-DOF arm), but nothing about them is arm-specific:
any arm that can reach a ~30 cm tabletop workspace can run them.

## The toys

| Toy | Task | Success signal | Auto-reset |
|---|---|---|---|
| [Ball to cup](toys/ball-to-cup/) | Drop a light-blue ball into a tall black cylinder | Vision: ball mask ends up inside the cylinder mask | Not yet (arm homes; ball stays in cup) |
| [Shelf](toys/shelf/) | Place an object on a small shelf | Vision: object mask sits above the shelf line for 5+ frames | Yes — the shelf flips and dumps the object back |
| [Press the button](toys/press-button/) | Reach out and press a red button | Electrical: the button is a USB key that types `1` when pressed | Yes — a 2-servo rig slides the button to a new random spot after every press |

They form a difficulty ladder for success detection, too:

1. **Press the button** needs no vision at all — success is a keystroke.
2. **Shelf** needs one segmentation mask and a line test.
3. **Ball to cup** needs two masks and an overlap test.

## What "success detection" means here

The vision-scored toys use a promptable segmenter (we use
[SAM 3](https://ai.meta.com/sam3/)) on a fixed front camera: you give it a text
prompt like `"red fabric"` or `"black cylinder inside"`, it gives you a mask
per frame, and success is a simple geometric test on those masks. Any
detector/segmenter that turns a text prompt into a mask will work. Each toy's
README states its exact prompts and test.

Every task also has a **failure timeout** (60 s with no success ⇒ the attempt
is scored as a failure), so an eval run never hangs.

## What's in this repo today

Hardware specs, parts lists, and success/reset definitions for the three toys —
enough to build the rigs and score attempts with your own stack. The eval
software we run on top of these (policy server, success tracker, scene-reset
replay, web UI) lives in our research repo and will be published as it
stabilizes.

## Common setup

All three toys assume:

- A tabletop arm with roughly a 30 cm reach (we use the SO-101 follower, plus a
  leader arm for teleoperated demonstrations).
- A fixed **front camera** looking at the workspace (the vision toys are scored
  from this view), plus optional side and wrist cameras for policy input.
- A host computer that can see the cameras and the arm's serial port.

## License

MIT — do whatever you want with it.
