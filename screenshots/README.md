# Visual baselines

Ten screenshots — five desktop at 1440px, five mobile at 480px — that CI
compares every run against. A difference above 1% of pixels fails the build.

## Why they are committed images

Three defects reached production because nobody could see the interface: an 8px
type scale, a dropdown truncating the town name being chosen, and — found by
looking at the first CI capture, before these baselines existed — a dashboard
toolbar printing its buttons on top of each other. All three are valid CSS.
They typecheck, they lint, they build. Only a rendered picture shows them.

## Why they come from CI, never from a laptop

Font rendering, device pixel ratio and Chrome version all differ between a
developer's machine and a GitHub runner. A baseline shot locally makes CI red
on its first run and stays red, which is how a visual check gets switched off.
These are the artifacts of run 34538906931 on `ubuntu-latest`.

## Updating them

When a change is *meant* to alter the interface, the visual job fails, and that
is the check working. Then:

1. Read the diff percentages the job prints, and download the artifacts.
2. **Look at the new screenshots.** This is the only step that matters. A
   baseline updated without looking freezes whatever broke as the new truth.
3. Copy the artifacts over these files and commit them with the change that
   caused them.

## What the check cannot do

It compares pixels, so it sees layout, colour and type. It knows nothing about
whether a button does the right thing when pressed. And it only covers what
`scripts/ci_ui_shots.py` walks through: login, landing, dashboard, campaign
edit, settings. The corridor results view is not in it yet — it needs a route
in the fixture database, which `scripts/seed_fixture_db.js` does not build.
