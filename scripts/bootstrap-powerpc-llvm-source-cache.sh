#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script_name=${0##*/}
bash_name=${script_name%.sh}.bash
# Terminal handoff: share Bash startup isolation with the public launcher.
. "$script_dir/whp-build/shell-functions.sh"
whp_exec_bash "$script_dir/$bash_name" "$@"
