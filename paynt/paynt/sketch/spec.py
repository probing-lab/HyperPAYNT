

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
            filtered_sublist = list(filter(lambda x: x in indexes, sublist))
            grouped.append(filtered_sublist)
        return grouped

    @classmethod
    def or_group_dict(cls, dict):
        keys = dict.keys()
        grouped = []
        for sublist in Specification.disjoint_indexes:
            filtered_sublist = list(filter(lambda i: i in keys, sublist))
            res_slice = list(map(lambda i: (i, dict[i]), filtered_sublist))
            grouped.append(res_slice)
        return grouped


class PropertyResult:
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

    def __str__(self):
        return str(self.value) + "(s_" + str(self.property.state) + ") vs " + str(self.threshold) \
               + "(s_" + str(self.property.other_state) + "): " + str(self.sat)


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
        if self.property.minimizing:
            return "{} - {}; ".format(prim, seco)
        else:
            return "{} - {}; ".format(seco, prim)


# a wrapper for a list of MdpPropertyResults
class MdpConstraintsResult:
    def __init__(self, results):

        res_dict = {index: result for index, result in enumerate(results) if result is not None}
        grouped_results = Specification.or_group_dict(res_dict)

        # feasibility list
        feas_list = list(map(lambda x: False if x is None else x.feasibility, results))
        fr_True = Specification.or_filter(feas_list, True)
        fr_None = Specification.or_filter(feas_list, None)

        # primary feasibility list
        pr_feas_list = list(map(lambda x: False if x is None else x.primary_feasibility, results))
        pr_fr_True = Specification.or_filter(pr_feas_list, True)

        self.results = results

        # undecided constraint which are not in a or relation with a true constraint
        self.undecided_constraints = [index for index, result in enumerate(results) if
                                      result is not None and result.feasibility is None
                                      and fr_True[index] is None]

        # overall feasibility of the set of constraints
        self.feasibility = True

        # is there a primary scheduler consistent, feasible and the same for all constraints?
        self.primary_feasibility = True
        self.primary_selections = []

        for group in grouped_results:
            # this group is empty
            if not group:
                continue

            primary_selections = []
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
                    break

                # this property is undecided and not in a Or relation with a True property
                if result.feasibility is None and orTrue is None:
                    self.feasibility = None
                self.update_primary_feasibility(result, pr_orTrue, primary_selections)

            self.update_primary_feasibility_groups(primary_selections)

    def check_lists(self, l1, l2):
        return set(l1) == set(l2) or l1 is [] or l2 is []

    def update_primary_feasibility(self, result, orTrue, primary_selections):
        primary_feasibility = result.primary_feasibility
        primary_selection = result.primary_selection

        # primary feasibility of the constraints is already false
        if not self.primary_feasibility:
            return

        # primary feasibility of this property is False and not in a Or relation with a True primary feasibility
        if not primary_feasibility and not orTrue:
            self.primary_feasibility = False
            return

        # primary feasibility of this property is False but in a Or relation with a True primary feasibility
        if not primary_feasibility and orTrue:
            return

        if primary_feasibility:
            primary_selections.append(primary_selection)

    def update_primary_feasibility_groups(self, primary_selections):
        # update primary selections stored
        if self.primary_feasibility and not self.primary_selections:
            # this is the first iteration of the algorithm
            self.primary_selections = primary_selections
            self.primary_feasibility = self.primary_selections is not []
        elif self.primary_feasibility:
            # check satisfiability of the already stored primary selections
            new_selections = []
            for saved_selection in self.primary_selections:
                for found_selection in primary_selections:
                    check_compatible = [self.check_lists(a, b) for a, b in zip(saved_selection, found_selection)]
                    if all(check_compatible):
                        new_selection = [a + b for a, b in zip(saved_selection, found_selection)]
                        new_selections.append(new_selection)
            self.primary_selections = new_selections
            self.primary_feasibility = self.primary_selections is not []

    def improving(self, family):
        ''' Interpret MDP constraints result. '''

        # self.feasibility can be:
        # True - every scheduler of this family satisfies all constraints
        # False - no scheduler of this family satisfies all constraints
        # None - undecided result

        # constraints were satisfied
        if self.feasibility is True:
            improving_assignment = family.pick_any()
            return improving_assignment, False

        # constraints not satisfied
        if self.feasibility is False:
            return None,False

        # constraints undecided, but primary selection is consistent and both feasible and the same for all constraints
        if self.primary_feasibility:
                selection = self.primary_selections[0]

                # fill empty holes
                for hole_index in family.mdp.design_space.hole_indices:
                    options = selection[hole_index]
                    if options == []:
                        selection[hole_index] = [family.mdp.design_space[hole_index].options[0]]

                assignment = family.copy()
                assignment.assume_options(selection)
                return assignment, True

        # constraints undecided
        return None, True

    def __str__(self):
        return ",".join([str(result) for result in self.results])

    def undecided_result(self):
        return self.results[self.undecided_constraints[0]]
