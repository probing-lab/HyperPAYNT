import operator

import stormpy
from ..sketch.property import Property, logger, Specification


class HyperProperty(Property):
    ''' Wrapper over an hyperproperty as a simple comparison of a reachability probability between two states. '''

    def __init__(self, prop, state, other_state, op, min_bound = 0):
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

        # minimal distance at which we consider the hyperproperty satisfied
        self.min_bound = min_bound
        assert min_bound > Property.float_precision

        self.threshold = None

    def __str__(self):
        return str(self.formula_str) + " {" + str(self.state) + "} " + str(self.op) + " " + str(
            self.formula_str) + " {" + str(self.other_state) + "}"

    def satisfies_threshold(self, value, threshold):
        return self.result_valid(value) and self.meets_op(value + self.min_bound, threshold)


# TODO: implement optimality hyperproperties
class OptimalityHyperProperty(HyperProperty):
    def __init__(self):
        raise NotImplementedError("Implement me, Mario!")


class SchedulerOptimalityHyperProperty(HyperProperty):

    def __init__(self, minimizing):
        self.minimizing = minimizing
        self.op = operator.lt if minimizing else operator.gt

        # the current optimal value is not set
        self.hyperoptimum = None

        # all the other fields are of not interest
        self.property = None
        self.strict = None
        self.formula = None
        self.formula_alt = None
        self.formula_str = None
        self.state = None
        self.other_state = None

    def meets_op(self, a, b):
        return b is None or self.op(a, b)

    # there is no epsilon - better threshold scheduler differences can only be natural numbers
    def satisfies_threshold(self, value):
        self.meets_op(value, self.hyperoptimum)

    def improves_hyperoptimum(self, value):
        return self.meets_op(value, self.hyperoptimum)

    def update_hyperoptimum(self, hyperoptimum):
        assert self.improves_hyperoptimum(hyperoptimum)
        logger.debug(f"New scheduler hyper opt = {hyperoptimum}.")
        self.hyperoptimum = hyperoptimum

    def __str__(self):
        direction = "Minimizing " if self.minimizing else "Maximizing "
        return f"{direction} scheduler difference."


class HyperSpecification(Specification):

    # indexes for folding the properting into those that in OR conjunction
    # recall that we consider only properties in Conjunctive Normal Form
    disjoint_indexes = []

    # constraints can contain both properties and hyperproperties here
    def __init__(self, constraints, optimality, sched_hyperoptimality):
        super().__init__(constraints, optimality)

        # so stands for scheduler optimality (hyperproperty)
        self.sched_hyperoptimality = sched_hyperoptimality

    def __str__(self):
        constraints = "none" if len(self.constraints) == 0 else ";\n".join([str(c) for c in self.constraints])
        optimality = "none" if self.optimality is None else f"{self.optimality}"
        sched_optimality = "none" if self.sched_hyperoptimality is None else f"{self.sched_hyperoptimality}"

        return f"constraints: {constraints}.\n Optimality objective: {optimality}.\n " \
               f"Scheduler Optimality hyperobjective: {sched_optimality}\n "


    @property
    def has_hyperoptimality(self):
        # hyperoptimality properties have not been implemented so far
        return False

    @property
    def has_scheduler_hyperoptimality(self):
        return self.sched_hyperoptimality is not None

    def update_optimum(self, value):
        if self.optimality is not None:
            self.optimality.update_optimum(value)
        elif self.sched_hyperoptimality is not None:
            self.sched_hyperoptimality.update_hyperoptimum(value)
        else:
            assert False

    def all_constraint_indices(self):
        return [i for i,_ in enumerate(self.constraints)]

    def stormpy_properties(self):
        properties = [c.property for c in self.constraints]
        if self.has_optimality:
            properties += [self.optimality.property]
        return [c.property for c in self.constraints]

    def stormpy_formulae(self):
        mc_formulae = [c.formula for c in self.constraints]
        if self.has_optimality:
            mc_formulae += [self.optimality.formula]
        return mc_formulae

    @classmethod
    def or_filter(cls, results, sub):
        filtered = []
        for sublist in HyperSpecification.disjoint_indexes:
            slice = list(map(lambda x: results[x], sublist))
            if any(t is sub for t in slice):
                filtered.extend([sub] * len(slice))
            else:
                filtered.extend(slice)
        return filtered

    @classmethod
    def or_group_indexes(cls, indexes):
        grouped = []
        for sublist in HyperSpecification.disjoint_indexes:
            filtered_sublist = list(filter(lambda x: x in indexes, sublist))
            grouped.append(filtered_sublist)
        return grouped

    @classmethod
    def or_group_dict(cls, dict):
        keys = dict.keys()
        grouped = []
        for sublist in HyperSpecification.disjoint_indexes:
            filtered_sublist = list(filter(lambda i: i in keys, sublist))
            res_slice = list(map(lambda i: (i, dict[i]), filtered_sublist))
            grouped.append(res_slice)
        return grouped
