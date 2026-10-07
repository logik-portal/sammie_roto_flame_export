#!/bin/bash
# Double-clickable installer for the Sammie Roto Flame Export integration.
cd "$(dirname "$0")"
python3 install.py
echo "Press Return to close."
read _
