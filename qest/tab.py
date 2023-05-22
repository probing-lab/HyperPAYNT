import re
from tabulate import tabulate
import argparse

maze_re = re.compile(r'^eval/qest/SD/(.*)/(.*)$') # match.group(1) is the name of the experiment
time_re = re.compile(f'synthesis time: ([0-9]+\.[0-9]+)(.*)$') # match.group(1) is the time required by the experiment
iters_re = re.compile(f'iterations: ([0-9]+)(.*)$') # match.group(1) is the number of iterations
sat_members_re = re.compile(f'AR Sat members found: ([0-9]+)(.*)$') # match.group(1) is the number of sat members
feas_re = re.compile(f'feasible: (\s)$') #match.group(1) is the feasibility result
mdp_size_re = re.compile(f'Constructed quotient MDP having ([0-9]+)(.*) states$') # match.group(1) is the average MDP size
family_size_re = re.compile(f'Design space size: ([0-9]+)(.*)$') # match.group(1) is the family size
explored_re = re.compile(f'explored: ([0-9]+ %)$') #match.group(1) is the percentage explored
distance_re = re.compile(f'Current optimal value: ([0-9]+)(.*)$') # match.group(1) is the max distance
init_re = re.compile(f'cli.py - This is Paynt version 0.1.0.') # first log mesasge of any experiment

# alternatives for TO
explored_re_alt = re.compile(f'Progress ([0-9]+\.[0-9]+%)')
iters_re_alt = re.compile(f'iters = \(([0-9]+), 0\)')
to_dictionary = {explored_re: explored_re_alt, iters_re: iters_re_alt}

# hyperprob data
vars_re = re.compile(f'Number of variables: ([0-9]+)')
fs_re = re.compile(f'Number of formula checked: ([0-9]+)')
encoding_re = re.compile(f'Encoding time: ([0-9]+\.[0-9]+)')
solving_re = re.compile(f'Time required by z3 in seconds: ([0-9]+\.[0-9]+)')
init_hyperprob_re = re.compile(f'python hyperprob.py')

path = "./log_explore_all"

def remap(required, found, previous_line):
    res = []
    for r,f in zip(required, found):
        if f is None:
            if r == time_re:
                res.append("Time Out")
            else:
                regex = to_dictionary[r]
                match = regex.search(previous_line)
                res.append(match.group(1))
        else:
            res.append(f)
    return res

def parse(path, tab_name, header, required):
    with open(path) as file:
        results = []
        temp = [None for h in header]
        first_exp = True
        previous_line = None
        for line in file:
            # mark the beginning of a new experiment
            match = init_re.search(line)
            if match is not None:
                if first_exp:
                    first_exp = False
                else:
                    # timeout experiment
                    if None in temp:
                        temp = remap(required,temp, previous_line)
                    results.append(temp)
                    temp = [None for h in header]

            # check all the required regex
            for index, regex in enumerate(required):
                match = regex.search(line)
                if match is not None:
                    temp[index] = match.group(1)

            # update previous line (used for time out experiments)
            previous_line = line

        tabResults = tabulate(results, headers=header)
        text_file = open(tab_name, "w")
        text_file.write(tabResults)
        text_file.close()

def parseHyperprob(path, tab_name, header, required):
    with open(path) as file:
        results = []
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
                    results.append(temp)
                    temp = [None for h in header]

            # check all the required regex
            for index, regex in enumerate(required):
                match = regex.search(line)
                if match is not None:
                    temp[index] = match.group(1)

        tabResults = tabulate(results, headers=header)
        text_file = open(tab_name, "w")
        text_file.write(tabResults)
        text_file.close()

if __name__ == '__main__':
    argp = argparse.ArgumentParser()
    argp.add_argument('exp', type=str, nargs='+', help='which experiment needs to be parsed?')
    args = argp.parse_args()

    if args.exp == "hyperprob_comparison":
        path = "./logs/PW_TA_TS_PC_HyperPaynt.txt"
        header = [
            "Maze, Feasible, MDP size, AR family size, AR time, AR iters, Percentage explored"]
        parse(path, "Table2-HyperPaynt.csv", header, [maze_re, feas_re, mdp_size_re, family_size_re, time_re, iters_re, explored_re])

    if args.exp == "hyperprob":
        path= "./logs/PW_TA_TS_PC_HyperProb.txt"
        header = ["variables", "subformulae", "Encoding Time", "Solving Time"]
        parseHyperprob(path, "Table2-HyperProb.csv", header, [vars_re, fs_re, encoding_re, solving_re])

    if args.exp == "sd":
        path = "./logs/SD_HyperPaynt.txt"
        header = [
            "Maze, Feasible, MDP size, AR family size, AR time, AR iters, Percentage explored"]
        parse(path, "Table3-HyperPaynt.csv", header, [maze_re, feas_re, mdp_size_re, family_size_re, time_re, iters_re, explored_re])

    if args.exp == "hyperprob_sd":
        path= "./logs/SD_hyperprob.txt"
        header = ["variables", "subformulae", "Encoding Time", "Solving Time"]
        parseHyperprob(path, "Table3_HyperProb.csv", header, [vars_re, fs_re, encoding_re, solving_re])

    if args.exp == "explore_all":
        path = "./logs/SD_explore_all.txt"
        header = [
            "Maze, AR time, AR iters, Percentage explored, Feasible instances"]
        parse(path, "Table4.csv", header, [maze_re, ime_re, iters_re, explored_re, sat_members_re])

    if args.exp == "probni":
        path = "./logs/Probni.txt"
        header = [
            "Maze, Feasible, MDP size, AR family size, AR time, AR iters"]
        parse(path, "Table5-ProbNI.csv", header,
              [maze_re, feas_re, mdp_size_re, family_size_re, time_re, iters_re])

    if args.exp == "opacity":
        path = "./logs/Opacity.txt"
        header = [
            "Maze, MDP size, AR family size, AR time, AR iters, max distance"]
        parse(path, "Table5-Opacity.csv", header,
              [maze_re, mdp_size_re, family_size_re, time_re, iters_re, distance_re])







