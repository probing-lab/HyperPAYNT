#!/bin/bash

method="ar"
if [ -n "$1" ]; then
  method=$1
fi

# default parameters
timeout=3600

# workspace settings
SYNTHESIS=`pwd`
paynt_exe="./paynt/paynt.py"
projects_dir="./eval"
log_dir="./logs"
log_file="${log_dir}/log.txt"

# ------------------------------------------------------------------------------
# functions
function paynt() {
    # argument settings
    local project="--project $1"
    local method="--method $2"

    local paynt_call="python3 ${paynt_exe} ${project} ${method}"
    echo \$ ${paynt_call}
    eval timeout ${timeout} ${paynt_call} >> ${log_file}
}

# empty the current content of the log file
touch $log_file

for d in $projects_dir/*/ ; do
  paynt $d $method
done
