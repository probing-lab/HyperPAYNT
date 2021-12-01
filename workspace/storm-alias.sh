#!/bin/bash

# compilation parameters

export COMPILE_JOBS=$(nproc)

# environment variables

export SYNTHESIS=`pwd`
export PREREQUISITES=$SYNTHESIS/prerequisites
export DOWNLOADS=$PREREQUISITES/downloads

export SYNTHESIS_ENV=$SYNTHESIS/env

export STORM_DIR=$SYNTHESIS/storm
export STORM_BLD=$STORM_DIR/build
export STORM_BLD_DEBUG=$STORM_DIR/build_debug

export DYNASTY_DIR=$SYNTHESIS/paynt

### prerequisites ##############################################################

prerequisites-prepare() {
    cd $PREREQUISITES
    unzip $DOWNLOADS/carl.zip
    mv carl-master14 carl
    unzip $DOWNLOADS/pycarl.zip
    mv pycarl-master pycarl
    cd $SYNTHESIS
}

python-environment() {
    virtualenv -p python3 $SYNTHESIS_ENV
    source $SYNTHESIS_ENV/bin/activate
    pip3 install pytest pytest-runner pytest-cov numpy scipy pysmt z3-solver click
    deactivate
}

prerequisites-build() {
    # carl
    cd $PREREQUISITES
    mkdir -p carl/build
    cd carl/build
    cmake -DUSE_CLN_NUMBERS=ON -DUSE_GINAC=ON -DTHREAD_SAFE=ON ..
    make lib_carl --jobs $COMPILE_JOBS
    #[TEST] make test
    cd $SYNTHESIS

    #pycarl
    cd $PREREQUISITES/pycarl
    source $SYNTHESIS_ENV/bin/activate
    python3 setup.py build_ext --jobs $COMPILE_JOBS --disable-parser develop
    #[TEST] python3 setup.py test
    deactivate
    cd $SYNTHESIS
}

storm-dependencies() {
    sudo apt update
    sudo apt -y install build-essential git automake cmake libboost-all-dev libcln-dev libgmp-dev libginac-dev libglpk-dev libhwloc-dev libz3-dev libxerces-c-dev libeigen3-dev
    sudo apt -y install texlive-latex-extra
    sudo apt -y install maven uuid-dev python3-dev libffi-dev libssl-dev python3-pip virtualenv
    sudo update-alternatives --install /usr/bin/python python /usr/bin/python3 10
}

### storm patch (obsolete) #####################################################

paynt-patch-create() {
    local storm_src=$SYNTHESIS/storm/src
    local patch_storm_src=$SYNTHESIS/patch/storm/src

    rsync -av $storm_src/CMakeLists.txt $patch_storm_src/CMakeLists.txt
    rsync -av $storm_src/storm-synthesis $patch_storm_src/
    rsync -av $storm_src/storm-cli-utilities/CMakeLists.txt $patch_storm_src/storm-cli-utilities/CMakeLists.txt
}

paynt-patch() {
    rsync -av $SYNTHESIS/patch/ $SYNTHESIS/
}

### storm and stormpy ##########################################################

storm-config() {
    mkdir -p $STORM_BLD
    cd $STORM_BLD
    cmake ..
    cd ~-
}

storm-config-debug() {
    mkdir -p $STORM_BLD_DEBUG
    cd $STORM_BLD_DEBUG
    cmake .. -DSTORM_DEVELOPER=ON -DSTORM_USE_LTO=OFF
    cd ~-
}

storm-build() {
    cd $STORM_BLD
    make storm-main storm-synthesis --jobs $COMPILE_JOBS
    # make check --jobs $COMPILE_JOBS
    cd ~-
}

storm-build-debug() {
    cd $STORM_BLD_DEBUG
    make storm-main storm-synthesis --jobs $COMPILE_JOBS
    cd ~-
}

stormpy-build() {
    cd $SYNTHESIS/stormpy
    source $SYNTHESIS_ENV/bin/activate
    # python3 setup.py build_ext --storm-dir $STORM_BLD --jobs $COMPILE_JOBS develop
    python3 setup.py build_ext --storm-dir $STORM_BLD_DEBUG --jobs $COMPILE_JOBS develop
    # python3 setup.py test
    deactivate
    cd ~-
}

paynt-install() {
    cd $DYNASTY_DIR
    source $SYNTHESIS_ENV/bin/activate
    python3 setup.py install
    # python3 setup.py test
    deactivate
    cd ~-
}

synthesis-install() {
    cd $SYNTHESIS
    bash install.sh
    cd ~-
}

### development ################################################################

# recompilation

storm-rebuild() {
    storm-config
    storm-build
}

stormpy-rebuild() {
    storm-rebuild
    stormpy-build
}

# aliases

alias sc='storm-config'
alias sb='storm-build'
alias pb='stormpy-build'
alias sr='storm-rebuild'


### executing paynt ##########################################################

export WORKSPACE=$SYNTHESIS/workspace
export DYNASTY_LOG=$WORKSPACE/log

alias enva='source $SYNTHESIS_ENV/bin/activate'
alias envd='deactivate'

function paynt() {
    local core=0
    if [ -n "$1" ]; then
        core=$1
    fi
    local exp_sh=$WORKSPACE/execute.sh
    local run_sh=$DYNASTY_LOG/run_${core}.sh

    mkdir -p $DYNASTY_LOG
    cd $DYNASTY_LOG
    cp $exp_sh $run_sh
    source $SYNTHESIS_ENV/bin/activate
    bash $run_sh $core
    deactivate
    cd ~-
}
function d() {
    paynt $1
}
function db() {
    paynt $1 & disown
}

alias dpid='pgrep -f "^python3 .*/paynt.py .*"'
alias dtime='ps -aux | grep "python3 .*/paynt.py"'
alias dshow='pgrep -af "^python3 .*/paynt.py .*"'
alias dcount='pgrep -afc "^python3 .*/paynt.py .*"'
alias dkill='dpid | xargs kill'
alias dclear='rm $DYNASTY_LOG/*'

dlog() {
    cat $DYNASTY_LOG/log_$1.txt
}
dgrep() {
    cat $DYNASTY_LOG/log_grep_$1.txt
}

dhead() {
    dlog $1 | head -n 50
}
dtail() {
    dlog $1 | tail -n 50
}


### binds ###

bind '"\ei"':"\"storm-config \C-m\""
bind '"\ek"':"\"storm-config-debug \C-m\""
bind '"\eo"':"\"storm-build \C-m\""
bind '"\el"':"\"storm-build-debug \C-m\""
bind '"\ep"':"\"stormpy-build \C-m\""

bind '"\ed"':"\"db \C-m\""
bind '"\e1"':"\"db 1 \C-m\""
bind '"\e2"':"\"db 2 \C-m\""
bind '"\e3"':"\"db 3 \C-m\""
bind '"\e4"':"\"db 4 \C-m\""
bind '"\e5"':"\"db 5 \C-m\""
bind '"\e6"':"\"db 6 \C-m\""
bind '"\e7"':"\"db 7 \C-m\""
bind '"\e8"':"\"db 8 \C-m\""

### executing storm  ###########################################################

storm() {
    cd $STORM_BLD/bin
    local cmd="./storm --explchecks --build-overlapping-guards-label $1"
    eval $cmd
    cd -
}

storm-jani() {
    storm "--jani $DYNASTY_DIR/output_0.jani --prop $DYNASTY_DIR/workspace/examples/cav/maze/orig/compute.properties"
}

storm-eval() {
    storm "$1 --prop $2 --constants $3"
}

export DPM=$SYNTHESIS/workspace/examples/cav/dpm-main
export DICE=$SYNTHESIS/workspace/examples/cav/dice
export MAZE=$SYNTHESIS/workspace/examples/cav/maze
export WALK=$SYNTHESIS/workspace/examples/random-walk
export MAZE2=$SYNTHESIS/workspace/examples/maze/orig

dice() {
    storm-eval "--prism $DICE/sketch.templ" $DICE/compute.properties "CMAX=0,THRESHOLD=0,$1"
}
dpm() {
    storm-eval "--prism $DPM/sketch.templ" $DPM/compute.properties "CMAX=10,THRESHOLD=0,T2=5,$1"
}

walk() {
    storm-eval "-pc --prism $WALK/sketch.templ" $WALK/compute.properties "CMAX=10,THRESHOLD=0"
}

walk2() {
    storm-eval "-pc --prism $WALK/sketch2.templ" $WALK/compute.properties "CMAX=10,THRESHOLD=0"
}

maze2() {
    storm-eval "-pc --prism $MAZE2/sketch.prism" $MAZE2/sketch.properties "CMAX=10,THRESHOLD=0"
}

# useful flags
# ./storm-pomdp --prism $SYNTHESIS/workspace/examples/pomdp/maze/concise/sketch.templ --constants CMAX=2,THRESHOLD=1.0 --prop $SYNTHESIS/workspace/examples/pomdp/maze/concise/sketch.properties -ec --io:exportexplicit test.drn

