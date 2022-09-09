import stormpy

import math
import operator

import logging

from .spec import Specification

logger = logging.getLogger(__name__)


class Property:
    ''' Wrapper over a stormpy property. '''

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

        # set the state quantifier (either 0 or 1)
        self.state = state
        self.other_state = other_state

    def __str__(self):
        return str(self.formula_str) + " {" + str(self.state) + "} " + str(self.op) + " " + str(self.formula_str) + " {" + str(self.other_state) + "}"

    @property
    def reward(self):
        return False

    @staticmethod
    def above_mc_precision(a, b):
        return abs(a - b) > Specification.mc_precision

    @staticmethod
    def above_float_precision(a, b):
        return abs(a - b) > Specification.float_precision

    def meets_op(self, a, b):
        if self.strict:
            return Property.above_float_precision(a, b) and self.op(a, b)
        else:
            return not Property.above_float_precision(a, b) or self.op(a, b)

    def satisfies_threshold(self, value, threshold):
        return self.meets_op(value, threshold)
