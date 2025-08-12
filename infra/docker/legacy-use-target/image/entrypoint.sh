#!/bin/bash
set -e

# Set X server environment variables to reduce warnings
export DISPLAY=:${DISPLAY_NUM}
export XKB_DEFAULT_RULES=base
export XKB_DEFAULT_MODEL=pc105
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_VARIANT=""
export XKB_DEFAULT_OPTIONS=""
./xvfb_startup.sh
./x11vnc_startup.sh
./novnc_startup.sh

./start_vpn.sh

./start_remote_screen.sh &

./start_computer_api.sh
