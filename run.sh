#!/usr/bin/env bash

set -e

APP=~/git/dynamo-skips-app
PYTORCH_REPO=~/git/pytorch313
WORKTREE=~/git/pytorch-viable

# Reuse an existing env from the pytorch workspace rather than declaring a new
# one. Note the editable install below repoints this env's torch at $WORKTREE,
# which is deleted at the end of the run.
PIXI_WORKSPACE=pytorch
PIXI_ENV=pytorch313

# The worktree is built from scratch each run and torn down afterwards, so a
# week's results never depend on state left by the previous week. --force
# because the build leaves untracked artifacts and moves submodule pointers.
cleanup() {
    git -C "$PYTORCH_REPO" worktree remove --force "$WORKTREE" 2>/dev/null || true
    git -C "$PYTORCH_REPO" worktree prune
}

# Tear down only on success. A failed cold build is the case most worth
# inspecting, and the next run clears whatever this leaves behind.
on_exit() {
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        cleanup
    else
        echo "run.sh failed (exit $rc)" >&2
        echo "left for inspection: $WORKTREE" >&2
    fi
}

# Clear any leftover from a previous failure or a killed run.
cleanup
trap on_exit EXIT

git -C "$PYTORCH_REPO" fetch upstream

git -C "$PYTORCH_REPO" worktree add --detach "$WORKTREE" upstream/viable/strict

# worktree add leaves every submodule empty and the build needs all 37 of them.
# The objects are already in the parent repo, so this is mostly a local copy.
git -C "$WORKTREE" submodule update --init --recursive

# Which checkout to test. The runner takes its interpreter and torch from
# whatever environment it is launched in, so it needs nothing else from us.
export PYTORCH_ROOT="$WORKTREE"

(cd "$WORKTREE" && pixi run -w "$PIXI_WORKSPACE" -e "$PIXI_ENV" build)

# Captured before teardown. Width matches the hash cpython_test_runner.py
# puts in the data filename.
msg=$(git -C "$WORKTREE" rev-parse --short=11 HEAD)

cd "$APP"

# Run the tests in the same env that was just built, so `python` there is the
# one with the worktree's torch installed.
pixi run -w "$PIXI_WORKSPACE" -e "$PIXI_ENV" python "$APP/cpython_test_runner.py"

# Results only. Staging everything would sweep up in-progress edits to this
# script and push them silently.
git add data/

# Re-running in the same week reproduces an identical file and stages nothing.
# That is not a failure.
if git diff --cached --quiet; then
    echo "no new results to commit"
else
    git commit -m "Add tests for ${msg}"
    git push
fi
