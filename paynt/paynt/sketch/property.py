import stormpy

import math
import operator

import logging

logger = logging.getLogger(__name__)


class Property:
    # model checking precision
    mc_precision = 1e-10
    # precision for comparing floats
    float_precision = 1e-7

    ''' Wrapper over a stormpy property. '''

    def __init__(self, prop):
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
        return str(self.formula_str)

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
        # return not Property.above_float_precision(a,b) or self.op(a,b)
        return self.op(a, b)

    def meets_threshold(self, value):
        return self.meets_op(value, self.threshold)

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

    def __init__(self, prop, epsilon=None):
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

    def __str__(self):
        eps = f"[eps = {self.epsilon}]" if self.epsilon > 0 else ""
        return f"{self.formula_str} {eps}"

    def meets_op(self, a, b):
        ''' For optimality objective, we want to accept improvements above model checking precision. '''
        return b is None or (Property.above_mc_precision(a, b) and self.op(a, b))

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


class HyperProperty(Property):
    ''' Wrapper over an hyperproperty as a simple comparison of a reachability probability between two states. '''

    def __init__(self, prop, state, other_state, op):
        self.property = prop
        rf = prop.raw_formula

        # use operator to deduce optimizing direction
        self.op = op
        self.minimizing = op in [operator.le, operator.lt]
        self.strict = op in [operator.lt, operator.gt]

        # set optimality type
        self.formula = rf.clone()
        optimality_type = stormpy.OptimizationDirection.Minimize if self.minimizing else stormpy.OptimizationDirection.Maximize
        self.formula.set_optimality_type(optimality_type)

        # Construct alternative quantitative formula to use in AR.
        self.formula_alt = self.formula.clone()
        optimality_type_alt = stormpy.OptimizationDirection.Maximize if self.minimizing else stormpy.OptimizationDirection.Minimize
        self.formula_alt.set_optimality_type(optimality_type_alt)

        # for the str function
        self.formula_str = rf

        # set the state quantifier
        self.state = state
        self.other_state = other_state

    def __str__(self):
        return str(self.formula_str) + " {" + str(self.state) + "} " + str(self.op) + " " + str(self.formula_str) + " {" + str(self.other_state) + "}"

    def meets_op(self, a, b):
        ''' For constraints, we do not want to distinguish between small differences. '''
        if self.strict:
            return Property.above_float_precision(a, b) and self.op(a, b)
        else:
            return not Property.above_float_precision(a, b) or self.op(a, b)

    def satisfies_threshold(self, value, threshold):
        return self.result_valid(value) and self.meets_op(value, threshold)


class OptimalitySchedulerHyperProperty(HyperProperty):

    def __init__(self, minimizing):
        self.minimizing = minimizing
        self.op = operator.lt if minimizing else operator.gt

        # set the current optimal value
        self.optimum = None

    def meets_op(self, a, b):
        return b is None or self.op(a, b)

    def satisfies_threshold(self, value):
        self.meets_op(value, self.optimum)

    def improves_optimum(self, value):
        return self.meets_op(value, self.optimum)

    def update_optimum(self, optimum):
        assert self.improves_optimum(optimum)
        logger.debug(f"New scheduler hyper opt = {optimum}.")
        self.optimum = optimum
