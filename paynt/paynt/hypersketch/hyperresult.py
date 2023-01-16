from .hyperproperty import HyperSpecification


class HyperPropertyResult:
    # TODO: for the moment, I haven't implemented optimality hyperproperties
    def __init__(self, prop, result, result_alt):
        # the reachability property that we are verifying
        self.property = prop
        # a vector of results for each state of the Markov Chain
        self.result = result
        # for a DTMC, result and result_alt are the same
        # result_alt is basically the secondary direction
        self.result_alt = result_alt

        #setting the result value
        self.value = result.at(prop.state)

        # set the threshold
        self.threshold = result_alt.at(prop.other_state)

        self.sat = prop.satisfies_threshold(self.value, self.threshold)

        # improving the optimumum with respect to an hyperproperty
        # TODO: implement me!
        self.improves_hyperoptimum = False

    def __str__(self):
        return f"{self.value}(s_ {self.property.state}) vs {self.threshold}(s_{self.property.other_state}): {self.sat}"


class HyperConstraintsResult:
    '''
    A list of property results.
    Note: some results might be None (not evaluated).
    '''
    def __init__(self, results):
        self.results = results
        self.all_sat = True

        sat_list = list(map(lambda x: None if x is None else x.sat, results))
        filtered_result = HyperSpecification.or_filter(sat_list, True)

        for result in filtered_result:
            if result is not None and result == False:
                self.all_sat = False
                break

    def __str__(self):
        return ";\n".join([str(result) for result in self.results])

    def isSat(self, index):
        sat_list = list(map(lambda x: None if x is None else x.sat, self.results))
        filtered_result = HyperSpecification.or_filter(sat_list, True)
        return filtered_result[index]


class SchedulerOptimalityHyperPropertyResult(HyperPropertyResult):
    def __init__(self, prop, value):
        # the scheduler optimality hyperproperty we are verifying
        self.property = prop

        self.value = value

        self.sat = prop.satisfies_threshold(self.value)
        self.improves_hyperoptimum = prop.improves_hyperoptimum(self.value)

        # the rest are useless
        self.result = None
        self.result_alt = None
        self.threshold = None

    def __str__(self):
        return f"Current optimal value: {self.property.hyperoptimum}"


class HyperSpecificationResult:
    def __init__(self, constraints_result, optimality_result, scheduler_hyperoptimality_result):
        self.constraints_result = constraints_result
        self.optimality_result = optimality_result
        self.sched_hyperoptimality_result = scheduler_hyperoptimality_result

    def improving(self, family):
        ''' Interpret MDP constraints result. '''

        cr = self.constraints_result
        opt = self.optimality_result
        sched_hyperopt = self.sched_hyperoptimality_result

        # just one optimality of any type can be specified
        assert opt is None or sched_hyperopt is None

        # cr.feasibility can be:
        # True - every scheduler of this family satisfies all constraints
        # False - no scheduler of this family satisfies all constraints
        # None - undecided result

        # returns:
        # 1) a SAT assignment (that is improving the optimality property, if there is any optimality prop) (
        #       if there is any SAT assignment)
        # 2) the value that is improving

        # constraints were satisfied
        if cr.feasibility is True:
            # either no constraints or constraints were satisfied
            if opt is not None:
                return opt.improving_assignment, opt.improving_value, opt.can_improve
            if sched_hyperopt is not None:
                return sched_hyperopt.improving_assignment, sched_hyperopt.improving_value, sched_hyperopt.can_improve
            else:
                improving_assignment = family.pick_any()
                return improving_assignment, None, False

        # constraints not satisfied
        if cr.feasibility is False:
            return None, None, False

        # constraints undecided: try to push optimality or hyperoptimality assignment
        if opt is not None:
            #TODO: I have modified this
            return opt.improving_assignment, opt.improving_value, opt.can_improve

        if sched_hyperopt is not None:
            return sched_hyperopt.improving_assignment, sched_hyperopt.improving_value, sched_hyperopt.can_improve

        # constraints undecided, but primary selection is consistent and both feasible and the same for all constraints
        # and, there is no optimality or scheduler_hyperoptimality property
        # TODO: we might improve this and deal also with the case where there is an (hyper)optimality constraint
        if cr.primary_feasibility and opt is None and sched_hyperopt is None:
            selection = cr.primary_selections[0]

            # fill empty holes
            for hole_index in family.mdp.design_space.hole_indices:
                options = selection[hole_index]
                if options == []:
                    selection[hole_index] = [family.mdp.design_space[hole_index].options[0]]

            assignment = family.copy()
            assignment.assume_options(selection)
            # here can_improve == True because we don't have any optimality property, can_improve
            return assignment, None, True

        # constraints undecided
        return None, None, True

    def undecided_result(self):
        if self.optimality_result is not None and self.optimality_result.can_improve:
            return self.optimality_result

        return self.constraints_result.results[self.constraints_result.undecided_constraints[0]]

    def __str__(self):
        return str(self.constraints_result) + "\n" + str(self.optimality_result) + "\n" + str(
            self.sched_hyperoptimality_result)


class MdpHyperPropertyResult:
    def __init__(self,
                 prop, primary, secondary, feasibility,
                 primary_selection, primary_feasibility, primary_choice_values, primary_expected_visits,
                 primary_scores, secondary_selection, secondary_choice_values, secondary_expected_visits, secondary_scores
                 ):
        self.property = prop
        self.primary = primary
        self.secondary = secondary
        self.feasibility = feasibility

        #TODO: this does not work with multi targets comparisons
        self.primary_selection = primary_selection
        self.primary_feasibility = primary_feasibility
        self.primary_choice_values = primary_choice_values
        self.primary_expected_visits = primary_expected_visits
        self.primary_scores = primary_scores

        self.secondary_selection = secondary_selection
        self.secondary_choice_values = secondary_choice_values
        self.secondary_expected_visits = secondary_expected_visits
        self.secondary_scores = secondary_scores

    def __str__(self):
        prim = str(self.primary)
        seco = str(self.secondary)
        return "Primary direction: {} \nSecondary direction {}; ".format(prim, seco)


class MdpHyperConstraintsResult:
    def __init__(self, results):

        res_dict = {index: result for index, result in enumerate(results) if result is not None}
        grouped_results = HyperSpecification.or_group_dict(res_dict)

        # feasibility list
        feas_list = list(map(lambda x: False if x is None else x.feasibility, results))
        fr_True = HyperSpecification.or_filter(feas_list, True)
        fr_None = HyperSpecification.or_filter(feas_list, None)

        # primary feasibility list
        pr_feas_list = list(map(lambda x: False if x is None else x.primary_feasibility, results))
        pr_fr_True = HyperSpecification.or_filter(pr_feas_list, True)

        self.results = results

        # undecided constraint which are not in a or relation with a true constraint
        self.undecided_constraints = [index for index, result in enumerate(results) if
                                      result is not None and result.feasibility is None
                                      and fr_True[index] is None]

        # overall feasibility of the set of constraints
        self.feasibility = True

        # is there a primary scheduler consistent, feasible and the same for all constraints?
        self.primary_feasibility = None
        self.primary_selections = []

        for group in grouped_results:
            # this group is empty
            if not group:
                continue

            if self.feasibility is False:
                # a previous group was unfeasible
                break

            group_primary_selections = []
            for index, result in group:
                # we haven't checked this property
                if result is None:
                    continue

                orTrue = fr_True[index]
                orNone = fr_None[index]
                pr_orTrue = pr_fr_True[index]
                # this property is unfeasible, and not in an Or relation with a True or undecided property
                if result.feasibility is False and orTrue is False and orNone is False:
                    self.feasibility = False
                    self.primary_feasibility = False
                    self.primary_selections = []
                    break

                # this property is undecided and not in a Or relation with a True property
                if result.feasibility is None and orTrue is None:
                    self.feasibility = None

                self.update_primary_feasibility(result, pr_orTrue, group_primary_selections)

            self.update_primary_feasibility_groups(group_primary_selections)


    def check_lists(self, l1, l2):
        assert len(l1) <= 1 and len(l2) <= 1
        return not l1 or not l2 or l1[0] == l2[0]

    def update_primary_feasibility(self, result, orTrue, group_primary_selections):
        primary_feasibility = result.primary_feasibility
        primary_selection = result.primary_selection

        # primary feasibility of the constraints is already false
        if self.primary_feasibility is False:
            return

        # primary feasibility of this property is False and not in a Or relation with a True primary feasibility
        if not primary_feasibility and not orTrue:
            self.primary_feasibility = False
            self.primary_selections = []
            return

        # primary feasibility of this property is False
        if not primary_feasibility:
            return

        # primary feasibility of this property is True
        group_primary_selections.append(primary_selection)

    def update_primary_feasibility_groups(self, group_primary_selections):

        # primary feasibility of the constraints is already false
        if self.primary_feasibility is False:
            return

        # update primary selections stored
        if self.primary_feasibility is None:
            # this is the first iteration of the algorithm
            self.primary_selections = group_primary_selections
            self.primary_feasibility = self.primary_selections is not []
        else:
            # self.primary_feasiblity is True
            # check satisfiability of the already stored primary selections, combined with the new ones
            new_selections = []
            for saved_selection in self.primary_selections:
                for found_selection in group_primary_selections:
                    check_compatible = [self.check_lists(a, b) for a, b in zip(saved_selection, found_selection)]
                    if all(check_compatible):
                        new_selection = [list(set(a + b)) for a, b in zip(saved_selection, found_selection)]
                        new_selections.append(new_selection)
            self.primary_selections = new_selections
            self.primary_feasibility = self.primary_selections

    def __str__(self):
        return ",".join([str(result) for result in self.results])


# TODO: implement this!
class MdpHyperOptimalityResult(MdpHyperPropertyResult):
    def __init__(self):
        raise NotImplementedError("Implement me, Mario!")


class MdpSchedulerHyperOptimalityResult:
    def __init__(self, prop, primary, improving_assignment, improving_value, can_improve):
        # the scheduler optimality hyperproperty we are verifying
        self.property = prop
        # primary HyperPropertyResult (for the moment we do not consider in the implementation the secondary
        # direction for this type of hyperproperties)
        self.primary = primary
        self.improving_assignment = improving_assignment
        self.improving_value = improving_value
        self.can_improve = can_improve

    def __str__(self):
        return f"Current optimum value inside this MDP: {self.property.hyperoptimum}. " \
               f"This MDP has primary value {self.primary}."
