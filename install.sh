#!/bin/bash

set -ex

INSTALL_DEPENDENCIES=true

if [ "$INSTALL_DEPENDENCIES" = true ]; then
    if [[ ! $(sudo echo 0) ]]; then echo "sudo authentication failed"; exit; fi
fi

THREADS=$(nproc)
# THREADS=1 # uncomment this to disable multi-core compilation

SYNTHESIS=`pwd`
PREREQUISITES=$SYNTHESIS/prerequisites
SYNTHESIS_ENV=$SYNTHESIS/env
cd $SYNTHESIS

# dependencies
if [ "$INSTALL_DEPENDENCIES" = true ]; then
    sudo apt update
    sudo apt -y install build-essential git automake cmake libboost-all-dev libcln-dev libgmp-dev libginac-dev libglpk-dev libhwloc-dev libz3-dev libxerces-c-dev libeigen3-dev
    sudo apt -y install texlive-latex-extra
    sudo apt -y install maven uuid-dev python3-dev libffi-dev libssl-dev python3-pip python3-venv
    # sudo update-alternatives --install /usr/bin/python python /usr/bin/python3 10
fi

# set up python environment
python3 -m venv $SYNTHESIS_ENV
source $SYNTHESIS_ENV/bin/activate
pip3 install pytest pytest-runner pytest-cov numpy scipy pysmt z3-solver click
deactivate
cd $SYNTHESIS

# carl
cd $PREREQUISITES
mkdir -p carl/build
cd carl/build
cmake -DUSE_CLN_NUMBERS=ON -DUSE_GINAC=ON -DTHREAD_SAFE=ON ..
make lib_carl --jobs $THREADS
cd $SYNTHESIS

#pycarl
cd $PREREQUISITES/pycarl
source $SYNTHESIS_ENV/bin/activate
python3 setup.py build_ext --jobs $THREADS --disable-parser develop
deactivate
cd $SYNTHESIS

# storm
mkdir -p $SYNTHESIS/storm/build
cd $SYNTHESIS/storm/build
cmake ..
make storm-main storm-synthesis --jobs $THREADS
make check --jobs $THREADS
cd $SYNTHESIS

# stormpy
cd $SYNTHESIS/stormpy
source $SYNTHESIS_ENV/bin/activate
python3 setup.py build_ext --jobs $THREADS develop
python3 setup.py test
deactivate
cd $SYNTHESIS

# paynt
cd $SYNTHESIS/paynt
source $SYNTHESIS_ENV/bin/activate
python3 setup.py install
#[TEST] python3 setup.py test
deactivate
cd $SYNTHESIS
