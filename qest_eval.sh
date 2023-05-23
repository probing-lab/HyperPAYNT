#!/bin/bash

# at qest we present only the AR method
method="ar"
# default timeout
timeout=3600

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
    local paynt_call=" sudo python3 ${paynt_exe} ${project} ${method} ${param}"
    echo \$ ${paynt_call}
    echo \$ ${paynt_call} >> ${log_file}
    eval timeout ${timeout} ${paynt_call} >> ${log_file}
}

#---------------------------------------------

# empty the current content of the log dir
sudo rm -rf $log_dir
mkdir $log_dir

# ------------------------ TAB 2
#prepare the log file
log_file_hyperprob_comp="${log_dir}/PW_TA_TS_PC_HyperPaynt.txt"
touch $log_file_hyperprob_comp
projects_dir="${hyperpaynt_dir}/eval/qest/HyperProb_bench"
cd $projects_dir
dirs=$(find . -type d -exec sh -c '(ls -p "{}"|grep />/dev/null)||echo "{}"' \;)
cd $hyperpaynt_dir
for d in $dirs; do
  paynt "${projects_dir}/${d}" $method ${log_file_hyperprob_comp}
done

#parse the generated logs and generate Table 2
call=" sudo python3 qest/tab.py hyperprob_comparison"
eval ${call}

log_file_hyperprob="${log_dir}/PW_TA_TS_PC_HyperProb.txt"
touch $log_file_hyperprob
# HyperProb commands
cd $hyperprob_dir
hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/PW/password_leakage8.nm -hyperString \"AS sh . A s1 . A s2 . ~((start0(s1) & start1(s2)) & ~((P(F counter0(s1)) = P(F counter0(s2))) & ((P(F counter1(s1)) = P(F counter1(s2))) & ((P(F counter2(s1)) = P(F counter2(s2))) & ((P(F counter3(s1)) = P(F counter3(s2))) & ((P(F counter4(s1)) = P(F counter4(s2))) & ((P(F counter5(s1)) = P(F counter5(s2))) & ((P(F counter6(s1)) = P(F counter6(s2))) & ((P(F counter7(s1)) = P(F counter8(s2))) & (P(F counter8(s1)) = P(F counter8(s2))))))))))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/PW/password_leakage8.nm -hyperString \"AS sh . A s1 . A s2 . ((start0(s1) & start1(s2)) -> (P(F counter0(s1)) = P(F counter0(s2))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/TA/timing_attack8.nm -hyperString \"AS sh . A s1 . A s2 . ~((start0(s1) & start1(s2)) & ~((P(F counter0(s1)) = P(F counter0(s2))) & ((P(F counter1(s1)) = P(F counter1(s2))) & ((P(F counter2(s1)) = P(F counter2(s2))) & ((P(F counter3(s1)) = P(F counter3(s2))) & ((P(F counter4(s1)) = P(F counter4(s2))) & ((P(F counter5(s1)) = P(F counter5(s2))) & ((P(F counter6(s1)) = P(F counter6(s2)))  & ((P(F counter7(s1)) = P(F counter7(s2))) & (P(F counter8(s1)) = P(F counter8(s2))))))))))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/TA/timing_attack8.nm -hyperString \"AS sh . A s1 . A s2 . ((start0(s1) & start1(s2)) -> (P(F counter0(s1)) = P(F counter0(s2))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/TS/thread_scheduler10_20.nm -hyperString \"AS sh . A s1 . A s2 . ~((h1(s1) & h2(s2)) & ~((P(F l1(s1)) = P(F l1(s2))) & (P(F l2(s1)) = P(F l2(s2)))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/PC/synthesis0_1_2_3_4.nm -hyperString \"ES sh . A s1 . E s2 . ~((start1(s1) & start2(s2)) & ~((P(F die1(s1)) = P(F die1(s2))) & ((P(F die2(s1)) = P(F die2(s2))) & ((P(F die3(s1)) = P(F die3(s2))) & ((P(F die4(s1)) = P(F die4(s2))) & ((P(F die5(s1)) = P(F die5(s2))) & (P(F die6(s1)) = P(F die6(s2))) ) ) ) ) ) )\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

cd $hyperpaynt_dir
call=" sudo python3 qest/tab.py hyperprob"
eval ${call}

# ------------------------ TAB 3
#prepare the log file
log_file_sd="${log_dir}/SD_HyperPaynt.txt"
touch $log_file_sd
projects_dir="./eval/qest/SD"
cd $projects_dir
dirs=$(find . -type d -exec sh -c '(ls -p "{}"|grep />/dev/null)||echo "{}"' \;)
cd $hyperpaynt_dir
for d in $dirs; do
  paynt "${projects_dir}/${d}" $method ${log_file_sd}
done

#parse the generated logs and generate Table 3
call=" sudo python3 qest/tab.py sd"
eval ${call}

log_file_hyperprob_sd="${log_dir}/SD_HyperProb.txt"
touch $log_file_hyperprob_sd
# HyperProb commands
cd $hyperprob_dir
hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/simple/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/larger-1/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/larger-2/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/larger-3/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/splash-1/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/splash-2/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

hyperprob_call="python hyperprob.py -modelPath benchmark_files/mdp/SD/train/maze.nm -hyperString \"ES sh . A s1 . A s2 . ~((start1(s2) & start0(s1)) & ~(P(F target(s2)) < P(F target(s1))))\""
echo \$ ${hyperprob_call}
echo \$ ${hyperprob_call} >> ${log_file_hyperprob_sd}
eval timeout ${timeout} ${hyperprob_call} >> ${log_file_hyperprob}

cd $hyperpaynt_dir
call=" sudo python3 qest/tab.py hyperprob_sd"
eval ${call}

# -----------------------------

# ------------------------------ TAB 4
#prepare the log file
log_file_explore_all="${log_dir}/SD_explore_all.txt"
touch $log_file_explore_all
cd $hyperpaynt_dir

# explore_all commands
paynt_call=" sudo python3 ${paynt_exe} --project eval/qest/SD/./splash-1 --method ${method} --explore_all"
echo \$ ${paynt_call}
echo \$ ${paynt_call} >> ${log_file_explore_all}
eval ${paynt_call} >> ${log_file_explore_all}

paynt_call=" sudo python3 ${paynt_exe} --project eval/qest/SD/./larger-1 --method ${method} --explore_all"
echo \$ ${paynt_call}
echo \$ ${paynt_call} >> ${log_file_explore_all}
eval ${paynt_call} >> ${log_file_explore_all}

paynt_call=" sudo python3 ${paynt_exe} --project eval/qest/SD/./larger-3 --method ${method} --explore_all"
echo \$ ${paynt_call}
echo \$ ${paynt_call} >> ${log_file_explore_all}
eval ${paynt_call} >> ${log_file_explore_all}

#parse the generated logs and generate Table 4
call=" sudo python3 qest/tab.py explore_all"
eval ${call}
# ---------------------------------------------------

# ---------------------------- tab 5
log_file_probni="${log_dir}/Probni.txt"
touch $log_file_probni
projects_dir="./eval/qest/ProbNI"
cd $projects_dir
dirs=$(find . -type d -exec sh -c '(ls -p "{}"|grep />/dev/null)||echo "{}"' \;)
cd $hyperpaynt_dir
for d in $dirs; do
  paynt "${projects_dir}/${d}" $method ${log_file_probni}
done

#parse the generated logs and generate Table 5 - Probabilistic NonInterference
call=" sudo python3 qest/tab.py probni"
eval ${call}

log_file_op="${log_dir}/Opacity.txt"
touch $log_file_op
projects_dir="./eval/qest/Opacity"
cd $projects_dir
dirs=$(find . -type d -exec sh -c '(ls -p "{}"|grep />/dev/null)||echo "{}"' \;)
cd $hyperpaynt_dir
for d in $dirs; do
  paynt "${projects_dir}/${d}" $method ${log_file_op}
done

#parse the generated logs and generate Table 5 - Opacity
call=" sudo python3 qest/tab.py opacity"
eval ${call}
# -------------------------------------
