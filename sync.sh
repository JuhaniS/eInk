#!/bin/bash
# Sync project files to Raspberry Pi (excludes venv, cache, output, git)
rsync -av \
  --exclude venv \
  --exclude cache \
  --exclude output \
  --exclude .git \
  --exclude __pycache__ \
  "$(dirname "$0")/" pi@eink.local:~/eInk/
