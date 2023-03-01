import math
from collections import defaultdict

import stormpy
from ..hypersketch.hyperresult import MdpHyperPropertyResult
from ..profiler import Profiler
from ..sketch.holes import Holes, Hole, DesignSpace
from ..synthesizers.models import MarkovChain
from ..synthesizers.quotient import QuotientContainer

import logging
logger = logging.getLogger(__name__)


class HyperPropertyQuotientContainer(QuotientContainer):
    def __init__(self, sketch, parser):
        super().__init__(sketch)

        # build the quotient
        MarkovChain.builder_options.set_build_choice_labels(True)
        self.quotient_mdp = stormpy.build_sparse_model_with_options(self.sketch.prism, MarkovChain.builder_options)
        MarkovChain.builder_options.set_build_choice_labels(False)
        logger.debug(f"Constructed quotient MDP having {self.quotient_mdp.nr_states} states and {self.quotient_mdp.nr_choices} actions.")

        # to each state, construct a hole with options corresponding to actions
        # available at this state; associate each action with the corresponding
        # hole-option pair
        holes = Holes()

        assert self.quotient_mdp.has_choice_labeling()
        assert self.quotient_mdp.has_state_valuations()

        self.action_to_hole_options = []

        self.same_hole_hyper_split = 0
        self.split_on_primary = True

        self.sum_splitting = 0
        self.splits = 0

        # a dictionary of corresponding state names to a list of the corresponding instantiated holes
        matching_dictionary = defaultdict(list)

        for state in range(self.quotient_mdp.nr_states):

            # skip states without nondeterminism
            num_actions = self.quotient_mdp.get_nr_available_actions(state)
            if num_actions == 1:
                self.action_to_hole_options.append({})
                continue

            # a hole to be created
            state_name = self.quotient_mdp.state_valuations.get_string(state)
            variable_valuations = parser.parse_state_name(state_name, parse_state_quant=True)
            initial_states = parser.compute_initial_states(variable_valuations)
            associated_scheduler = parser.compute_associated_schedulers(variable_valuations)
            asch_list = [associated_scheduler]

            #first, check whether this hole belongs to some structural equality constraint
            is_constrained = False
            hole_index = None
            hole_name = state_name
            for constraint in parser.structural_equalities:
                (c_valuations, c_name, c_schedulers) = constraint
                is_constrained = parser.check_constraint_inclusion(c_valuations, c_schedulers, variable_valuations, associated_scheduler)
                if is_constrained:
                    hole_index = holes.lookup_hole_index(c_name, c_schedulers)
                    # update the name of the hole that we are currently creating
                    hole_name = c_name
                    variable_valuations = c_valuations
                    asch_list = c_schedulers
                    break

            if is_constrained and hole_index is not None:
                # this hole has already been defined somewhere, and it is in the list
                holes[hole_index].initial_states = holes[hole_index].initial_states.union(initial_states)
                parser.update_corresponding_holes(hole_index, state_name)
                index_list = []
                for offset in range(num_actions):
                    choice = self.quotient_mdp.get_choice_index(state, offset)
                    labels = self.quotient_mdp.choice_labeling.get_labels_of_choice(choice)
                    labels = str(labels)
                    index = None
                    for idx, label in enumerate(holes[hole_index].option_labels):
                        labels = str(labels)
                        if label == str(labels):
                            index = idx

                    assert index is not None
                    assert index not in index_list
                    index_list.append(index)
                    self.action_to_hole_options.append({hole_index: index})
                continue


            # create a new hole
            hole_index = len(holes)
            hole_options = list(range(num_actions))

            # extract labels for each option
            hole_option_labels = []
            for offset in range(num_actions):
                choice = self.quotient_mdp.get_choice_index(state,offset)
                labels = self.quotient_mdp.choice_labeling.get_labels_of_choice(choice)
                hole_option_labels.append(labels)
                self.action_to_hole_options.append({hole_index:offset})

            hole_option_labels = [str(labels) for labels in hole_option_labels]
            parser.update_corresponding_holes(hole_index, state_name)

            # TODO: remove state_quant from the hole_name here?
            hole = Hole(hole_name, hole_options, hole_option_labels, initial_states=initial_states,
                        variable_valuations=variable_valuations, associated_schedulers=asch_list)

            holes.append(hole)

        # now sketch has the corresponding design space
        self.sketch.design_space = DesignSpace(holes)
        self.sketch.design_space.property_indices = self.sketch.specification.all_constraint_indices()

        self.compute_default_actions()
        self.compute_state_to_holes()

    def scheduler_consistent_pctl(self, mdp, prop, result, initial_state):
        '''
        Get hole assignment induced by this scheduler and fill undefined
        holes by some option from the design space of this mdp.
        :return hole assignment
        :return whether the scheduler is consistent
        '''
        # selection = self.scheduler_selection(mdp, result.scheduler)
        if mdp.is_dtmc:
            selection = [[mdp.design_space[hole_index].options[0]] for hole_index in mdp.design_space.hole_indices]
            return selection, None, None, None, True

        return self.scheduler_selection_quantitative_pctl(mdp, prop, result, initial_state)

    def scheduler_consistent_hyper(self, mdp, prop, result, initial_state, result_alt, other_initial_state):
        '''
        Get hole assignment induced by this scheduler and fill undefined
        holes by some option from the design space of this mdp.
        :return hole assignment
        :return whether the scheduler is consistent
        '''
        # selection = self.scheduler_selection(mdp, result.scheduler)
        if mdp.is_dtmc:
            selection = [[mdp.design_space[hole_index].options[0]] for hole_index in mdp.design_space.hole_indices]
            return selection, True, selection, True, selection, True, None

        # with respect to the original implementation
        # we don't want to fill non reachable holes, the choice is left open for them
        return self.scheduler_selection_quantitative_hyper(mdp, prop, result, initial_state, result_alt, other_initial_state)

    def scheduler_selection_quantitative_pctl(self, mdp, prop, result, initial_state):
        '''
        Get hole options involved in the scheduler selection.
        '''
        Profiler.start("quotient::scheduler_selection_quantitative")

        scheduler = result.scheduler

        # get qualitative scheduler selection, filter inconsistent assignments
        selection = self.scheduler_selection(mdp, scheduler, initial_state)
        # extract choice values, compute expected visits
        choice_values = self.choice_values(mdp, prop, result)
        expected_visits = self.expected_visits(mdp, prop, result.scheduler, initial_state)

        # estimate scheduler difference
        inconsistent_assignments = {hole_index:options for hole_index,options
                                    in enumerate(selection) if len(options) > 1}
        consistent = len(inconsistent_assignments) == 0


        if consistent:
            hole_assignments = {hole_index: hole.options for hole_index, hole in enumerate(mdp.design_space) if
                                len(hole.options) > 1 and selection[hole_index]}
        else:
            hole_assignments = inconsistent_assignments

        assert len(hole_assignments) > 0

        differences = \
            self.estimate_scheduler_difference(mdp, hole_assignments, choice_values,
                                                     expected_visits, initial_state)

        Profiler.resume()
        return selection, choice_values, expected_visits, differences, consistent

    def scheduler_selection_quantitative_hyper(self, mdp, prop, result, initial_state, result_alt, other_initial_state):
        '''
        Get hole options involved in the scheduler selection.
        '''
        Profiler.start("quotient::scheduler_selection_quantitative")

        scheduler = result.scheduler
        scheduler_alt = result_alt.scheduler

        # get qualitative scheduler selection, filter inconsistent assignments
        primary_selection = self.scheduler_selection(mdp, scheduler, initial_state)
        secondary_selection = self.scheduler_selection(mdp, scheduler_alt, other_initial_state)
        joint_selection = [list(set(l1 + l2)) for l1, l2 in zip(primary_selection, secondary_selection)]

        # compute primary and secondary consistent
        primary_consistent = True
        for l in primary_selection:
            if len(l) > 1:
                primary_consistent = False
                break

        secondary_consistent = True
        for l in secondary_selection:
            if len(l) > 1:
                secondary_consistent = False
                break

        # extract choice values, compute expected visits
        primary_choice_values = self.choice_values(mdp, prop, result)
        primary_expected_visits = self.expected_visits(mdp, prop, scheduler, initial_state)

        secondary_choice_values = self.choice_values(mdp, prop, result_alt)
        secondary_expected_visits = self.expected_visits(mdp, prop, scheduler_alt, other_initial_state)

        # estimate scheduler difference
        inconsistent_assignments = {hole_index:options for hole_index,options
                                    in enumerate(joint_selection) if len(options) > 1}
        joint_consistent = len(inconsistent_assignments) == 0


        if joint_consistent:
            hole_assignments = {hole_index: hole.options for hole_index, hole in enumerate(mdp.design_space) if
                                len(hole.options) > 1}
        else:
            #print(f"inconsistent. Inconsistent assignments: {inconsistent_assignments}")
            hole_assignments  = inconsistent_assignments

        assert len(hole_assignments) > 0

        primary_differences = \
            self.estimate_scheduler_difference(mdp, hole_assignments, primary_choice_values,
                                                         primary_expected_visits)
        secondary_differences = \
            self.estimate_scheduler_difference(mdp, hole_assignments, secondary_choice_values,
                                                         secondary_expected_visits)

        #if not joint_consistent:
            #print(f"primary differences: {primary_differences}")
            #print(f"secondary differences:  {secondary_differences}")


        Profiler.resume()
        return primary_selection, primary_consistent, primary_differences, \
               secondary_selection, secondary_consistent, secondary_differences, \
               joint_selection, joint_consistent

    def scheduler_selection(self, mdp, scheduler, initial_state):
        ''' Get hole options involved in the scheduler selection. '''
        assert scheduler.memoryless and scheduler.deterministic

        Profiler.start("quotient::scheduler_selection")

        # construct DTMC that corresponds to this scheduler and filter reachable states/choices
        choices = scheduler.compute_action_support(mdp.model.nondeterministic_choice_indices)
        dtmc,_,choice_map = self.restrict_mdp(mdp.model, choices)
        choices = [ choice_map[state] for state in range(dtmc.nr_states) ]

        # map relevant choices to hole options
        selection = [set() for hole_index in mdp.design_space.hole_indices]
        for choice in choices:
            global_choice = mdp.quotient_choice_map[choice]
            choice_options = self.action_to_hole_options[global_choice]
            for hole_index,option in choice_options.items():
                # this hole is relevant for the initial state
                if initial_state in mdp.design_space[hole_index].initial_states:
                    selection[hole_index].add(option)
        selection = [list(options) for options in selection]
        Profiler.resume()

        return selection

    def estimate_scheduler_difference(self, mdp, hole_assignments, choice_values, expected_visits):
        Profiler.start(" estimate scheduler difference")

        # for each hole, compute its difference sum and a number of affected states
        hole_difference_sum = {hole_index: 0 for hole_index in hole_assignments}
        hole_states_affected = {hole_index: 0 for hole_index in hole_assignments}
        hole_difference_max = {hole_index: 0 for hole_index in hole_assignments}
        options_rankings = {hole_index: [] for hole_index in hole_assignments}
        tm = mdp.model.transition_matrix

        for state in range(mdp.states):

            # for this state, compute for each hole the difference in choice values between respective options
            hole_min = None
            hole_max = None
            ranking = []

            for choice in range(tm.get_row_group_start(state), tm.get_row_group_end(state)):

                choice_global = mdp.quotient_choice_map[choice]
                if self.default_actions.get(choice_global):
                    # there isn't a hole assignment associated with this action
                    continue

                choice_options = self.action_to_hole_options[choice_global]
                # every choice corresponds to choosing one option for one hole, the hole of the state
                assert len(list(choice_options.items())) == 1
                hole_index, option = list(choice_options.items())[0]

                inconsistent_options = hole_assignments.get(hole_index, set())
                if option not in inconsistent_options:
                    continue

                value = choice_values[choice]
                if hole_min is None or value < hole_min:
                    hole_min = value
                if hole_max is None or value > hole_max:
                    hole_max = value
                ranking.append((option, value))

            if hole_min is None or hole_max is None:
                # this state has no hole to fill
                continue

            # compute the difference and the ranking
            difference = (hole_max - hole_min) * expected_visits[state]
            assert not math.isnan(difference)
            hole_difference_sum[hole_index] += difference
            hole_states_affected[hole_index] += 1
            if difference >= hole_difference_max[hole_index]:
                hole_difference_max[hole_index] = difference
                ranking.sort(key=lambda tup: tup[1])
                # print(f"Found the current ranking for hole_index {hole_index}: {ranking}")
                options_rankings[hole_index] = [i for i, _ in ranking]

        # filter out unreachable holes, which don't have any option in the ranking
        # but in the current approach we consider only overall reachability in the MDP
        # TODO: handle the case where some holes are not reachable from current initial state
        # i.e., expected visits of the state are zero
        # for example, for PC this holds for all holes from the initial state of the DTMC
        options_rankings = {key: value for key,value in options_rankings.items() if value}
        hole_differences = {key: hole_difference_sum[key] / hole_states_affected[key] for key in options_rankings}

        # aggregate the results
        hole_differences = (hole_differences, options_rankings)
        Profiler.resume()
        return hole_differences

    # split the options of the best hole according to the scores
    def compute_suboptions(self, scores, primary, minimizing, mdp):

        scores, options_rankings = scores

        # compute the hole on which to split
        splitters = self.holes_with_max_score(scores)
        splitter = splitters[0]

        # get the corresponding option for that split, already ordered by choice_value
        options = options_rankings[splitter]

        take_highest = primary == minimizing

        if take_highest:
            # -1 takes last element
            core_suboption = options[-1]
        else:
            core_suboption = options[0]

        other_suboptions = [option for option in mdp.design_space[splitter].options if option != core_suboption]

        return [[core_suboption]], other_suboptions, splitter, scores[splitter]


    def split(self, family):
        Profiler.start("quotient::split")

        mdp = family.mdp
        assert not mdp.is_dtmc
        # reduced design space
        new_design_space = mdp.design_space.copy()

        # split family wrt last undecided result
        result = family.analysis_result.undecided_result()
        assert result is not None
        isHyper = isinstance(result, MdpHyperPropertyResult)
        minimizing = result.property.minimizing


        # compute the hole on which to split given by the analysis of the secondary scheduler
        #print(f"primary scores: {result.primary_scores}")
        primary_core_suboptions, primary_other_suboptions, primary_splitter, primary_splitter_score = \
            self.compute_suboptions(result.primary_scores, True, minimizing, mdp)

        assert primary_splitter_score > 0

        # compute the hole on which to split given by the analysis of the secondary scheduler
        if isHyper:
            secondary_core_suboptions, secondary_other_suboptions, secondary_splitter, secondary_splitter_score = \
                self.compute_suboptions(result.secondary_scores, False, minimizing, mdp)
            assert secondary_splitter_score > 0

        design_subspaces = []
        if not isHyper or primary_splitter == secondary_splitter:
            # fix the suboptions
            if not isHyper:
                splitter = primary_splitter
                if not result.primary_consistent:
                    core_suboptions, other_suboptions = self.suboptions_enumerate(mdp, primary_splitter,
                                                                                  result.primary_selection[primary_splitter])
                else:
                    core_suboptions, other_suboptions = primary_core_suboptions, primary_other_suboptions
            else:
                # TODO: improve the reasoning here, and distinguish between the case when primary and secondary
                #  are consistent and when they are not.
                self.same_hole_hyper_split += 1
                if self.same_hole_hyper_split %1000 == 0:
                    logger.info(f"{self.same_hole_hyper_split} Hyper splits on the same hole")
                core_suboptions, other_suboptions = (primary_core_suboptions, primary_other_suboptions) if self.split_on_primary else (secondary_core_suboptions, secondary_other_suboptions)
                splitter = primary_splitter if self.split_on_primary else secondary_splitter
                self.split_on_primary = not self.split_on_primary

            if len(other_suboptions) > 0:
                suboptions_list = [other_suboptions] + core_suboptions  # DFS solves core first
            else:
                suboptions_list = core_suboptions
            # construct corresponding design subspaces

            family.splitters = [splitter]
            parent_info = family.collect_parent_info()
            for suboptions in suboptions_list:
                subholes = new_design_space.subholes([(splitter, suboptions)])
                design_subspace = DesignSpace(subholes, parent_info)
                # TODO: do we need this? Isn't it done by subhole method?
                design_subspace.assume_hole_options(splitter, suboptions)
                design_subspaces.append(design_subspace)
        else:
            primary_suboptions = [primary_other_suboptions] + primary_core_suboptions
            secondary_suboptions = [secondary_other_suboptions] + secondary_core_suboptions
            suboptions_list = [(i, j) for i in primary_suboptions for j in secondary_suboptions]
            # construct corresponding design subspaces
            family.splitters = [primary_splitter, secondary_splitter]
            parent_info = family.collect_parent_info()
            for (primary_suboptions, secondary_suboptions) in suboptions_list:
                subholes = new_design_space.subholes(
                    [(primary_splitter, primary_suboptions), (secondary_splitter, secondary_suboptions)])
                design_subspace = DesignSpace(subholes, parent_info)
                # TODO: do we need this? Isn't it done by subhole method?
                design_subspace.assume_hole_options(primary_splitter, primary_suboptions)
                design_subspace.assume_hole_options(secondary_splitter, secondary_suboptions)
                design_subspaces.append(design_subspace)

        Profiler.resume()
        return design_subspaces

    def double_check_assignment_scheduler_hyperoptimality(self, assignment):
        '''
        Double-check whether this assignment truly improves optimum.
        :return singleton family if the assignment truly improves optimum
        '''
        assert assignment.size == 1
        dtmc = self.build_chain(assignment)
        res = dtmc.check_hyperspecification(self.sketch.specification, assignment)
        # opt_result = dtmc.model_check_property(opt_prop)
        if res.constraints_result.all_sat and self.sketch.specification.sched_hyperoptimality.improves_hyperoptimum(
                res.sched_hyperoptimality_result.value):
            return assignment, res.sched_hyperoptimality_result.value
        else:
            return None, None

    def double_check_hyperassignment(self, assignment):
        '''
        Double-check whether this assignment truly improves optimum.
        :return singleton family if the assignment truly improves optimum
        '''
        assert assignment.size == 1
        dtmc = self.build_chain(assignment)
        res = dtmc.check_hyperspecification(self.sketch.specification, assignment)
        if res.constraints_result.all_sat and self.sketch.specification.optimality.improves_optimum(
                res.optimality_result.value):
            return assignment, res.optimality_result.value
        else:
            return None, None
