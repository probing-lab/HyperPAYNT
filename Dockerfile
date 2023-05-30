# the docker image can be built by executing:
# docker build -t <image-name> .
# to enable multi-thread compilation, use --build-arg threads=<value>

FROM ubuntu
MAINTAINER Francesco Pontiggia <francesco.pontiggia@tuwien.ac.at>
ARG threads=1

# execute bash when running the container
ENTRYPOINT ["/bin/bash"]

# to prevent texlive from asking our geographical area
#ENV DEBIAN_FRONTEND noninteractive

# main directory
RUN apt-get -y update
RUN apt -y install build-essential git automake cmake libboost-all-dev libcln-dev libgmp-dev libginac-dev libglpk-dev libhwloc-dev libz3-dev libxerces-c-dev libeigen3-dev
#RUN apt -y install texlive-latex-extra
RUN apt -y install maven uuid-dev python3-dev libffi-dev libssl-dev python3-pip python3-venv unzip nano git

# download everything
# using --depth 1 to make the download faster and the image smaller
RUN git clone --depth 1 --branch main https://github.com/francescopont/HyperProject HyperPaynt
RUN git clone --depth 1 --branch master https://github.com/francescopont/HyperProb.git HyperProb

WORKDIR /HyperPaynt/prerequisites
RUN unzip downloads/carl.zip
RUN rm -rf carl
RUN mv carl-master14 carl
RUN unzip downloads/pycarl.zip
RUN rm -rf pycarl
RUN mv pycarl-2.0.5 pycarl

# python environment
RUN pip3 install scipy pysmt z3-solver click termcolor tabulate lark pytest-runner

#carl
WORKDIR /HyperPaynt/prerequisites/carl/build
RUN cmake -DUSE_CLN_NUMBERS=ON -DUSE_GINAC=ON -DTHREAD_SAFE=ON ..
RUN make lib_carl --jobs

#pycarl
WORKDIR /HyperPaynt/prerequisites/pycarl
RUN python3 setup.py build_ext --disable-parser develop

# storm
WORKDIR /HyperPaynt/storm/build
RUN cmake ..
RUN make storm-main storm-synthesis

# stormpy
WORKDIR /HyperPaynt/stormpy
RUN python3 setup.py build_ext develop

# paynt
WORKDIR /HyperPaynt/paynt
RUN python3 setup.py install

#initial directory
WORKDIR /HyperPaynt

