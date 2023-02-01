import stormpy

import math
import operator

import logging

logger = logging.getLogger(__name__)

class Property:
    # model checking precision
    mc_precision = 1e-7
    # precision for comparing floats
    float_precision = 1e-3

    ''' Wrapper over a stormpy property. '''

    def __init__(self, prop, state, min_bound = 0):
        self.property = prop
        rf = prop.raw_formula

        # use comparison type to deduce optimizing direction
        comparison_type = rf.comparison_type
        self.minimizing = comparison_type in [stormpy.ComparisonType.LESS, stormpy.ComparisonType.LEQ]
        self.op = {
            stormpy.ComparisonType.LESS: operator.lt,
            stormpy.ComparisonType.LEQ: operator.le,
            stormpy.ComparisonType.GREATER: operator.gt,
            stormpy.ComparisonType.GEQ: operator.ge
        }[comparison_type]

        self.strict = self.op in [operator.lt, operator.gt]

        # set threshold
        self.threshold = rf.threshold_expr.evaluate_as_double()

        # construct quantitative formula (without bound) for explicit model checking
        # set optimality type
        self.formula = rf.clone()
        self.formula.remove_bound()
        if self.minimizing:
            self.formula.set_optimality_type(stormpy.OptimizationDirection.Minimize)
        else:
            self.formula.set_optimality_type(stormpy.OptimizationDirection.Maximize)
        self.formula_alt = Property.alt_formula(self.formula)
        self.formula_str = rf

        self.state = state
        self.min_bound = min_bound

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
        return f"{self.formula_str}[{self.state}] -- bound: [{self.min_bound}]"

    @property
    def reward(self):
        return self.formula.is_reward_operator

    @staticmethod
    def above_mc_precision(a, b):
        return abs(a - b) > Property.mc_precision

    @staticmethod
    def above_float_precision(a, b):
        return abs(a - b) > Property.float_precision

    def meets_op(self, a, b):
        ''' For constraints, we do not want to distinguish between small differences. '''
        if self.strict:
            return Property.above_float_precision(a, b) and self.op(a, b)
        else:
            return not Property.above_float_precision(a, b) or self.op(a, b)

    def meets_threshold(self, value):
        return self.meets_op(value + self.min_bound, self.threshold)

    def result_valid(self, value):
        return not self.reward or value != math.inf

    def satisfies_threshold(self, value):
        ''' check if DTMC model checking result satisfies the property '''
        return self.result_valid(value) and self.meets_threshold(value)


class OptimalityProperty(Property):
    '''
    Optimality property can remember current optimal value and adapt the
    corresponding threshold wrt epsilon.
    '''

    def __init__(self, prop, state, epsilon=None):
        self.property = prop
        rf = prop.raw_formula

        # use comparison type to deduce optimizing direction
        if rf.optimality_type == stormpy.OptimizationDirection.Minimize:
            self.minimizing = True
            self.op = operator.lt
            self.threshold = math.inf
        else:
            self.minimizing = False
            self.op = operator.gt
            self.threshold = -math.inf

        # construct quantitative formula (without bound) for explicit model checking
        self.formula = rf.clone()
        self.formula_alt = Property.alt_formula(self.formula)
        self.formula_str = rf

        # additional optimality stuff
        self.optimum = None
        self.epsilon = epsilon

        self.state = state


    def __str__(self):
        eps = f"[eps = {self.epsilon}]" if self.epsilon > 0 else ""
        return f"{self.formula_str}[{self.state}] {eps}"

    def meets_op(self, a, b):
        ''' For optimality objective, we want to accept improvements above floating point precision. '''
        return b is None or Property.above_float_precision(a, b) and self.op(a, b)

    def satisfies_threshold(self, value):
        return self.result_valid(value) and self.meets_op(value, self.threshold)

    def improves_optimum(self, value):
        return self.result_valid(value) and self.meets_op(value, self.optimum)

    def update_optimum(self, optimum):
        assert self.improves_optimum(optimum)
        logger.debug(f"New opt = {optimum}.")
        self.optimum = optimum
        if self.minimizing:
            self.threshold = optimum * (1 - self.epsilon)
        else:
            self.threshold = optimum * (1 + self.epsilon)

    def suboptimal_value(self):
        assert self.optimum is not None
        if self.minimizing:
            return self.optimum * (1 + self.mc_precision)
        else:
            return self.optimum * (1 - self.mc_precision)


class Specification:

    def __init__(self, constraints, optimality):
        self.constraints = constraints
        self.optimality = optimality

    def __str__(self):
        if len(self.constraints) == 0:
            constraints = "none"
        else:
            constraints = ",".join([str(c) for c in self.constraints])
        if self.optimality is None:
            optimality = "none"
        else:
            optimality = str(self.optimality)
        return f"constraints: {constraints}, optimality objective: {optimality}"

    @property
    def has_optimality(self):
        return self.optimality is not None

    def all_constraint_indices(self):
        return [i for i, _ in enumerate(self.constraints)]

    def stormpy_properties(self):
        properties = [c.property for c in self.constraints]
        if self.has_optimality:
            properties += [self.optimality.property]
        return properties

    def stormpy_formulae(self):
        mc_formulae = [c.formula for c in self.constraints]
        if self.has_optimality:
            mc_formulae += [self.optimality.formula]
        return mc_formulae
