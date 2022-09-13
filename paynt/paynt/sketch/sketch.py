import stormpy

from .spec import Specification
from .holes import Hole, Holes, DesignSpace
from ..synthesizers.models import MarkovChain
from ..synthesizers.quotient import *
from ..profiler import Profiler
from .property import Property

import os
import re
import operator
import uuid

import logging
logger = logging.getLogger(__name__)

class Sketch:

    def __init__(self, sketch_path, properties_path):

        Profiler.initialize()
        Profiler.start("sketch")

        self.prism = None
        self.hole_expressions = None

        self.design_space = None
        self.specification = None
        self.quotient = None

        self.sched_quant_dict = {}
        self.state_quant_dict = {}
        self.state_range_dict = {}

        # parsing the scheduler quantifiers, and returning the rest of the specification
        logger.info(f"Loading properties from {properties_path} ...")
        logger.info(f"Parsing scheduler quantifiers ...")
        lines = self.parse_scheduler_quants(properties_path)
        logger.info(f"Found the following scheduler quantifiers: {self.sched_quant_dict}")

        # sketch loading
        logger.info(f"Loading sketch from {sketch_path}...")
        logger.info(f"Assuming a sketch in a PRISM format ...")
        self.prism = Sketch.parse_program(sketch_path, len(self.sched_quant_dict))

        #formulae loading
        dummy_model = stormpy.build_model(self.prism)
        nr_initial_states = len(dummy_model.initial_states)
        logger.info(f"The model has {nr_initial_states} initial states...")
        logger.info("parsing state quantifiers")
        lines = self.parse_state_quants(lines)
        logger.info(f"Found the following state quantifiers: {self.state_quant_dict}")
        lines = self.spread_properties(lines, nr_initial_states)
        self.specification = self.parse_specification(lines, self.prism)
        logger.info(f"Found the following specification:\n {self.specification}")

        # initializing the Model Checking options
        MarkovChain.initialize(self.specification.stormpy_formulae())

        # setting the correct design space
        logger.info("Processing actions and Initializing the quotient...")
        self.quotient = HyperPropertyQuotientContainer(self)

        logger.info(f"Sketch has {self.design_space.num_holes} holes")
        logger.info(f"Design space size: {self.design_space.size}")
        logger.info(f"Design space: {self.design_space}")
        logger.info(f"Sketch parsing complete.")
        Profiler.stop()

    def parse_scheduler_quants(self, path):

        # read lines
        lines = []
        with open(path) as file:
            for line in file:
                line = line.replace("\n", "")
                if not line or line == "" or line.startswith("//"):
                    continue
                lines.append(line)

        # parse scheduler quantifiers
        sched_re = re.compile(r'^(ES|AS)\s(\S+)(\s?)(.*$)')

        # the first line are scheduler quantifiers
        line = lines.pop(0)
        match = sched_re.search(line)
        if match is None:
            raise Exception("the input formula is wrong formatted!")

        while True:
            sched_quant = match.group(1)
            sched_name = match.group(2)

            if sched_name in list(self.sched_quant_dict.keys()):
                raise Exception("two scheduler variables cannot have the same name")

            # for now we support only straighforward synthesis specifications
            # hence currently the dictionary values are never retrieved
            if sched_quant == "AS":
                # TODO: implement encoding of AS quantifications
                raise NotImplementedError

            # add this scheduler quantifier to the dictionary
            self.sched_quant_dict[sched_name] = sched_quant

            # end of line
            if match.group(4) == "":
                break

            # move to next scheduler
            line = match.group(4)
            match = sched_re.search(line)
            if match is None:
                raise Exception("the input formula is wrong formatted!")

        return lines

    def parse_state_quants(self, lines):
        # parse state quantifiers
        state_re = re.compile(r'^(E|A)\s(\S+)\((\S+)\)(\s?)(.*$)')
        line = lines.pop(0)
        match = state_re.search(line)
        if match is None:
            raise Exception("the input formula is wrong formatted!")

        existential_quantifier = False
        while True:
            state_quant = match.group(1)
            state_name = match.group(2)
            sched_name = match.group(3)

            # every scheduler variable must be quantified
            if sched_name not in list(self.sched_quant_dict.keys()):
                raise Exception("a scheduler variable occurs free in the formula")

            # the implementation of HyperPaynt supports only specifications in conjunctive normal form
            if existential_quantifier and state_quant == "A":
                raise Exception("this nesting is not allowed: please use conjunctions of disjuctions")

            if state_name in list(self.state_quant_dict.keys()):
                raise Exception("two state variables cannot have the same name")

            if state_quant == "E":
                existential_quantifier = True

            # add the state quantifier to the dictionary
            self.state_quant_dict[state_name] = (state_quant, sched_name)

            # end of state quantifiers
            if match.group(5) == "":
                break

            # move to next state quantifier
            line = match.group(5)
            match = state_re.search(line)
            if match is None:
                raise Exception("the input formula is wrong formatted!")

        return lines

    @classmethod
    def parse_program(cls, path, scheduler_quantifiers):
        if scheduler_quantifiers > 1:
            with open(path, "r") as f:
                lines = f.readlines()
                f.close()

            with open(path, "a") as f:
                # add a global variable to distinguish two initial states
                # note: this does not work if the file is empty or if the PRISM file already contains the global variable sched_quant
                f.write("\nglobal sched_quant : [0.." + str(scheduler_quantifiers -1) + "];")
                f.close()

            prism = stormpy.parse_prism_program(path, prism_compat=True)

            # remove the global variable to be clean
            with open(path, "w") as f:
                f.writelines(lines)
                f.close()
            return prism
        else:
            return stormpy.parse_prism_program(path, prism_compat=True)

    # instantiate the properties for the initial states according to their quantifiers
    def spread_properties(self, lines, nr_initial_states):
        nr_schedulers = len(self.sched_quant_dict)
        nr_init_per_sched = int(nr_initial_states / nr_schedulers)
        for state_name, value in self.state_quant_dict.items():
            state_quant, sched_name = value
            sched_order = list(self.sched_quant_dict.keys()).index(sched_name)
            # compute the set of possible values for each state variable
            initial_states = [i for i in range(nr_init_per_sched * sched_order, nr_init_per_sched * (sched_order + 1))]

            #instantiate the properties for this state variable
            if state_quant == 'E':
                lines = list(map(lambda x: self.grow_horizontally(x, state_name, initial_states), lines))
            elif state_quant == 'A':
                spread_lines = list(map(lambda x: self.grow_vertically(x, state_name, initial_states), lines))
                lines = [item for sublist in spread_lines for item in sublist]
        return lines

    # "horizontally" means to add some more properties in disjunction with the ones found in the current line
    def grow_horizontally(self, line, state_name, initial_states):
        # we must have at least some initial states
        assert len(initial_states) > 0
        spread_properties = ""
        props_separator_re = re.compile(r'\s\|\s')
        props = re.split(props_separator_re, line)
        for prop in props:
            if state_name in prop:
                #instantial the property for all initial states
                instantiated_property = ""
                for state in [i for i in initial_states if "{" + str(i) + "}" not in prop]:
                    if instantiated_property == "":
                        instantiated_property += prop.replace(state_name, str(state))
                    else:
                        instantiated_property += " | " + prop.replace(state_name, str(state))
                prop = instantiated_property

            #append the instantiated property
            if spread_properties == "":
                spread_properties += prop
            else:
                spread_properties += " | " + prop
        return spread_properties

    # "vertically" means to add some more properties in conjunction with the ones found in the current line
    def grow_vertically(self, line, state_name, initial_states):
        if state_name in line:
            return [line.replace(state_name, str(i)) for i in initial_states if "{" + str(i) + "}" not in line]
        else:
            return [line]

    #parse all the instantiated properties and return a Specification
    def parse_specification(self, lines, prism):
        properties = []
        i = 0
        for line in lines:
            indexes = []
            props_separator_re = re.compile(r'\s\|\s')
            props = re.split(props_separator_re, line)
            for prop in props:
                prop_re = re.compile(r'(P(\{(\S+)\})(.*?))(\s(<=|<|=>|>)\s)(P(\{(\S+)\})(.*?))$')
                match = prop_re.search(prop)
                if match is None:
                    raise Exception("input formula is wrong formatted!")
                if not match.group(4) == match.group(10):
                    raise NotImplementedError("Comparison of different reachability targets are not supported yet. "
                                              "Please also check that whitespaces match in the two targets: \""
                                              + match.group(4) + "\" and \"" + match.group(10) + "\"")
                # collect information
                state_quant = int(match.group(3))
                compare_state = int(match.group(9))
                ops = {"<=": operator.le, "<": operator.lt, "=>": operator.ge, ">": operator.gt}
                op = ops[match.group(6)]

                # parse the property
                p = match.group(1).replace(match.group(2), "=?")
                ps = stormpy.parse_properties_for_prism_program(p, prism)
                p = ps[0]
                p = Property(p, state_quant, compare_state, op)

                #add the property to the list
                properties.extend([p])
                indexes.extend([i])
                i += 1

            Specification.disjoint_indexes.append(indexes)
        return  Specification(properties)
