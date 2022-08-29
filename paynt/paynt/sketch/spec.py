

# a specification is just a set of properties
class Specification:
    # model checking precision
    mc_precision = 1e-5
    # precision for comparing floats
    float_precision = 1e-5

    disjoint_indexes = []

    def __init__(self, constraints):
        self.constraints = constraints

    def __str__(self):
        constraints = ";\n".join([str(c) for c in self.constraints])
        return f"{constraints}"

    @property
    def has_optimality(self):
        return False

    def all_constraint_indices(self):
        return [i for i,_ in enumerate(self.constraints)]

    def stormpy_properties(self):
        return [c.property for c in self.constraints]

    def stormpy_formulae(self):
        return [c.formula for c in self.constraints]

    @classmethod
    def or_filter(cls, results, sub):
        filtered = []
        for sublist in Specification.disjoint_indexes:
            slice = list(map(lambda x: results[x], sublist))
            if any(t is sub for t in slice):
                filtered.extend([sub] * len(slice))
            else:
                filtered.extend(slice)
        return filtered

    @classmethod
    def or_group_indexes(cls, indexes):
        grouped = []
        for sublist in Specification.disjoint_indexes:
            filtered = list(filter(lambda x: x in indexes, sublist))
            grouped.append(filtered)
        return grouped

    @classmethod
    def or_group_dict(cls, dict):
        keys = dict.keys()
        grouped = []
        for sublist in Specification.disjoint_indexes:
            filtered = list(filter(lambda i: i in keys, sublist))
            res = list(map(lambda i: (i, dict[i]), filtered))
            grouped.append(res)
        return grouped


class PropertyResult:
    def __init__(self, prop, result, value):
        self.property = prop
        self.result = result
        self.value = value
        self.sat = prop.satisfies_threshold(value)

    def __str__(self):
        return str(self.value) + "(s_" + str(self.property.state_quant) + ") vs " + str(self.property.threshold) \
               + "(s_" + str(self.property.compare_state) + "): " + str(self.sat)


class ConstraintsResult:
    '''
    A list of property results.
    Note: some results might be None (not evaluated).
    '''
    def __init__(self, results):
        self.results = results
        self.all_sat = True

        sat_list = list(map(lambda x: None if x is None else x.sat, results))
        filtered_result = Specification.or_filter(sat_list, True)

        for result in filtered_result:
            if result is not None and result == False:
                self.all_sat = False
                break

    def __str__(self):
        return ";\n".join([str(result) for result in self.results])

    def isSat(self, index):
        sat_list = list(map(lambda x: None if x is None else x.sat, self.results))
        filtered_result = Specification.or_filter(sat_list, True)
        return filtered_result[index]

class MdpPropertyResult:
    def __init__(self,
                 prop, primary, secondary, feasibility,
                 primary_selection, primary_feasibility, primary_choice_values, primary_expected_visits,
                 primary_scores
                 ):
        self.property = prop
        self.primary = primary
        self.secondary = secondary
        self.feasibility = feasibility

        self.primary_selection = primary_selection
        self.primary_feasibility = primary_feasibility
        self.primary_choice_values = primary_choice_values
        self.primary_expected_visits = primary_expected_visits
        self.primary_scores = primary_scores

    def __str__(self):
        prim = str(self.primary)
        seco = str(self.secondary)
        if self.property.minimizing:
            return "{} - {}; ".format(prim, seco)
        else:
            return "{} - {}; ".format(seco, prim)


# a wrapper for a list of MdpPropertyResults
class MdpConstraintsResult:
    def __init__(self, results):
        feas_list = list(map(lambda x: False if x is None else x.feasibility, results))
        fr_True = Specification.or_filter(feas_list, True)
        fr_None = Specification.or_filter(feas_list, None)

        self.results = results
        # undecided constraint which are not in a or relation with a true constraint
        self.undecided_constraints = [index for index, result in enumerate(results) if
                                      result is not None and result.feasibility is None
                                      and fr_True[index] is None]

        self.unfeasible_constraints = [index for index, result in enumerate(results) if
                                      result is not None and result.feasibility is False]
        self.feasibility = True
        self.primary_feasibility = True
        self.sched_selection = None
        for result, filter1, filter2 in zip(results, fr_True, fr_None):
            if result is None:
                continue
            if result.feasibility == False and filter1 == False and filter2 == False:
                self.feasibility = False
                self.primary_feasibility = False
                break
            if result.feasibility == None and filter1 == None:
                self.feasibility = None
                if self.primary_feasibility:
                    if not result.primary_feasibility:
                        self.primary_feasibility = False
                    else:
                        if self.sched_selection is None:
                            self.sched_selection = result.primary_selection
                        else:
                            for options1 in self.sched_selection:
                                for options2 in result.primary_selection:
                                    if len(options1) != len(options2):
                                        self.primary_feasibility = False
                                    set1 = set(options1)
                                    set2 = set(options2)
                                    if set1 != set2:
                                        self.primary_feasibility = False

    def improving(self, family):
        ''' Interpret MDP constraints result. '''

        # constraints were satisfied
        if self.feasibility == True:
            improving_assignment = family.pick_any()
            return improving_assignment, False

        # constraints not satisfied
        if self.feasibility == False:
            return None,False

        # constraints undecided, but primary selection is feasible for all constraints
        if self.primary_feasibility:
            for res in self.results:
                if res is not None and res.primary_feasibility:
                    assignment = family.copy()
                    assignment.assume_options(res.primary_selection)
                    return assignment.pick_any(), False

        # constraints undecided
        return None, True

    def __str__(self):
        return ",".join([str(result) for result in self.results])

    def undecided_result(self):
        return self.results[self.undecided_constraints[0]]
