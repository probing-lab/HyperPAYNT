import operator

import stormpy
from paynt.paynt.sketch.property import Property, logger

# TODO: implement optimality hyperproperties
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


class SchedulerOptimalityHyperProperty(HyperProperty):

    def __init__(self, minimizing):
        self.minimizing = minimizing
        self.op = operator.lt if minimizing else operator.gt

        # set the current optimal value
        self.optimum = None

    def meets_op(self, a, b):
        return b is None or self.op(a, b)

    # there no epsilon - better threshold scheduler differences can only be natural numbers
    def satisfies_threshold(self, value):
        self.meets_op(value, self.optimum)

    def improves_optimum(self, value):
        return self.meets_op(value, self.optimum)

    def update_optimum(self, optimum):
        assert self.improves_optimum(optimum)
        logger.debug(f"New scheduler hyper opt = {optimum}.")
        self.optimum = optimum

    def __str__(self):
        direction = "Minimizing " if self.minimizing else "Maximizing "
        return f"{direction} scheduler difference."
