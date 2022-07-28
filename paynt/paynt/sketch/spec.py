



# a specification is just a set of properties
class Specification:
    # model checking precision
    mc_precision = 1e-5
    # precision for comparing floats
    float_precision = 1e-5

    def __init__(self, constraints, disjunct):
        self.constraints = constraints
        self.disjuct = disjunct

    def __str__(self):
        constraints = ",".join([str(c) for c in self.constraints])
        return f"constraints: {constraints}"

    @property
    def has_optimality(self):
        return False

    def all_constraint_indices(self):
        return [i for i,_ in enumerate(self.constraints)]

    def stormpy_properties(self):
        return [c.property for c in self.constraints]

    def stormpy_formulae(self):
        return [c.formula for c in self.constraints]

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


# a wrapper for a list of MdpPropertyResults
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