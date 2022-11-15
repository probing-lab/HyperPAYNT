import stormpy
import stormpy.synthesis

import math
import re
import itertools

from .statistic import Statistic

from ..sketch.holes import Hole,Holes,DesignSpace

from .synthesizer import Synthesizer

from ..profiler import Profiler

from .models import MarkovChain,MDP,DTMC

import logging
logger = logging.getLogger(__name__)


class QuotientContainer:

    def __init__(self, sketch):
        # model origin
        self.sketch = sketch

        # quotient MDP for the super-family
        self.quotient_mdp = None

        # for each choice of the quotient MDP contains a set of hole-option labelings
        self.action_to_hole_options = None
        # bitvector of quotient MDP choices not labeled by any hole
        self.default_actions = None
        # for each state of the quotient MDP, a set of holes associated with the actions in this state
        self.state_to_holes = None

        # builder options
        self.subsystem_builder_options = stormpy.SubsystemBuilderOptions()
        self.subsystem_builder_options.build_state_mapping = True
        self.subsystem_builder_options.build_action_mapping = True

        # (optional) counter of discarded assignments
        self.discarded = None

    def compute_default_actions(self):
        self.default_actions = stormpy.BitVector(self.quotient_mdp.nr_choices, False)
        for choice in range(self.quotient_mdp.nr_choices):
            if not self.action_to_hole_options[choice]:
                self.default_actions.set(choice)

    def compute_state_to_holes(self):
        tm = self.quotient_mdp.transition_matrix
        self.state_to_holes = []
        for state in range(self.quotient_mdp.nr_states):
            relevant_holes = set()
            for action in range(tm.get_row_group_start(state), tm.get_row_group_end(state)):
                # TODO: isn't it true that for a state all actions have the same hole set?
                # TODO: why do we iterate over all the actions?
                relevant_holes.update(set(self.action_to_hole_options[action].keys()))
            self.state_to_holes.append(relevant_holes)

    def select_actions(self, family):
        ''' Select non-default actions relevant in the provided design space. '''
        Profiler.start("quotient::select_actions")

        if family.parent_info is None:
            # select from the super-quotient
            selected_actions = []
            for action in range(self.quotient_mdp.nr_choices):
                if self.default_actions[action]:
                    continue
                hole_options = self.action_to_hole_options[action]
                if family.includes(hole_options):
                    selected_actions.append(action)
        else:
            # filter each action in the parent wrt newly restricted design space
            parent_actions = family.parent_info.selected_actions
            selected_actions = []
            for action in parent_actions:
                hole_options = self.action_to_hole_options[action]
                if family.includes(hole_options):
                    selected_actions.append(action)

        # construct bitvector of selected actions
        selected_actions_bv = stormpy.synthesis.construct_selection(self.default_actions, selected_actions)

        Profiler.resume()
        return None,selected_actions,selected_actions_bv

    def restrict_mdp(self, mdp, selected_actions_bv):
        '''
        Restrict the quotient MDP to the selected actions.
        :param selected_actions_bv a bitvector of selected actions
        :return (1) the restricted model
        :return (2) sub- to full state mapping
        :return (3) sub- to full action mapping
        '''
        Profiler.start("quotient::restrict_mdp")

        keep_unreachable_states = False # TODO investigate this
        all_states = stormpy.BitVector(mdp.nr_states, True)
        submodel_construction = stormpy.construct_submodel(
            mdp, all_states, selected_actions_bv, keep_unreachable_states, self.subsystem_builder_options
        )

        model = submodel_construction.model
        state_map = list(submodel_construction.new_to_old_state_mapping)
        choice_map = list(submodel_construction.new_to_old_action_mapping)

        Profiler.resume()
        return model,state_map,choice_map



    def restrict_quotient(self, selected_actions_bv):
        return self.restrict_mdp(self.quotient_mdp, selected_actions_bv)


    def build(self, family):
        ''' Construct the quotient MDP for the family. '''

        # select actions compatible with the family and restrict the quotient
        hole_selected_actions,selected_actions,selected_actions_bv = self.select_actions(family)
        model,state_map,choice_map = self.restrict_quotient(selected_actions_bv)



        # cash restriction information
        family.hole_selected_actions = hole_selected_actions
        family.selected_actions = selected_actions

        # encapsulate MDP
        family.mdp = MDP(model, self, state_map, choice_map, family)
        family.mdp.analysis_hints = family.translate_analysis_hints()

        # prepare to discard designs
        self.discarded = 0


    @staticmethod
    def mdp_to_dtmc(mdp):
        tm = mdp.transition_matrix
        tm.make_row_grouping_trivial()
        components = stormpy.storage.SparseModelComponents(tm, mdp.labeling, mdp.reward_models)
        dtmc = stormpy.storage.SparseDtmc(components)
        return dtmc


    def build_chain(self, family):
        assert family.size == 1

        _,_,selected_actions_bv = self.select_actions(family)
        mdp,state_map,choice_map = self.restrict_quotient(selected_actions_bv)
        dtmc = QuotientContainer.mdp_to_dtmc(mdp)

        return DTMC(dtmc,self,state_map,choice_map)

    def scheduler_selection(self, mdp, scheduler):
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
                selection[hole_index].add(option)
        selection = [list(options) for options in selection]
        Profiler.resume()

        return selection


    @staticmethod
    def make_vector_defined(vector):
        vector_noinf = [ value if value != math.inf else 0 for value in vector]
        default_value = sum(vector_noinf) / len(vector)
        vector_valid = [ value if value != math.inf else default_value for value in vector]
        return vector_valid


    def choice_values(self, mdp, prop, result):
        '''
        Get choice values after model checking MDP against a property.
        Value of choice c: s -> s' is computed as
        ev(s) * [ rew(c) + P(s,c,s') * mc(s') ], where
        - ev(s) is the expected number of visits of state s in DTMC induced by
          the primary scheduler
        - rew(c) is the reward associated with choice (c)
        - P(s,c,s') is the probability of transitioning from s to s' under action c
        - mc(s') is the model checking result in state s'
        '''
        Profiler.start("quotient::choice_values")

        # multiply probability with model checking results
        choice_values = stormpy.synthesis.multiply_with_vector(mdp.model.transition_matrix, result.get_values())
        choice_values = QuotientContainer.make_vector_defined(choice_values)

        # if the associated reward model has state-action rewards, then these must be added to choice values
        # TODO: refactor this and move it to a new overriden method to add reward specifications to hyperproperties synthesis
        if prop.reward:
            reward_name = prop.formula.reward_name
            rm = mdp.model.reward_models.get(reward_name)
            assert not rm.has_transition_rewards and (rm.has_state_rewards != rm.has_state_action_rewards)
            if rm.has_state_action_rewards:
                choice_rewards = list(rm.state_action_rewards)
                assert mdp.choices == len(choice_rewards)
                for choice in range(mdp.choices):
                    choice_values[choice] += choice_rewards[choice]

        # sanity check
        for choice in range(mdp.choices):
            assert not math.isnan(choice_values[choice])

        Profiler.resume()

        return choice_values


    def expected_visits(self, mdp, prop, scheduler, initial_state):
        '''
        Compute expected number of visits in the states of DTMC induced by
        this scheduler.
        '''

        # extract DTMC induced by this MDP-scheduler
        choices = scheduler.compute_action_support(mdp.model.nondeterministic_choice_indices)
        sub_mdp,state_map,_ = self.restrict_mdp(mdp.model, choices)
        dtmc = QuotientContainer.mdp_to_dtmc(sub_mdp)

        # compute visits
        dtmc_visits = stormpy.synthesis.compute_expected_number_of_visits(MarkovChain.environment,
                                                                          dtmc, initial_state).get_values()
        dtmc_visits = list(dtmc_visits)

        # handle infinity- and zero-visits
        if prop.minimizing:
            dtmc_visits = QuotientContainer.make_vector_defined(dtmc_visits)
        else:
            dtmc_visits = [ value if value != math.inf else 0 for value in dtmc_visits]

        # map vector of expected visits onto the state space of the quotient MDP
        expected_visits = [0] * mdp.states
        for state in range(dtmc.nr_states):
            mdp_state = state_map[state]
            visits = dtmc_visits[state]
            expected_visits[mdp_state] = visits

        return expected_visits


    def estimate_scheduler_difference(self, mdp, inconsistent_assignments, choice_values, expected_visits):
        Profiler.start(" estimate scheduler difference")

        # for each hole, compute its difference sum and a number of affected states
        hole_difference_sum = {hole_index: 0 for hole_index in inconsistent_assignments}
        hole_states_affected = {hole_index: 0 for hole_index in inconsistent_assignments}
        tm = mdp.model.transition_matrix

        for state in range(mdp.states):

            # for this state, compute for each inconsistent hole the difference in choice values between respective options
            hole_min = {hole_index: None for hole_index in inconsistent_assignments}
            hole_max = {hole_index: None for hole_index in inconsistent_assignments}

            for choice in range(tm.get_row_group_start(state),tm.get_row_group_end(state)):

                choice_global = mdp.quotient_choice_map[choice]
                if self.default_actions.get(choice_global):
                    continue

                choice_options = self.action_to_hole_options[choice_global]

                # collect holes in which this action is inconsistent
                inconsistent_holes = []
                for hole_index,option in choice_options.items():
                    inconsistent_options = inconsistent_assignments.get(hole_index,set())
                    if option in inconsistent_options:
                        inconsistent_holes.append(hole_index)

                value = choice_values[choice]
                for hole_index in inconsistent_holes:
                    current_min = hole_min[hole_index]
                    if current_min is None or value < current_min:
                        hole_min[hole_index] = value
                    current_max = hole_max[hole_index]
                    if current_max is None or value > current_max:
                        hole_max[hole_index] = value

            # compute the difference
            for hole_index,min_value in hole_min.items():
                if min_value is None:
                    continue
                max_value = hole_max[hole_index]
                difference = (max_value - min_value) * expected_visits[state]
                assert not math.isnan(difference)

                hole_difference_sum[hole_index] += difference
                hole_states_affected[hole_index] += 1

        # aggregate
        inconsistent_differences = {
            hole_index: (hole_difference_sum[hole_index] / hole_states_affected[hole_index])
            for hole_index in inconsistent_assignments
            }

        Profiler.resume()
        return inconsistent_differences


    def scheduler_selection_quantitative(self, mdp, prop, result):
        '''
        Get hole options involved in the scheduler selection.
        Use numeric values to filter spurious inconsistencies.
        '''
        Profiler.start("quotient::scheduler_selection_quantitative")

        scheduler = result.scheduler

        # get qualitative scheduler selection, filter inconsistent assignments
        selection = self.scheduler_selection(mdp, scheduler)
        inconsistent_assignments = {hole_index:options for hole_index,options in enumerate(selection) if len(options) > 1 }
        if len(inconsistent_assignments) == 0:
            Profiler.resume()
            return selection,None,None,None

        # extract choice values, compute expected visits and estimate scheduler difference
        choice_values = self.choice_values(mdp, prop, result)
        expected_visits = self.expected_visits(mdp, prop, result.scheduler, 0)
        inconsistent_differences = self.estimate_scheduler_difference(mdp, inconsistent_assignments, choice_values,
                                                                      expected_visits)

        Profiler.resume()
        return selection,choice_values,expected_visits,inconsistent_differences


    def scheduler_consistent(self, mdp, prop, result):
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

        selection,choice_values,expected_visits,scores = self.scheduler_selection_quantitative(mdp, prop, result)
        consistent = True
        for hole_index in mdp.design_space.hole_indices:
            options = selection[hole_index]
            if len(options) > 1:
                consistent = False
            if options == []:
                selection[hole_index] = [mdp.design_space[hole_index].options[0]]

        return selection,choice_values,expected_visits,scores,consistent


    def suboptions_half(self, mdp, splitter):
        ''' Split options of a splitter into two halves. '''
        options = mdp.design_space[splitter].options
        half = len(options) // 2
        suboptions = [options[:half], options[half:]]
        return suboptions

    def suboptions_unique(self, mdp, splitter, used_options):
        ''' Distribute used options of a splitter into different suboptions. '''
        assert len(used_options) > 1
        suboptions = [[option] for option in used_options]
        index = 0
        for option in mdp.design_space[splitter].options:
            if option in used_options:
                continue
            suboptions[index].append(option)
            index = (index + 1) % len(suboptions)
        return suboptions

    def suboptions_enumerate(self, mdp, splitter, used_options):
        assert len(used_options) > 1
        core_suboptions = [[option] for option in used_options]
        other_suboptions = [option for option in mdp.design_space[splitter].options if option not in used_options]
        return core_suboptions, other_suboptions

    def holes_with_max_score(self, hole_scores):
        max_score = max(hole_scores.values())
        # TODO: decomment this after having implemented a proper handling
        # assert max_score > 0
        with_max_score = [hole_index for hole_index in hole_scores if hole_scores[hole_index] == max_score]
        return with_max_score

    def most_inconsistent_holes(self, scheduler_assignment):
        num_definitions = [len(options) for options in scheduler_assignment]
        most_inconsistent = self.holes_with_max_score(num_definitions)
        return most_inconsistent

    def discard(self, mdp, hole_assignments, core_suboptions, other_suboptions):

        # default result
        reduced_design_space = mdp.design_space.copy()
        if len(other_suboptions) == 0:
            suboptions = core_suboptions
        else:
            suboptions = [other_suboptions] + core_suboptions  # DFS solves core first

        if not Synthesizer.incomplete_search:
            return reduced_design_space, suboptions

        # reduce simple holes
        ds_before = reduced_design_space.size
        for hole_index in reduced_design_space.hole_indices:
            if mdp.hole_simple[hole_index]:
                assert len(hole_assignments[hole_index]) == 1
                reduced_design_space.assume_hole_options(hole_index, hole_assignments[hole_index])
        ds_after = reduced_design_space.size
        self.discarded += ds_before - ds_after

        # discard other suboptions
        suboptions = core_suboptions
        # self.discarded += (reduced_design_space.size * len(other_suboptions)) / (len(other_suboptions) + len(core_suboptions))

        return reduced_design_space, suboptions


    def split(self, family):
        Profiler.start("quotient::split")

        mdp = family.mdp
        assert not mdp.is_dtmc

        # split family wrt last undecided result
        result = family.analysis_result.undecided_result()

        hole_assignments = result.primary_selection
        scores = result.primary_scores
        if scores is None:
            scores = {hole:0 for hole in mdp.design_space.hole_indices if len(mdp.design_space[hole].options) > 1}

        splitters = self.holes_with_max_score(scores)
        splitter = splitters[0]
        if len(hole_assignments[splitter]) > 1:
            core_suboptions,other_suboptions = self.suboptions_enumerate(mdp, splitter, hole_assignments[splitter])
        else:
            assert len(mdp.design_space[splitter].options) > 1
            core_suboptions = self.suboptions_half(mdp, splitter)
            other_suboptions = []

        new_design_space, suboptions = self.discard(mdp, hole_assignments, core_suboptions, other_suboptions)

        # construct corresponding design subspaces
        design_subspaces = []

        family.splitters = [splitter]
        parent_info = family.collect_parent_info()
        for suboption in suboptions:
            subholes = new_design_space.subholes(splitter, suboption)
            design_subspace = DesignSpace(subholes, parent_info)
            design_subspace.assume_hole_options(splitter, suboption)
            design_subspaces.append(design_subspace)

        Profiler.resume()
        return design_subspaces


class HyperPropertyQuotientContainer(QuotientContainer):
    def __init__(self, *args):
        super().__init__(*args)

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
        for state in range(self.quotient_mdp.nr_states):

            # skip states without nondeterminism
            num_actions = self.quotient_mdp.get_nr_available_actions(state)
            if num_actions == 1:
                self.action_to_hole_options.append({})
                continue

            # a hole to be created
            hole_name = self.quotient_mdp.state_valuations.get_string(state)
            hole_options = list(range(num_actions))

            # extract labels for each option
            hole_option_labels = []
            for offset in range(num_actions):
                choice = self.quotient_mdp.get_choice_index(state,offset)
                labels = self.quotient_mdp.choice_labeling.get_labels_of_choice(choice)
                hole_option_labels.append(labels)
                self.action_to_hole_options.append({len(holes):offset})

            hole_option_labels = [str(labels) for labels in hole_option_labels]

            hole = Hole(hole_name, hole_options, hole_option_labels)
            holes.append(hole)

        # only now sketch has the corresponding design space
        self.sketch.design_space = DesignSpace(holes)
        self.sketch.design_space.property_indices = self.sketch.specification.all_constraint_indices()

        self.compute_default_actions()
        self.compute_state_to_holes()

    def scheduler_consistent(self, mdp, prop, result, initial_state):
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

        selection, choice_values, expected_visits, scores = self.scheduler_selection_quantitative(mdp, prop, result,
                                                                                                  initial_state)
        #for hole_index in mdp.design_space.hole_indices:
        #    options = selection[hole_index]
            # TODO: do we need this filling of empty selections to deal with non reachable holes?
        #    if options == []:
        #        selection[hole_index] = [mdp.design_space[hole_index].options[0]]

        # for an hyperproperty specification, every scheduler is consistent, hence always return True
        return selection, choice_values, expected_visits, scores, True

    def scheduler_selection_quantitative(self, mdp, prop, result, initial_state):
        '''
        Get hole options involved in the scheduler selection.
        Use numeric values to filter spurious inconsistencies.
        '''
        Profiler.start("quotient::scheduler_selection_quantitative")

        scheduler = result.scheduler

        # get qualitative scheduler selection
        selection = self.scheduler_selection(mdp, scheduler)
        hole_assignments = {hole_index: hole.options for hole_index, hole in enumerate(mdp.design_space) if
                            len(hole.options) > 1}

        # the MDP must not be a MC
        assert len(hole_assignments) > 0

        # extract choice values, compute expected visits and estimate scheduler difference
        choice_values = self.choice_values(mdp, prop, result)
        expected_visits = self.expected_visits(mdp, prop, result.scheduler, initial_state)
        hole_differences = self.estimate_scheduler_difference(mdp, hole_assignments, choice_values,
                                                              expected_visits)

        Profiler.resume()
        return selection, choice_values, expected_visits, hole_differences

    def estimate_scheduler_difference(self, mdp, hole_assignments, choice_values, expected_visits):
        Profiler.start(" estimate scheduler difference")

        # for each hole, compute its difference sum and a number of affected states
        hole_differences = {hole_index: 0 for hole_index in hole_assignments}
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
                    # there isn't a nondeterministic choice associated with this hole
                    continue

                choice_options = self.action_to_hole_options[choice_global]
                # every choice corresponds to choosing one option for one hole, the hole of the state
                hole_index, option = list(choice_options.items())[0]

                if hole_index not in list(hole_assignments.keys()):
                    # we have only possible choice for this state
                    # i.e., this hole has only one hole option
                    # this can happen in subsequent splits
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
            hole_differences[hole_index] = difference
            ranking.sort(key=lambda tup: tup[1])
            options_rankings[hole_index] = [i for i, _ in ranking]

        # filter out unreachable holes, which don't have any option in the ranking
        # but in the current approach we consider only overall reachability in the MDP
        # TODO: handle the case where some holes are not reachable from current initial state
        # i.e., expected visits of the state are zero
        # for example, for PC this holds for all holes from the initial state of the DTMC
        options_rankings = {key: value for key,value in options_rankings.items() if value}
        hole_differences = {key: value for key,value in hole_differences.items() if key in options_rankings}

        # aggregate the results
        hole_differences = (hole_differences, options_rankings)
        Profiler.resume()
        return hole_differences

    # split the options of the best hole according to the scores
    def compute_suboptions(self, scores, options_rankings, primary, splitting_factor=None):
        # compute the hole on which to split
        splitters = self.holes_with_max_score(scores)
        splitter = splitters[0]

        # get the corresponding option for that split, already ordered by choice_value
        options = options_rankings[splitter]

        # splitting_factor(secondary) = 1 - splitting_factor(primary)
        # splitting_factor(primary) > splitting_factor(secondary)
        # i.e., we always try to increase the mc results for the primary selection and decrease them for secondary selection
        # TODO: this works only for prop.minimizing is True
        if splitting_factor is None:
            splitting_factor = 0.80 if primary else 0.20

        chunk_size = math.floor(len(options) * splitting_factor) if primary else math.ceil(len(options) * splitting_factor)
        return options[:chunk_size], options[chunk_size:], splitter

    def split(self, family):
        Profiler.start("quotient::split")

        mdp = family.mdp
        assert not mdp.is_dtmc

        # split family wrt last undecided result
        # TODO: can we use some metrics here as well?
        result = family.analysis_result.undecided_result()

        primary_scores, primary_options_rankings = result.primary_scores
        secondary_scores, secondary_options_rankings = result.secondary_scores

        # fill missing scores
        if primary_scores is None:
            primary_scores = {hole: 0 for hole in mdp.design_space.hole_indices if
                              len(mdp.design_space[hole].options) > 1}
            # we don't want it now
            assert False

        if secondary_scores is None:
            secondary_scores = {hole: 0 for hole in mdp.design_space.hole_indices if
                              len(mdp.design_space[hole].options) > 1}
            # we don't want it now
            assert False

        # compute the holes on which to split,
        # one given by the analysis of the primary_scheduler,
        # one by the analysis of the secondary scheduler
        primary_other_suboptions, primary_core_suboptions, primary_splitter = self.compute_suboptions(primary_scores,
            primary_options_rankings, True)
        secondary_core_suboptions, secondary_other_suboptions, secondary_splitter = self.compute_suboptions(
            secondary_scores, secondary_options_rankings, False)

        # reduced design space
        new_design_space = mdp.design_space.copy()

        # when the best splitter is the same for both selections, then just split halfway on it.
        if primary_splitter == secondary_splitter:
            # split equally on the same hole
            core_suboptions, other_suboptions, unique_splitter = self.compute_suboptions(primary_scores,
                                                                                  primary_options_rankings, True,
                                                                                  splitting_factor=0.5)
            suboptions_list = [core_suboptions, other_suboptions]
            #construct corresponding design subspaces
            design_subspaces = []

            family.splitters = [unique_splitter]
            parent_info = family.collect_parent_info()
            for suboptions in suboptions_list:
                subholes = new_design_space.subholes([(unique_splitter, suboptions)])
                design_subspace = DesignSpace(subholes, parent_info)
                # TODO: do we need this? Isn't it done by subhole method?
                design_subspace.assume_hole_options(unique_splitter, suboptions)
                design_subspaces.append(design_subspace)

            Profiler.resume()
            return design_subspaces

        #generate all subspaces
        primary_suboptions = [primary_other_suboptions, primary_core_suboptions]
        secondary_suboptions = [secondary_other_suboptions, secondary_core_suboptions]
        suboptions_list = [(i,j) for i in primary_suboptions for j in secondary_suboptions]

        # construct corresponding design subspaces
        design_subspaces = []
        family.splitters = [primary_splitter, secondary_splitter]
        parent_info = family.collect_parent_info()
        for (primary_suboptions, secondary_suboptions) in suboptions_list:
            subholes = new_design_space.subholes([(primary_splitter, primary_suboptions), (secondary_splitter, secondary_suboptions)])
            design_subspace = DesignSpace(subholes, parent_info)
            # TODO: do we need this? Isn't it done by subhole method?
            design_subspace.assume_hole_options(primary_splitter, primary_suboptions)
            design_subspace.assume_hole_options(secondary_splitter, secondary_suboptions)
            design_subspaces.append(design_subspace)

        Profiler.resume()

        return design_subspaces
