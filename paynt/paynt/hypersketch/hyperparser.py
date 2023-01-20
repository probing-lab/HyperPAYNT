import stormpy

from .hyperproperty import HyperProperty, SchedulerOptimalityHyperProperty, HyperSpecification
from ..sketch.holes import DesignSpace
from ..sketch.property import Property, OptimalityProperty

from collections import defaultdict

import re
import operator

import logging



logger = logging.getLogger(__name__)


class HyperParsingException(Exception):
    pass

# TODO: implement parsing of OptimalityHyperProperty
class HyperParser:

    def __init__(self):
        self.sched_quant_dict = {}
        self.state_quant_dict = {}
        self.state_range_dict = {}
        self.state_quant_restrictions = {}

        # to optimize the AR splitting
        self.sched_quant_to_initial_states = {}

        # parsed lines of the property
        self.lines = []

        # parsed optimality properties
        self.optimality_property = None
        self.scheduler_optimality_hyperproperty = None

        # parsed structural equality constraints
        self.structural_equalities = []

        DesignSpace.matching_hole_indexes = defaultdict(list)

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
                raise Exception(f"Trying to restrict a variable not in scope: {state_name}")
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
        sop_re = re.compile(r'^(MIN|MAX)\s(SD)\s*$')
        line = self.lines.pop(0)
        match = sop_re.search(line)
        if match is None:
            # scheduler optimality not required
            self.lines = [line] + self.lines
            return

        if len(self.sched_quant_dict) == 1:
            raise Exception("Cannot impose MIN/MAX scheduler difference with just one scheduler quantification\n")
        minimizing = True if match.group(1) == "MIN" else False
        self.scheduler_optimality_hyperproperty = SchedulerOptimalityHyperProperty(minimizing)

    def parse_structural_equalities(self):
        # parse the structural equalities contraints, if required
        seq_re = re.compile(r'^X(\[.*\])\((.*)\)')
        while True:
            line = self.lines.pop(0)
            match = seq_re.search(line)

            if match is None:
                # no structural required anymore
                self.lines = [line] + self.lines
                return

            valuations_dict = self.parse_state_name(match.group(1))

            scheduler_names = re.split(r'\W+', match.group(2))

            # some sanity checks
            for sched_name in scheduler_names:
                if sched_name not in list(self.sched_quant_dict.keys()):
                    raise Exception(f"Free Occurrence of a scheduler variable: {sched_name}")
            if self.structural_equalities:
                for constr in self.structural_equalities:
                    (valuations, _, snames) = constr
                    if self.compatible(valuations, valuations_dict, snames, scheduler_names):
                        raise Exception(f"Two compatible structural equalities have been specified: {valuations}, {snames}) - ({valuations_dict}, {scheduler_names})")

            self.structural_equalities.append((valuations_dict, match.group(1), scheduler_names))

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

    # "horizontally" means to add some more properties in disjunction with the ones found in the current line
    def grow_horizontally(self, line, state_name, initial_states):
        # we must have at least some initial states
        assert len(initial_states) > 0
        spread_properties = ""
        props_separator_re = re.compile(r'\s\|\|\s')
        props = re.split(props_separator_re, line)
        for prop in props:
            if state_name in prop:
                # instantial the property for all initial states
                instantiated_property = ""
                # we are instantiating the properties with distinct initial states
                for state in [i for i in initial_states if "{" + str(i) + "}" not in prop]:
                    if instantiated_property == "":
                        instantiated_property += prop.replace(state_name, str(state))
                    else:
                        instantiated_property += " || " + prop.replace(state_name, str(state))
                prop = instantiated_property

            # append the instantiated property
            if spread_properties == "":
                spread_properties += prop
            else:
                spread_properties += " || " + prop
        return spread_properties

    # "vertically" means to add some more properties in conjunction with the ones found in the current line
    def grow_vertically(self, line, state_name, initial_states):
        if state_name in line:
            return [line.replace(state_name, str(i)) for i in initial_states if "{" + str(i) + "}" not in line]
        else:
            return [line]

    # instantiate the properties for the initial states according to their quantifiers
    def spread_properties(self, nr_initial_states, model):
        n_sched_quants = len(self.sched_quant_dict)
        assert model.has_state_valuations()

        for state_var, value in self.state_quant_dict.items():
            state_quant, associated_sched = value
            initial_states = []
            sched_index = list(self.sched_quant_dict).index(associated_sched)
            sched_quant_ref = f"sched_quant={sched_index}"
            for state in model.initial_states:
                state_name = model.state_valuations.get_string(state)
                if sched_quant_ref in state_name or n_sched_quants == 1:
                    initial_states.append(state)

            logger.info(f"initial states for {state_var}: {initial_states}")
            # check potential restrictions on this initial state
            restriction = self.state_quant_restrictions.get(state_var, None)
            if restriction:
                initial_states = [i for i in initial_states if model.labeling.has_state_label(restriction, i)]

            logger.info(f"initial states for {state_var} after restrictions: {initial_states}")

            # update the set of initial states associated with this scheduler quantifier
            self.sched_quant_to_initial_states[associated_sched] = self.sched_quant_to_initial_states.get(associated_sched, set()).union(set(initial_states))

            #instantiate the properties for this state variable
            if state_quant == 'E':
                self.lines = list(map(lambda x: self.grow_horizontally(x, state_var, initial_states), self.lines))
            elif state_quant == 'A':
                spread_lines = list(map(lambda x: self.grow_vertically(x, state_var, initial_states), self.lines))
                self.lines = [item for sublist in spread_lines for item in sublist]

    # TODO: add support for the multi target comparison
    def parse_hyperproperty(self, prop, prism):
        prop_re = re.compile(r'(.*?(\{(\S+)\})(.*?))(\s(<=|<|=>|>)\s)(.*?(\{(\S+)\})(.*?))$')
        match = prop_re.search(prop)
        if match is None:
            raise HyperParsingException(f"input formula is wrong formatted! [{prop}]")
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
        reward_structure_re = re.compile(r'(\{.*?\})(.*?)')
        reward_structure_match = reward_structure_re.search(match.group(4))
        if reward_structure_match is None:
            # this is not a reward hyperproperty
            p = match.group(1).replace(match.group(2), "=?")

        else:
            # this is a Reward Hyperproperty, and has a reward structure
            p = match.group(1).replace(match.group(2), "")
            p = p.replace(match.group(4), reward_structure_match.group(1) + "=?" + reward_structure_match.group(2))

        ps = stormpy.parse_properties_for_prism_program(p, prism)
        p = ps[0]
        return HyperProperty(p, state_quant, compare_state, op)

    def parse_property(self, string, prism):

        # strip relative error
        relative_error_re = re.compile(r'^(.*)\{(.*?)\}(=\?.*?$)')
        relative_error_str = None
        match = relative_error_re.search(string)
        if match is not None:
            relative_error_str = match.group(2)
            string = match.group(1) + match.group(3)

        optimality_epsilon = float(relative_error_str) if relative_error_str is not None else 0

        # parse state id
        state_id_re = re.compile(r'^(.*?)(\{(.*?)\})(.*?$)')
        match = state_id_re.search(string)
        if match is None:
            raise HyperParsingException(f"Input formula wrong formatted! [{string}]")

        # collect information
        state_id = int(match.group(3))
        string = match.group(1) + match.group(4)

        props = stormpy.parse_properties_for_prism_program(string, prism)
        prop = props[0]
        rf = prop.raw_formula
        assert rf.has_bound != rf.has_optimality_type, "optimizing formula contains a bound or a comparison formula does not"
        if rf.has_bound:
            # comparison formula
            return Property(prop, state_id)
        else:
            # optimality formula
            return OptimalityProperty(prop, optimality_epsilon, state_id)

    # parse all the instantiated properties and return a HyperSpecification
    def parse_instantiated_properties(self, prism):
        properties = []
        i = 0
        for line in self.lines:
            indexes = []
            props_separator_re = re.compile(r'\s\|\|\s')
            props = re.split(props_separator_re, line)
            for prop in props:
                logger.info(f"Assuming an hyperproperty with index {i}...")
                try:
                    p = self.parse_hyperproperty(prop, prism)
                except HyperParsingException:
                    logger.info(f"HyperProperty Parsing failed: assuming a property for string {prop} at index {i}... ")
                    p = self.parse_property(prop, prism)

                #add the property to the list
                if isinstance(p, OptimalityProperty):
                    assert self.optimality_property is None and self.scheduler_optimality_hyperproperty is None, "two optimality formulae specified"
                    self.optimality_property = p
                else:
                    properties.extend([p])
                    indexes.extend([i])
                    i += 1

            HyperSpecification.disjoint_indexes.append(indexes)
        return HyperSpecification(properties, self.optimality_property, self.scheduler_optimality_hyperproperty)

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

        # parsing, if present, the structural equality constraints
        logger.info(f"Parsing structural constraints (if any)")
        self.parse_structural_equalities()
        str_structural_equalities = [(c_name, c_schedulers) for (_, c_name, c_schedulers) in self.structural_equalities]
        logger.info(f"Found the following structural equality constraints: {str_structural_equalities}")

        # parse program
        logger.info(f"Loading sketch from {sketch_path}...")
        logger.info(f"Assuming a sketch in a PRISM format ...")
        prism = self.parse_program(sketch_path)

        # dummy model for instantiating the properties
        builder_options = stormpy.BuilderOptions()
        builder_options.set_build_state_valuations(True)
        dummy_model = stormpy.build_sparse_model_with_options(prism, builder_options)
        nr_initial_states = len(dummy_model.initial_states)
        logger.info(f"The model has {nr_initial_states} initial states...")

        # actual parsing of the properties
        logger.info("Instantiating the properties for the quantified initial states")
        self.spread_properties(nr_initial_states, dummy_model)
        specification = self.parse_instantiated_properties(prism)
        logger.info(f"Found the following specification:\n {specification}")
        return specification, prism

    def compute_initial_states(self,variable_valuations):
        sched_index = variable_valuations["sched_quant"]
        sched_name = list(self.sched_quant_dict.keys())[int(sched_index)]
        return self.sched_quant_to_initial_states[sched_name]

    def compute_associated_schedulers(self, variable_valuations):
        sched_index = variable_valuations["sched_quant"]
        sched_name = list(self.sched_quant_dict.keys())[int(sched_index)]
        return sched_name

    def update_corresponding_holes(self, hole_index, state_name):
        n_sched_quants = len(self.sched_quant_dict)

        if n_sched_quants > 1:
            for sched_index in range(n_sched_quants):
                # deleting the sched_quant variable from state valuations
                sched_quant_ref = f"sched_quant={sched_index}"
                if sched_quant_ref in state_name:
                    state_name = state_name.replace(sched_quant_ref, "")

        # set matching holes
        DesignSpace.matching_hole_indexes[state_name].append(hole_index)

    def parse_state_name(self, state_name, parse_state_quant= False):
        valuations_dict = {}
        l = state_name.replace('[','').replace(']','').split('&')
        for valuation in l:
            if '=' not in valuation: # boolean variable
                if '!' in valuation:
                    valuation = re.sub(r'\W', '', valuation)
                    valuations_dict[valuation] = "false"
                else:
                    valuation = re.sub(r'\W', '', valuation)
                    valuations_dict[valuation] = "true"
                continue

            valuation = valuation.split('=')
            varName = re.sub(r'\W', '', valuation[0])
            value = re.sub(r'\W', '', valuation[1])
            valuations_dict[varName] = value

        # handle the case of a single scheduler quantification
        if not "sched_quant" in valuations_dict and parse_state_quant:
            valuations_dict["sched_quant"] = 0

        return valuations_dict

    def compatible(self, valuations1, valuations2, snames1, snames2):
        for varName in list(valuations1.keys()):
            if varName in valuations2 and valuations1[varName] != valuations2[varName]:
                return False

        for varName in list(valuations2.keys()):
            if varName in valuations1 and valuations1[varName] != valuations2[varName]:
                return False

        return set.intersection(set(snames1), set(snames2))

    def check_constraint_inclusion(self,c_valuations, c_schedulers, valuations, associated_scheduler):
        is_constrained = all(item in valuations.items() for item in c_valuations.items())
        return is_constrained and associated_scheduler in c_schedulers

