#!/bin/bash

#install STORM and STORMPY, all the prerequisites
source install.sh


method="ar"
# default timeout
timeout=3600

# workspace settings
SYNTHESIS=`pwd`
paynt_exe="./paynt/paynt.py"
projects_dir="./eval"
log_dir="."
log_file="${log_dir}/qest.txt"
projects_dir="eval/qest"
hyperprob_dir="/HyperProb"


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

# explore_all commands
paynt_call="python3 ${paynt_exe} eval/qest/SD/splash-1 ${method} --explore_all"
echo \$ ${paynt_call}
eval ${paynt_call} >> ${log_file}

paynt_call="python3 ${paynt_exe} eval/qest/SD/larger-1 ${method} --explore_all"
echo \$ ${paynt_call}
eval ${paynt_call} >> ${log_file}

paynt_call="python3 ${paynt_exe} eval/qest/SD/larger-3 ${method} --explore_all"
echo \$ ${paynt_call}
eval ${paynt_call} >> ${log_file}

# HyperProb commands
hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/PV/password_leakage8.nm -hyperString \"AS sh . A s1 . A s2 . ~((start0(s1) & start1(s2)) & ~((P(F counter0(s1)) = P(F counter0(s2))) & ((P(F counter1(s1)) = P(F counter1(s2))) & ((P(F counter2(s1)) = P(F counter2(s2))) & ((P(F counter3(s1)) = P(F counter3(s2))) & ((P(F counter4(s1)) = P(F counter4(s2))) & ((P(F counter5(s1)) = P(F counter5(s2))) & ((P(F counter6(s1)) = P(F counter6(s2))) & ((P(F counter7(s1)) = P(F counter8(s2))) & (P(F counter8(s1)) = P(F counter8(s2))))))))))))\""
echo \$ ${hyperprob_call}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/PV/password_leakage8.nm -hyperString \"AS sh . A s1 . A s2 . ((start0(s1) & start1(s2)) -> (P(F counter0(s1)) = P(F counter0(s2))))\""
echo \$ ${hyperprob_call}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/TA/timing_attack8.nm -hyperString \"AS sh . A s1 . A s2 . ~((start0(s1) & start1(s2)) & ~((P(F counter0(s1)) = P(F counter0(s2))) & ((P(F counter1(s1)) = P(F counter1(s2))) & ((P(F counter2(s1)) = P(F counter2(s2))) & ((P(F counter3(s1)) = P(F counter3(s2))) & ((P(F counter4(s1)) = P(F counter4(s2))) & ((P(F counter5(s1)) = P(F counter5(s2))) & ((P(F counter6(s1)) = P(F counter6(s2)))  & ((P(F counter7(s1)) = P(F counter7(s2))) & (P(F counter8(s1)) = P(F counter8(s2))))))))))))\""
echo \$ ${hyperprob_call}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/TA/timing_attack8.nm -hyperString \"AS sh . A s1 . A s2 . ((start0(s1) & start1(s2)) -> (P(F counter0(s1)) = P(F counter0(s2))))\""
echo \$ ${hyperprob_call}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/TS/thread_scheduler10_20.nm -hyperString \"AS sh . A s1 . A s2 . ~((h1(s1) & h2(s2)) & ~((P(F l1(s1)) = P(F l1(s2))) & (P(F l2(s1)) = P(F l2(s2)))))\""
echo \$ ${hyperprob_call}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/PC_sat/synthesis0_1_2_3_4.nm -hyperString \"ES sh . A s1 . E s2 . ~((start1(s1) & start2(s2)) & ~((P(F die1(s1)) = P(F die1(s2))) & ((P(F die2(s1)) = P(F die2(s2))) & ((P(F die3(s1)) = P(F die3(s2))) & ((P(F die4(s1)) = P(F die4(s2))) & ((P(F die5(s1)) = P(F die5(s2))) & (P(F die6(s1)) = P(F die6(s2))) ) ) ) ) ) )\""
echo \$ ${hyperprob_call}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file}