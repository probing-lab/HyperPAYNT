import stormpy

import math
import operator

import logging

logger = logging.getLogger(__name__)


class Property:
    # model checking precision
    mc_precision = 1e-4
    # precision for comparing floats
    float_precision = 1e-10

    ''' Wrapper over a stormpy probability property. '''

    def __init__(self, prop, minimizing, maximizing, state_var):
        self.property = prop
        rf = prop.raw_formula
        self.formula = rf
        self.state_var = state_var

        # set the optimizing direction
        self.minimizing = minimizing
        self.maximizing = maximizing

        # construct quantitative formula (without bound) for explicit model checking
        # set optimality type
        if self.minimizing:
            self.formula.set_optimality_type(stormpy.OptimizationDirection.Minimize)
            self.formula_alt = Property.alt_formula(self.formula)
        elif self.maximizing:
            self.formula.set_optimality_type(stormpy.OptimizationDirection.Maximize)
            self.formula_alt = Property.alt_formula(self.formula)
        else:
            self.formula_alt = self.formula.clone()

    @staticmethod
    def alt_formula(formula):
        ''' Construct alternative quantitative formula to use in AR. '''
        formula_alt = formula.clone()
        optimality_type = formula.optimality_type
        # negate optimality type
        if optimality_type == stormpy.OptimizationDirection.Minimize:
            optimality_type = stormpy.OptimizationDirection.Maximize
        else:
            optimality_type = stormpy.OptimizationDirection.Minimize
        formula_alt.set_optimality_type(optimality_type)
        return formula_alt

    def __str__(self):
        return str(self.formula)

    @staticmethod
    def above_float_precision(a, b):
        return abs(a - b) > Property.float_precision

    def meets_op(self, a, b):
        ''' For constraints, we do not want to distinguish between small differences. '''
        return not Property.above_float_precision(a, b) or self.op(a, b)
        # return self.op(a,b)

    # TODO: this has to be moved elsewhere
    def meets_threshold(self, value):
        return self.meets_op(value, self.threshold)

    def result_valid(self, value):
        return value != math.inf

    def satisfies_threshold(self, value):
        ''' check if DTMC model checking result satisfies the property '''
        return self.result_valid(value)


class Specification:

    def __init__(self, lc, rc):
        self.left_f = lc
        self.right_f = rc

    def __str__(self):
        ''' to be overridden '''
        pass


# a specification where a reachability probability is compared against a threshold value
class ThresholdSpecification(Specification):
    def __init__(self, lc, threshold, op, state_dict):
        Specification.__init__(lc, threshold)
        self.isThreshold = True
        self.op = op
        self.state_dict = state_dict

    def __str__(self):
        return self.left_f.__str__() + " " + self.op.__str__() + " " + str(self.right_f)


# a specification where a reachability probability is compared against another reachability probability (the double property)
class DPSpecification(Specification):
    def __init__(self, lc, threshold, op, state_dict):
        Specification.__init__(lc, threshold)
        self.isThreshold = False
        self.op = op
        self.state_dict = state_dict

    def __str__(self):
        return self.left_f.__str__() + " " + self.op.__str__() + " " + self.right_f.__str__()


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
