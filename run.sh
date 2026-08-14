#!/usr/bin/env bash

set -e

git -C ~/git/pytorch313-cp fetch upstream

git -C ~/git/pytorch313-cp checkout --detach upstream/viable/strict

pixi run python cpython_test_runner.py

git add .

msg=$(cd ~/git/pytorch313-cp; git rev-parse --short HEAD)

git commit -m "Add tests for ${msg}"

git push
