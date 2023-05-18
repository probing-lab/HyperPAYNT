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

if [ -n "$2" ]; then
  projects_dir="$2"
fi

param=''
if [ -n "$3" ]; then
  param="$3"
fi

# ------------------------------------------------------------------------------
# functions
function paynt() {
    # argument settings
    local project="--project $1"
    local method="--method $2"

    local paynt_call="python3 ${paynt_exe} ${project} ${method} ${param}"
    echo \$ ${paynt_call}
    eval timeout ${timeout} ${paynt_call} >> ${log_file}
}

# empty the current content of the log file
rm -rf $log_dir
mkdir $log_dir
touch $log_file

cwd=$(pwd)
cd $projects_dir
dirs=$(find . -type d -exec sh -c '(ls -p "{}"|grep />/dev/null)||echo "{}"' \;)
cd $cwd
for d in $dirs; do
  paynt "${projects_dir}/${d}" $method
done

