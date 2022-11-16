import stormpy

from .spec import HyperSpecification
from .property import HyperProperty, SchedulerOptimalityHyperProperty

import re
import operator

import logging
logger = logging.getLogger(__name__)


# TODO: implement Optimality Properties and Optimality HyperProperties
class Parser:

    def __init__(self):
        self.sched_quant_dict = {}
        self.state_quant_dict = {}
        self.state_range_dict = {}
        self.state_quant_restrictions = {}

        # parsed lines of the property
        self.lines = []

        # parsed scheduler optimality property
        self.scheduler_optimality_hyperproperty = None

    def parse_properties(self, sketch_path, properties_path):
        # parsing the scheduler quantifiers
        logger.info(f"Loading properties from {properties_path} ...")
        logger.info(f"Parsing scheduler quantifiers ...")
        self.parse_scheduler_quants(properties_path)
        logger.info(f"Found the following scheduler quantifiers: {self.sched_quant_dict}")

        # parsing scheduler quantifiers
        logger.info("Parsing state quantifiers...")
        self.parse_state_quants()
        logger.info(f"Found the following state quantifiers: {self.state_quant_dict}")

        # parsing restrictions
        logger.info(f"Parsing restrictions")
        self.parse_restrictions()
        logger.info(f"Found the following restrictions: {self.state_quant_restrictions}")

        # parsing, if present, the scheduler optimality property
        logger.info(f"Parsing scheduler optimality ( if required)")
        self.parse_scheduler_optimality()
        found_sop = "" if self.scheduler_optimality_hyperproperty is not None else "not "
        logger.info(f"Scheduler optimality property {found_sop}found.")

        # parse program
        logger.info(f"Loading sketch from {sketch_path}...")
        logger.info(f"Assuming a sketch in a PRISM format ...")
        prism = self.parse_program(sketch_path)

        # dummy model for instantiating the properties
        dummy_model = stormpy.build_model(prism)
        nr_initial_states = len(dummy_model.initial_states)
        logger.info(f"The model has {nr_initial_states} initial states...")

        # actual parsing of the properties
        logger.info("Instantiating the properties for the quantified initial states")
        self.spread_properties(nr_initial_states, dummy_model.labeling)
        specification = self.parse_instantiated_properties(prism)
        logger.info(f"Found the following specification:\n {specification}")
        return specification, prism

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

        self.lines = lines

    def parse_state_quants(self):
        # parse state quantifiers
        state_re = re.compile(r'^(E|A)\s(\S+)\((\S+)\)(\s?)(.*$)')
        line = self.lines.pop(0)
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

    def parse_restrictions(self):
        restriction_re = re.compile(r'Restrict\s(\S+)\s(\S+)(\s?)(.*$)')
        line = self.lines.pop(0)
        match = restriction_re.search(line)
        if match is None:
            # no restriction specified
            self.lines = [line] + self.lines
            return

        while True:
            state_name = match.group(1)
            restriction_label = match.group(2)
            if state_name not in self.state_quant_dict:
                print("state name: " + str(state_name))
                raise Exception("Trying to restrict a variable not in scope")
            if state_name in self.state_quant_restrictions:
                raise Exception("Trying to restrict two times the same variable")

            # storing this restriction
            self.state_quant_restrictions[state_name] = restriction_label

            if match.group(4) == "":
                # no other restrictions found
                return

            # move to next restriction
            line = match.group(4)
            match = restriction_re.search(line)
            if match is None:
                raise Exception("Wrong formatted restrictions")

    def parse_scheduler_optimality(self):
        # parse the scheduler optimality hyperproperty, if required
        sop_re = re.compile(r'^(MIN|MAX)\s(SD)(.*$)')
        line = self.lines.pop(0)
        match = sop_re.search(line)
        if match is None:
            # scheduler optimality not required
            self.lines = [line] + self.lines
            return

        if len(self.sched_quant_dict) == 0:
            raise Exception("Cannot impose MIN/MAX scheduler difference with just one scheduler\n")
        minimizing = True if match.group(1) == "MIN" else False
        self.scheduler_optimality_hyperproperty = SchedulerOptimalityHyperProperty(minimizing)

    # instantiate the properties for the initial states according to their quantifiers
    def spread_properties(self, nr_initial_states, labeling):
        nr_schedulers = len(self.sched_quant_dict)
        nr_init_per_sched = int(nr_initial_states / nr_schedulers)
        for state_name, value in self.state_quant_dict.items():
            state_quant, sched_name = value
            sched_order = list(self.sched_quant_dict.keys()).index(sched_name)
            # compute the set of possible values for each state variable
            initial_states = [i for i in range(nr_init_per_sched * sched_order, nr_init_per_sched * (sched_order + 1))]

            print("initial states for " + str(state_name) +":" + str(initial_states))
            # check potential restrictions on this initial state
            restriction = self.state_quant_restrictions.get(state_name, None)
            if restriction is not None:
                initial_states = [i for i in initial_states if labeling.has_state_label(restriction, i)]

            print("initial states for " + str(state_name) + "after restrictions:" + str(initial_states))


            #instantiate the properties for this state variable
            if state_quant == 'E':
                self.lines = list(map(lambda x: self.grow_horizontally(x, state_name, initial_states), self.lines))
            elif state_quant == 'A':
                spread_lines = list(map(lambda x: self.grow_vertically(x, state_name, initial_states), self.lines))
                self.lines = [item for sublist in spread_lines for item in sublist]

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
                # we are instantiating the properties with distinct initial states
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

    #parse all the instantiated properties and return a HyperSpecification
    def parse_instantiated_properties(self, prism):
        properties = []
        i = 0
        for line in self.lines:
            indexes = []
            props_separator_re = re.compile(r'\s\|\s')
            props = re.split(props_separator_re, line)
            for prop in props:
                prop_re = re.compile(r'(P(\{(\S+)\})(.*?))(\s(<=|<|=>|>)\s)(P(\{(\S+)\})(.*?))$')
                match = prop_re.search(prop)
                if match is None:
                    raise Exception(f"input formula is wrong formatted! [{prop}]")
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
                p = HyperProperty(p, state_quant, compare_state, op)

                #add the property to the list
                properties.extend([p])
                indexes.extend([i])
                i += 1

            HyperSpecification.disjoint_indexes.append(indexes)
        return HyperSpecification(properties, None, self.scheduler_optimality_hyperproperty)

    def parse_program(self, path):
        n_sched_quants = len(self.sched_quant_dict)
        # perform the "duplication trick"
        if n_sched_quants > 1:
            with open(path, "r") as f:
                lines = f.readlines()
                f.close()

            with open(path, "a") as f:
                # add a global variable to distinguish two initial states
                # note: this does not work if the file is empty or if the PRISM file already contains the global variable sched_quant
                # note: this does not work also if the PRISM file does not contain a init ... endinit definition.
                f.write("\nglobal sched_quant : [0.." + str(n_sched_quants - 1) + "];")
                f.close()

            prism = stormpy.parse_prism_program(path, prism_compat=True)

            # remove the global variable to be clean
            with open(path, "w") as f:
                f.writelines(lines)
                f.close()
            return prism
        else:
            return stormpy.parse_prism_program(path, prism_compat=True)