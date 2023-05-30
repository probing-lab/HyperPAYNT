import re
from tabulate import tabulate
import argparse
import os

maze_re = re.compile(f'Loading properties from .*?eval/qest/.*?/./(.*?)/')
time_re = re.compile(f'synthesis time: ([0-9]+\.[0-9]+)(.*)$') # match.group(1) is the time required by the experiment
iters_re = re.compile(f'iterations: ([0-9]+)(.*)') # match.group(1) is the number of iterations
sat_members_re = re.compile(f'AR Sat members found: ([0-9]+)(.*)$') # match.group(1) is the number of sat members
feas_re = re.compile(f'feasible: (.*)$') #match.group(1) is the feasibility result
mdp_size_re = re.compile(f'Constructed quotient MDP having ([0-9]+)(.*) states') # match.group(1) is the average MDP size
family_size_re = re.compile(f'Design space size: ([0-9]+)(.*)$') # match.group(1) is the family size
explored_re = re.compile(f'explored: ([0-9]+ %)$') #match.group(1) is the percentage explored
distance_re = re.compile(f'Current optimal value: ([0-9]+)(.*)$') # match.group(1) is the max distance
init_re = re.compile(f'python3') # first log mesasge of any experiment

# alternatives for TO
explored_re_alt = re.compile(f'Progress ([0-9]+\.[0-9]+%)')
iters_re_alt = re.compile(f'iters = \(([0-9]+), 0\)')
to_dictionary = {explored_re: explored_re_alt, iters_re: iters_re_alt}

# hyperprob data
maze_alt_re = re.compile(f'python3 hyperprob.py -modelPath benchmark_files/mdp/(.*?)/')
vars_re = re.compile(f'Number of variables: ([0-9]+)')
fs_re = re.compile(f'Number of formula checked: ([0-9]+)')
encoding_re = re.compile(f'Encoding time: ([0-9]+\.[0-9]+)')
solving_re = re.compile(f'Time required by z3 in seconds: ([0-9]+\.[0-9]+)')
init_hyperprob_re = re.compile(f'python3 hyperprob.py')

def remap(required, found, previous_line):
    res = []
    for r,f in zip(required, found):
        appended = False
        # not present due to timeout
        if f is None:
            if r == time_re:
                res.append("Time Out")
                appended = True
            else:
                regex = to_dictionary.get(r, None)
                if regex is not None:
                    match = regex.search(previous_line)
                    if match is not None:
                        res.append(match.group(1))
                        appended = True
            if not appended:
                res.append("?")
        else:
            res.append(f)
    return res

def parse(path, tab_name, header, required):
    results = []
    with open(path) as file:
        temp = [None for h in header]
        first_exp = True
        previous_line = None
        for line in file:
            # little optimization
            if line.startswith(">"):
                previous_line = line
                continue

            # mark the beginning of a new experiment
            match = init_re.search(line)
            if match is not None:
                if first_exp:
                    first_exp = False
                else:
                    if None in temp:
                        # timeout experiment
                        temp = remap(required,temp, previous_line)
                    results.append(temp)
                    temp = [None for h in header]

            # check all the required regex
            for index, regex in enumerate(required):
                # if such regex has not been found yet
                if temp[index] is None:
                    match = regex.search(line)
                    if match is not None:
                        temp[index] = match.group(1)

            # update previous line (used for time out experiments)
            previous_line = line

        # handle last experiment
        if None in temp:
            # timeout experiment
            temp = remap(required, temp, previous_line)
        results.append(temp)

    tabResults = tabulate(results, headers=header)

    # remove potential previous data for security
    if os.path.exists(tab_name):
        os.remove(tab_name)

    text_file = open(tab_name, "w")
    text_file.write(tabResults)
    text_file.close()

def parseHyperprob(path, tab_name, header, required):
    results = []
    with open(path) as file:
        temp = [None for h in header]
        first_exp = True
        for line in file:
            # mark the beginning of a new experiment
            match = init_hyperprob_re.search(line)
            if match is not None:
                if first_exp:
                    first_exp = False
                else:
                    # timeout experiment
                    temp = ["Time Out" if t is None else t for t in temp]
                    # flush collected data
                    results.append(temp)
                    temp = [None for h in header]

            # check all the required regex
            for index, regex in enumerate(required):
                if temp[index] is None:
                    match = regex.search(line)
                    if match is not None:
                        temp[index] = match.group(1)

    # handle last experiment
    temp = ["Time Out" if t is None else t for t in temp]
    results.append(temp)

    tabResults = tabulate(results, headers=header)
    text_file = open(tab_name, "w")
    text_file.write(tabResults)
    text_file.close()

if __name__ == '__main__':
    argp = argparse.ArgumentParser()
    argp.add_argument('exp', type=str, nargs='+', help='which experiment needs to be parsed?')
    args = argp.parse_args()

    argument = args.exp[0]
    if argument == "hyperprob_comparison":
        path = "./qest/logs/PW_TA_TS_PC_HyperPaynt.txt"
        header = [
            "Case Study", "Feasible", "MDP size", "AR family size", "AR time", "AR iters", "Percentage explored"]
        parse(path, "qest/Table2-HyperPaynt.csv", header, [maze_re, feas_re, mdp_size_re, family_size_re, time_re, iters_re, explored_re])

    if argument == "hyperprob":
        path = "./qest/logs/PW_TA_TS_PC_HyperProb.txt"
        header = ["Case Study", "variables", "subformulae", "Encoding Time", "Solving Time"]
        parseHyperprob(path, "qest/Table2-Hyperprob.csv", header, [maze_alt_re, vars_re, fs_re, encoding_re, solving_re])

    if argument == "sd":
        path = "./qest/logs/SD_HyperPaynt.txt"
        header = [
            "Maze", "Feasible", "MDP size", "AR family size", "AR time", "AR iters", "Percentage explored"]
        parse(path, "qest/Table3-HyperPaynt.csv", header, [maze_re, feas_re, mdp_size_re, family_size_re, time_re, iters_re, explored_re])

    if argument == "hyperprob_sd":
        path= "./qest/logs/SD-Hyperprob.txt"
        header = ["Maze", "variables", "subformulae", "Encoding Time", "Solving Time"]
        parseHyperprob(path, "qest/Table3-Hyperprob.csv", header, [maze_alt_re, vars_re, fs_re, encoding_re, solving_re])

    if argument == "explore_all":
        path = "./qest/logs/SD_explore_all.txt"
        header = [
            "Maze", "AR time", "AR iters", "Percentage explored", "Feasible instances"]
        parse(path, "qest/Table4.csv", header, [maze_re, time_re, iters_re, explored_re, sat_members_re])

    if argument == "probni":
        path = "./qest/logs/Probni.txt"
        header = [
            "Maze", "Feasible", "MDP size", "AR family size", "AR time", "AR iters"]
        parse(path, "qest/Table5-ProbNI.csv", header,
              [maze_re, mdp_size_re, family_size_re, time_re, iters_re])

    if argument == "opacity":
        path = "./qest/logs/Opacity.txt"
        header = [
            "Maze", "MDP size", "AR family size", "AR time", "AR iters", "max distance"]
        parse(path, "qest/Table5-Opacity.csv", header,
              [maze_re, mdp_size_re, family_size_re, time_re, iters_re, distance_re])







