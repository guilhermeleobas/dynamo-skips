#!/usr/bin/env bash

set -e

APP=~/git/dynamo-skips-app
PYTORCH_REPO=~/git/pytorch313
WORKTREE=~/git/pytorch-viable

# Reuse an existing env from the pytorch workspace rather than declaring a new
# one. The build below layers a worktree-local venv on top so it never touches
# this env's own torch install.
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

# Captured before teardown. Width matches the hash cpython_test_runner.py
# puts in the data filename.
msg=$(git -C "$WORKTREE" rev-parse --short=11 HEAD)

# Build and test in a venv layered on the pixi env, not in the env itself. The
# env has a single shared editable-torch finder (_editable_skbc_torch.pth); a
# plain `pip install -e .` here would repoint it at $WORKTREE, and cleanup()
# would then leave $PYTORCH_REPO unable to `import torch` until it is rebuilt.
# The venv's site-packages precedes the env on sys.path, so the finder this
# build writes is scoped to the worktree and is deleted along with it.
pixi run -w "$PIXI_WORKSPACE" -e "$PIXI_ENV" bash -c "
set -e
cd '$WORKTREE'
python -m venv --system-site-packages .venv
source .venv/bin/activate
export CCACHE_BASEDIR=\"\$HOME\"
pip install -e . -v --no-build-isolation
cd '$APP'
python '$APP/cpython_test_runner.py'
"

cd "$APP"

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
