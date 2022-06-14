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

class PC_Property:
    # model checking precision
    mc_precision = 1e-4
    # precision for comparing floats
    float_precision = 1e-10

    ''' Wrapper over a stormpy property. '''

    def __init__(self, prop):

        #the state variables of this property
        self.L_state_var = "s1"
        self.R_state_var = "s2"

        # each property specifies an equality between two probabilities
        self.property = prop
        self.op = operator.eq

        self.formula = prop.raw_formula

    def __str__(self):
        return str(self.formula) + " = " + str(self.formula)

    def meets_op(self, a, b):
        return self.op(a, b)

    def satisfies_threshold(self, value_left, value_right):
        return self.meets_op(value_left, value_right)

# a specification is just
#    - a set of properties (i.e. all the equalities)
#    - the dictionary to retrive the state quantifications


class Specification:

    def __init__(self, constraints):
        self.constraints = constraints
        # see the formula for the probabilistic conformance
        self.sq_dict = {"s1" : "AS", "s2" : "ES"}

    def __str__(self):
        constraints = ",".join([str(c) for c in self.constraints])
        return f"constraints: {constraints}"

    def all_constraint_indices(self):
        return [i for i, _ in enumerate(self.constraints)]

    def stormpy_properties(self):
        properties = [c.L_property for c in self.constraints] + [c.R_property for c in self.constraints]
        return properties

    def stormpy_formulae(self):
        mc_formulae = [c.L_formula for c in self.constraints] + [c.R_formula for c in self.constraints]
        return mc_formulae

    @classmethod
    def string_formulae(cls):
        fs = ["P=? [F \"die1\"", "P=? [F \"die2\"", "P=? [F \"die3\"",
              "P=? [F \"die4\"", "P=? [F \"die5\"", "P=? [F \"die6\""]
        return fs

# TODO: refactor this as well (I have no idea whether we need it at the moment)

class SpecificationResult:
    def __init__(self, constraints_result, optimality_result):
        self.constraints_result = constraints_result
        self.optimality_result = optimality_result

    def __str__(self):
        return str(self.constraints_result) + " : " + str(self.optimality_result)

    def improving(self, family):
        ''' Interpret MDP specification result. '''

        cr = self.constraints_result
        opt = self.optimality_result

        if cr.feasibility == True:
            # either no constraints or constraints were satisfied
            if opt is not None:
                return opt.improving_assignment, opt.improving_value, opt.can_improve
            else:
                improving_assignment = family.pick_any()
                return improving_assignment, None, False

        if cr.feasibility == False:
            return None, None, False

        # constraints undecided: try to push optimality assignment
        if opt is not None:
            can_improve = opt.improving_value is None and opt.can_improve
            return opt.improving_assignment, opt.improving_value, can_improve
        else:
            return None, None, True

    def undecided_result(self):
        if self.optimality_result is not None and self.optimality_result.can_improve:
            return self.optimality_result
        return self.constraints_result.results[self.constraints_result.undecided_constraints[0]]


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

    def __str__(self):
        return ",".join([str(result) for result in self.results])
