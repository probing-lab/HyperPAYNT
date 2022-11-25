# a specification is just a set of properties
from .property import OptimalityProperty


class PropertyResult:
    def __init__(self, prop, result, value):
        self.property = prop
        self.result = result
        self.value = value
        self.sat = prop.satisfies_threshold(value)
        self.improves_optimum = None if not isinstance(prop, OptimalityProperty) else prop.improves_optimum(value)

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
                 primary_selection, primary_feasibility, primary_choice_values, primary_expected_visits, primary_scores
                 ):
        self.property = prop
        self.primary = primary
        self.secondary = secondary
        self.feasibility = feasibility

        self.primary_selection = primary_selection
        # primary feasibility indicates whether the primary selection induces a SAT scheduler
        # this can be exploited easily because we do not have inconsistent selections.
        self.primary_feasibility = primary_feasibility
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


class MdpOptimalityResult(MdpPropertyResult):
    def __init__(self,
                 prop, primary, secondary,
                 improving_assignment, improving_value, can_improve,
                 primary_selection, primary_choice_values, primary_expected_visits,
                 primary_scores
                 ):
        super().__init__(
            prop, primary, secondary, None,
            primary_selection, primary_choice_values, primary_expected_visits,
            primary_scores)
        self.improving_assignment = improving_assignment
        self.improving_value = improving_value
        self.can_improve = can_improve


