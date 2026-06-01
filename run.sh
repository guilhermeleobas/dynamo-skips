#!/usr/bin/env bash

set -e

pixi run python cpython_test_runner.py

git add .

msg=$(cd ~/git/pytorch313; git rev-parse --short HEAD)

git commit -m "Add tests for ${msg}"

git push
