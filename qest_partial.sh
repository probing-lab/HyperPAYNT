#!/bin/bash

# at qest we present only the AR method
method="ar"
# default timeout
timeout=36
timeout1=60

# workspace settings
hyperpaynt_dir=$(pwd)
paynt_exe="${hyperpaynt_dir}/paynt/paynt.py"
log_dir="${hyperpaynt_dir}/qest/logs"
hyperprob_dir="${hyperpaynt_dir}/../HyperProb"

# ------------------------------------------------------------------------------
# functions
function paynt() {
    # argument settings
    local project="--project $1"
    local method="--method $2"
    local log_file="$3"
    local paynt_call="python3 ${paynt_exe} ${project} ${method} ${param}"
    echo \$ ${paynt_call}
    echo \$ ${paynt_call} >> ${log_file}
    eval timeout ${timeout} ${paynt_call} >> ${log_file}
}
#---------------------------------------------

# empty the current content of the log dir
rm -rf $log_dir
mkdir $log_dir

# uncomment this when not in Docker.
source env/bin/activate

log_file_hyperprob_sd="${log_dir}/SD-Hyperprob.txt"
touch $log_file_hyperprob_sd
# HyperProb commands
cd $hyperprob_dir
hyperprob_call1="python3 hyperprob.py -modelPath benchmark_files/mdp/simple/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call1}
echo \$ ${hyperprob_call1} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call1} >> ${log_file_hyperprob_sd}

hyperprob_call2="python3 hyperprob.py -modelPath benchmark_files/mdp/larger-1/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call2}
echo \$ ${hyperprob_call2} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call2} >> ${log_file_hyperprob_sd}

hyperprob_call5="python3 hyperprob.py -modelPath benchmark_files/mdp/splash-1/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call5}
echo \$ ${hyperprob_call5} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call5} >> ${log_file_hyperprob_sd}

cd $hyperpaynt_dir
call=" python3 qest/tab.py hyperprob_sd"
eval ${call}
