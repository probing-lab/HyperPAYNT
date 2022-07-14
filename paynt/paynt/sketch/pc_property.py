import stormpy

import math
import operator

import logging

logger = logging.getLogger(__name__)

# Probabilistic conformance formula
# overall formula: ES sh . A s1 . E s2 .
#     (P(F die1(s1)) = P(F die1(s2)))
#   & (P(F die2(s1)) = P(F die2(s2)))
#   & (P(F die3(s1)) = P(F die3(s2)))
#   & (P(F die4(s1)) = P(F die4(s2)))
#   & (P(F die5(s1)) = P(F die5(s2)))
#   & (P(F die6(s1)) = P(F die6(s2)))
# these equivalences are converted into (e.g.)
# (P(F die1(s1)) <= P(F die1(s2))) & (P(F die1(s2)) = P(F die1(s1)))


class PC_Property:
    # model checking precision
    mc_precision = 1e-5
    # precision for comparing floats
    float_precision = 1e-5

    ''' Wrapper over a stormpy property. '''

    def __init__(self, prop, state_quant, minimizing):
        self.property = prop
        rf = prop.raw_formula

        # each pc_property specifies an equality between two probabilities,
        # but we resort to LEQ\GEQ relations
        self.minimizing = minimizing
        self.op = operator.le if minimizing else operator.ge

        # the threshold is set at every model check query
        self.threshold = None

        # set optimality type
        self.formula = rf.clone()
        optimality_type = stormpy.OptimizationDirection.Minimize if minimizing else stormpy.OptimizationDirection.Maximize
        self.formula.set_optimality_type(optimality_type)

        # Construct alternative quantitative formula to use in AR.
        self.formula_alt = self.formula.clone()
        optimality_type_alt = stormpy.OptimizationDirection.Maximize if minimizing else stormpy.OptimizationDirection.Minimize
        self.formula_alt.set_optimality_type(optimality_type_alt)

        self.formula_str = rf

        #set the state quantifier (either 0 or 1)
        self.state_quant = state_quant

    def double(self):
        # TODO: this works only for the PC experiment, which has only two states
        state_quant = 1 if self.state_quant == 0 else 0
        minimizing = not self.minimizing
        return PC_Property(self.property, state_quant, minimizing)


    @property
    def reward(self):
        return False

    def __str__(self):
        other_state_quant = 0 if self.state_quant == 1 else 1
        return str(self.formula_str) + " " + str(self.state_quant) + " " + str(self.op) + " " + str(other_state_quant)

    @staticmethod
    def above_mc_precision(a, b):
        return abs(a-b) > PC_Property.mc_precision

    @staticmethod
    def above_float_precision(a, b):
        return abs(a-b) > PC_Property.float_precision

    def meets_op(self, a, b):
        return not PC_Property.above_float_precision(a,b) or self.op(a,b)

    def satisfies_threshold(self, value):
        assert self.threshold is not None
        return self.meets_op(value, self.threshold)

    def set_threshold(self, threshold):
        self.threshold = threshold


# a specification is just a set of properties (i.e. all the equalities)
class Specification:

    def __init__(self, constraints):
        self.constraints = constraints

    def __str__(self):
        constraints = ",".join([str(c) for c in self.constraints])
        return f"constraints: {constraints}"

    @property
    def has_optimality(self):
        return False

    def all_constraint_indices(self):
        return [i for i in range(24)]

    def stormpy_properties(self):
        return [c.property for c in self.constraints]

    def stormpy_formulae(self):
        return [c.formula for c in self.constraints]

    @classmethod
    def string_formulae(cls):
        return ["P=? [F \"die1\"]", "P=? [F \"die2\"]", "P=? [F \"die3\"]",
                "P=? [F \"die4\"]", "P=? [F \"die5\"]", "P=? [F \"die6\"]"]


class PropertyResult:
    def __init__(self, prop, result, value):
        self.property = prop
        self.result = result
        self.value = value
        self.sat = prop.satisfies_threshold(value)

    def __str__(self):
        return str(self.value)


class ConstraintsResult:
    '''
    A list of property results.
    Note: some results might be None (not evaluated).
    '''
    def __init__(self, results):
        self.results = results
        self.all_sat = True
        for result in results:
            if result is not None and result.sat == False:
                self.all_sat = False
                break

    def __str__(self):
        return ",".join([str(result) for result in self.results])


class MdpPropertyResult:
    def __init__(self,
                 prop, primary, secondary, feasibility,
                 primary_selection, primary_choice_values, primary_expected_visits,
                 primary_scores
                 ):
        self.property = prop
        self.primary = primary
        self.secondary = secondary
        self.feasibility = feasibility

        self.primary_selection = primary_selection
        self.primary_choice_values = primary_choice_values
        self.primary_expected_visits = primary_expected_visits
        self.primary_scores = primary_scores

    def __str__(self):
        prim = str(self.primary)
        seco = str(self.secondary)
        if self.property.minimizing:
            return "{} - {}".format(prim, seco)
        else:
            return "{} - {}".format(seco, prim)


class MdpConstraintsResult:
    def __init__(self, results):
        self.results = results
        self.undecided_constraints = [index for index, result in enumerate(results) if
                                      result is not None and result.feasibility is None]

        self.feasibility = True
        for result in results:
            if result is None:
                continue
            if result.feasibility == False:
                self.feasibility = False
                break
            if result.feasibility == None:
                self.feasibility = None

    def improving(self, family):
        ''' Interpret MDP constraints result. '''

        # constraints were satisfied
        if self.feasibility == True:
            improving_assignment = family.pick_any()
            return improving_assignment, False

        # constraints not satisfied
        if self.feasibility == False:
            return None,False

        # constraints undecided
        return None, True

    def __str__(self):
        return ",".join([str(result) for result in self.results])

    def undecided_result(self):
        return self.results[self.undecided_constraints[0]]
