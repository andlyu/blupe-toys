# blupe-toys

Self-resetting environments — toys your robots will play with for hours.

It's underappreciated how close to perfect the performance of a robot needs to
be to be profitable, and getting there takes an enormous amount of
experimentation across data, hardware, and machine learning. In CV or LLMs,
the same test set can be used forever. In robotics, each test needs to be
manually reset and evaluated for success. That doesn't scale — measuring a
policy at the 90%+ level with any confidence takes 40–50 rollouts per
checkpoint, every rollout needs a human to reset the scene and judge success,
and improving a policy means doing that over and over for each test.

The way to automate evals is to build the environment so that A) resetting it
is easier than doing the task, and B) success is scored automatically.
Evals like that run while you grab a bite, join a meeting, or take a nap —
with DAgger-style interventions layered on top, this loop took MolmoAct from
62% zero-shot to 91% in five iterations, with roughly 30 minutes of
intermittent attention instead of 5 hours of a person resetting objects.

This repo is for setting up the three toys we built to do it — print files,
bills of materials, success criteria, and setup code for each:

| Toy | Task | Success signal | Auto-reset | Demo |
|---|---|---|---|---|
| [Ball to cup](toys/ball-to-cup/) | Drop a light-blue ball into a tall black cylinder | Vision: ball mask intersects the cup mask, then comes to rest | Yes — the cup is shaped to roll the ball back out, to a random spot | [video](https://youtu.be/Tn7ImfhEiuk) |
| [Shelf](toys/shelf/) | Place an object on a small shelf | Vision: object mask sits above the shelf line for 5+ frames | Yes — the shelf flips and dumps the object back | [video](https://youtu.be/QhoUHm92rZE) |
| [Press the button](toys/press-button/) | Reach out and press a red button | Electrical: the button is a USB key that types `1` when pressed | Yes — a 2-servo rig slides the button to a new random spot after every press | [video](https://youtu.be/fBEsYfOkB0k) |

Each toy's folder has the full walkthrough. The toys were built around the
[SO-101](https://github.com/TheRobotStudio/SO-ARM100) arm, but nothing about
them is arm-specific: any arm that can reach a ~30 cm tabletop workspace can
run them.
