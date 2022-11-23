import stormpy
from ..sketch.hyperresult import *

from ..sketch.property import Property
from ..profiler import Profiler
from ..sketch.result import ConstraintsResult, MdpPropertyResult, MdpConstraintsResult, SpecificationResult, \
    MdpOptimalityResult, PropertyResult

from ..sketch.holes import DesignSpace


class MarkovChain:

    # options for the construction of chains
    builder_options = None
    # model checking environment (method & precision)
    environment = None

    @classmethod
    def initialize(cls, formulae):
        # builder options
        cls.builder_options = stormpy.BuilderOptions(formulae)
        cls.builder_options.set_build_with_choice_origins(True)
        cls.builder_options.set_build_state_valuations(True)
        cls.builder_options.set_add_overlapping_guards_label()

        # model checking environment
        cls.environment = stormpy.Environment()

        se = cls.environment.solver_environment

        se.set_linear_equation_solver_type(stormpy.EquationSolverType.gmmxx)
        se.minmax_solver_environment.precision = stormpy.Rational(Property.mc_precision)
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.policy_iteration
        se.minmax_solver_environment.method = stormpy.MinMaxMethod.value_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.sound_value_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.interval_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.optimistic_value_iteration
        # se.minmax_solver_environment.method = stormpy.MinMaxMethod.topological

    def __init__(self, model, quotient_container, quotient_state_map, quotient_choice_map):
        Profiler.start("models::MarkovChain")
        if model.labeling.contains_label("overlap_guards"):
            assert model.labeling.get_states("overlap_guards").number_of_set_bits() == 0
        self.model = model
        self.quotient_container = quotient_container
        self.quotient_choice_map = quotient_choice_map
        self.quotient_state_map = quotient_state_map

        # map choices to their origin states
        self.choice_to_state = []
        tm = model.transition_matrix
        for state in range(model.nr_states):
            for choice in range(tm.get_row_group_start(state),tm.get_row_group_end(state)):
                self.choice_to_state.append(state)

        # identify simple holes
        tm = self.model.transition_matrix
        design_space = self.quotient_container.sketch.design_space
        hole_to_states = [0 for hole in design_space]
        for state in range(self.states):
            for hole in quotient_container.state_to_holes[self.quotient_state_map[state]]:
                hole_to_states[hole] += 1
        self.hole_simple = [hole_to_states[hole] == 1 for hole in design_space.hole_indices]

        self.analysis_hints = None
        Profiler.resume()

    @property
    def states(self):
        return self.model.nr_states

    @property
    def choices(self):
        return self.model.nr_choices

    @property
    def is_dtmc(self):
        return self.model.nr_choices == self.model.nr_states

    @property
    def initial_states(self):
        return self.model.initial_states

    def model_check_formula(self, formula):
        result = stormpy.model_checking(
            self.model, formula, only_initial_states=False,
            extract_scheduler=(not self.is_dtmc),
            # extract_scheduler=True,
            environment=self.environment
        )
        assert result is not None
        return result

    def model_check_formula_hint(self, formula, hint):
        stormpy.synthesis.set_loglevel_off()
        task = stormpy.core.CheckTask(formula, only_initial_states=False)
        task.set_produce_schedulers(produce_schedulers=True)
        result = stormpy.synthesis.model_check_with_hint(self.model, task, self.environment, hint)
        return result

    def model_check_property(self, prop, alt=False):
        direction = "prim" if not alt else "seco"
        Profiler.start(f"  MC {direction}")
        # get hint
        hint = None
        if self.analysis_hints is not None:
            hint_prim, hint_seco = self.analysis_hints[prop]
            hint = hint_prim if not alt else hint_seco
            # hint = self.analysis_hints[prop]

        formula = prop.formula if not alt else prop.formula_alt
        if hint is None:
            result = self.model_check_formula(formula)
        else:
            result = self.model_check_formula_hint(formula, hint)

        value = result.at(prop.state)
        Profiler.resume()
        return PropertyResult(prop, result, value)

    def model_check_hyperproperty(self, prop, alt=False):
        direction = "prim" if not alt else "seco"
        Profiler.start(f"  MC {direction}")
        # get hint
        hint = None
        if self.analysis_hints is not None:
            hint_prim,hint_seco = self.analysis_hints[prop]
            hint = hint_prim if not alt else hint_seco
            # hint = self.analysis_hints[prop]

        formula = prop.formula if not alt else prop.formula_alt
        formula_alt = prop.formula_alt if not alt else prop.formula
        if hint is None:
            result = self.model_check_formula(formula)
            result_alt = self.model_check_formula(formula_alt)
        else:
            result = self.model_check_formula_hint(formula, hint)
            result_alt = self.model_check_formula_hint(formula_alt, hint)

        Profiler.resume()
        return HyperPropertyResult(prop, result, result_alt)

    def model_check_scheduler_difference(self, prop, family, alt=False):
        diff_count = 0

        # TODO: rewrite this in functional style
        min = prop.minimizing if not alt else not prop.minimizing
        for matching_holes_indexes in DesignSpace.matching_hole_indexes:
            if min:
                diff_count = diff_count + 1 if set.isdisjoint \
                    (*map(lambda x: set(family[x].options), matching_holes_indexes)) else diff_count
            else:
                raise NotImplementedError("Implement me, Mario!")
                # TODO: this code is wrong and needs to be refactored according to the definition of maximal difference
                # diff_count = diff_count + 1 if not set.symmetric_difference \
                # (*map(lambda x: set(family[x].options), matching_holes_indexes)) else diff_count
        return SchedulerOptimalityHyperPropertyResult(prop, diff_count)


class DTMC(MarkovChain):

    def check_constraints(self, properties, property_indices=None, short_evaluation=False):
        '''
        Check constraints.
        :param properties a list of all constraints
        :param property_indices a selection of property indices to investigate
        :param short_evaluation if set to True, then evaluation terminates as
          soon as a constraint is not satisfied
        '''

        # implicitly, check all constraints
        if property_indices is None:
            property_indices = [index for index, _ in enumerate(properties)]

        # check selected properties
        results = [None for prop in properties]
        for index in property_indices:
            prop = properties[index]
            result = self.model_check_property(prop)
            results[index] = result
            if short_evaluation and not result.sat:
                break

        return ConstraintsResult(results)

    def check_specification(self, specification, property_indices=None, short_evaluation=False):
        constraints_result = self.check_constraints(specification.constraints, property_indices, short_evaluation)
        optimality_result = None
        if specification.has_optimality and not (short_evaluation and not constraints_result.all_sat):
            optimality_result = self.model_check_property(specification.optimality)
        return SpecificationResult(constraints_result, optimality_result)

    def check_hyperconstraints(self, properties, property_indices=None, short_evaluation=False):
        '''
        Check constraints.
        :param properties a list of all constraints
        :param property_indices a selection of property indices to investigate
        :param short_evaluation if set to True, then evaluation terminates as
          soon as a constraint is not satisfied
        '''

        # implicitly, check all constraints
        if property_indices is None:
            property_indices = [index for index,_ in enumerate(properties)]

        results = [None for prop in properties]
        grouped = HyperSpecification.or_group_indexes(property_indices)
        for group in grouped:
            if not group:
                continue
            unsat = True
            for index in group:
                prop = properties[index]
                result = self.model_check_hyperproperty(prop)
                results[index] = result
                unsat = False if result.sat is not False else unsat
            if short_evaluation and unsat:
                return HyperConstraintsResult(results)
        return HyperConstraintsResult(results)

    def check_hyperspecification(self, hyperspecification, assignment, property_indices=None, short_evaluation=False):

        # check the constraints
        # TODO: this method should discover itself if the property is an hyperproperty or not
        constraints_result = self.check_hyperconstraints(hyperspecification.constraints, property_indices, short_evaluation)

        # for now, we only have PCTL/rew optimality constraints
        # TODO: implement optimal hyperproperties
        optimality_result = None
        if hyperspecification.has_optimality and not (short_evaluation and not constraints_result.all_sat):
            optimality_result = self.model_check_property(hyperspecification.optimality)

        sched_hyper_optimality_result = None
        if hyperspecification.has_scheduler_hyperoptimality and not (short_evaluation and not constraints_result.all_sat):
            assert assignment.size == 1
            sched_hyper_optimality_result = self.model_check_scheduler_difference(hyperspecification.sched_hyperoptimality, assignment)

        return HyperSpecificationResult(constraints_result, optimality_result, sched_hyper_optimality_result)

class MDP(MarkovChain):

    # whether the secondary direction will be explored if primary is not enough
    compute_secondary_direction = False

    def __init__(self, model, quotient_container, quotient_state_map, quotient_choice_map, design_space):
        super().__init__(model, quotient_container, quotient_state_map, quotient_choice_map)

        self.design_space = design_space
        self.analysis_hints = None
        self.quotient_to_restricted_action_map = None

    def check_property(self, prop):

        # check primary direction
        primary = self.model_check_property(prop, alt=False)

        # no need to check secondary direction if primary direction yields UNSAT
        if not primary.sat:
            return MdpPropertyResult(prop, primary, None, False, None, None, None, None)

        # primary direction is SAT
        # check if the primary scheduler is consistent
        selection, choice_values, expected_visits, scores, consistent = self.quotient_container.scheduler_consistent(
            self, prop, primary.result)

        # regardless of whether it is consistent or not, we compute secondary direction to show that all SAT

        # compute secondary direction
        secondary = self.model_check_property(prop, alt=True)
        if self.is_dtmc and primary.value != secondary.value:
            dtmc = self.quotient_container.mdp_to_dtmc(self.model)
            result = stormpy.model_checking(
                dtmc, prop.formula, only_initial_states=False,
                extract_scheduler=(not self.is_dtmc),
                # extract_scheduler=True,
                environment=self.environment
            )
            assert False

        feasibility = True if secondary.sat else None
        return MdpPropertyResult(prop, primary, secondary, feasibility, selection, choice_values, expected_visits,
                                 scores)

    def check_constraints(self, properties, property_indices = None, short_evaluation = False):
        if property_indices is None:
            property_indices = [index for index,_ in enumerate(properties)]

        results = [None for prop in properties]
        for index in property_indices:
            prop = properties[index]
            result = self.check_property(prop)
            results[index] = result
            if short_evaluation and result.feasibility == False:
                break

        return MdpConstraintsResult(results)

    def check_optimality(self, prop):
        # check primary direction
        primary = self.model_check_property(prop, alt = False)

        if not primary.improves_optimum:
            # OPT <= LB
            return MdpOptimalityResult(prop, primary, None, None, None, False, None, None, None, None)

        # LB < OPT
        # check if LB is tight
        selection,choice_values,expected_visits,scores,consistent = self.quotient_container.scheduler_consistent(self, prop, primary.result)
        if consistent:
            # LB is tight and LB < OPT
            scheduler_assignment = self.design_space.copy()
            scheduler_assignment.assume_options(selection)
            improving_assignment, improving_value = self.quotient_container.double_check_assignment(scheduler_assignment)
            return MdpOptimalityResult(prop, primary, None, improving_assignment, improving_value, False, selection, choice_values, expected_visits, scores)

        if not MDP.compute_secondary_direction:
            return MdpOptimalityResult(prop, primary, None, None, None, True, selection, choice_values, expected_visits, scores)

        # UB might improve the optimum
        secondary = self.model_check_property(prop, alt = True)

        if not secondary.improves_optimum:
            # LB < OPT < UB :  T < LB < OPT < UB (cannot improve) or LB < T < OPT < UB (can improve)
            can_improve = primary.sat
            return MdpOptimalityResult(prop, primary, secondary, None, None, can_improve, selection, choice_values, expected_visits, scores)

        # LB < UB < OPT
        # this family definitely improves the optimum
        assignment = self.design_space.pick_any()
        improving_assignment, improving_value = self.quotient_container.double_check_assignment(assignment, prop)
        # either LB < T, LB < UB < OPT (can improve) or T < LB < UB < OPT (cannot improve)
        can_improve = primary.sat
        return MdpOptimalityResult(prop, primary, secondary, improving_assignment, improving_value, can_improve, selection, choice_values, scores)

    def check_specification(self, specification, property_indices = None, short_evaluation = False):
        constraints_result = self.check_constraints(specification.constraints, property_indices, short_evaluation)
        optimality_result = None
        if specification.has_optimality and not (short_evaluation and constraints_result.feasibility == False):
            optimality_result = self.check_optimality(specification.optimality)
        return SpecificationResult(constraints_result, optimality_result)

    def check_hyperproperty(self, prop):

        # check primary direction
        primary = self.model_check_hyperproperty(prop, alt = False)

        # no need to check secondary direction if primary direction yields UNSAT
        if not primary.sat:
            return MdpHyperPropertyResult(prop, primary, None, False, None, False, None, None, None, None, None, None, None)

        # primary direction is SAT
        # check secondary direction to show that all SAT
        # TODO: this does not work if we have a multi targets comparison
        secondary = HyperPropertyResult(prop, primary.result_alt, primary.result)
        feasibility = True if secondary.sat else None

        if feasibility:
            # no need to explore further
            # we are not constraining at all the primary selection
            primary_selection = [ [] for hole_index in self.design_space.hole_indices]
            return MdpHyperPropertyResult(prop, primary, secondary, feasibility, primary_selection, True, None,
                                          None, None, None, None, None, None)

        # check if primary scheduler (of state quant) induces a feasible scheduler
        value = primary.value
        threshold = secondary.threshold
        primary_feasibility = prop.meets_op(value, threshold)

        # prepare for splitting on this property
        # TODO: implement the betting strategy here
        unsat_bet = True
        state = prop.state if unsat_bet else prop.other_state
        other_state = prop.other_state if unsat_bet else prop.state
        # compute the scores for splitting
        primary_selection, primary_choice_values, primary_expected_visits, primary_scores, _ = self.quotient_container.scheduler_consistent(
            self, prop, primary.result, state)

        secondary_selection, secondary_choice_values, secondary_expected_visits, secondary_scores, _ = self.quotient_container.scheduler_consistent(
            self, prop, primary.result_alt, other_state)

        return MdpHyperPropertyResult(prop, primary, secondary, feasibility, primary_selection, primary_feasibility,
                                      primary_choice_values, primary_expected_visits, primary_scores, secondary_selection,
                                      secondary_choice_values, secondary_expected_visits, secondary_scores)

    def check_hyperconstraints(self, properties, property_indices=None, short_evaluation=False):
        if property_indices is None:
            property_indices = [index for index, _ in enumerate(properties)]

        results = [None for prop in properties]
        grouped = HyperSpecification.or_group_indexes(property_indices)
        for group in grouped:
            if not group:
                continue
            unfeasible = True
            for index in group:
                prop = properties[index]
                result = self.check_hyperproperty(prop)
                results[index] = result
                unfeasible = False if result.feasibility is not False else unfeasible
            if short_evaluation and unfeasible:
                return MdpHyperConstraintsResult(results)
        # TODO: check that, if there are no constraints, this object will have attribute sat == true
        return MdpHyperConstraintsResult(results)

    # TODO: implement Optimal HyperProperties
    def check_hyperoptimality(self, prop):
        raise NotImplementedError("implement me, Mario!")

    def check_scheduler_hyperoptimality(self, prop):

        # check primary direction
        primary = self.model_check_scheduler_difference(prop, self.design_space, alt=False)

        if not primary.improves_hyperoptimum:
            # OPT <= LB
            return MdpSchedulerOptimalityHyperPropertyResult(prop, primary, None, None, False)

        # LB < OPT
        scheduler_assignment = self.design_space.copy()
        scheduler_assignment.assume_optimizing_options(prop.minimizing)

        # check again if the value improves the optimum a
        improving_assignment, improving_value = self.quotient_container.double_check_assignment_scheduler_hyperoptimality(
            scheduler_assignment)

        can_improve = False if improving_assignment is not None else True

        return MdpSchedulerOptimalityHyperPropertyResult(prop, primary, improving_assignment, improving_value, can_improve)

    def check_hyperspecification(self, hyperspec, property_indices=None, short_evaluation=False):
        constraints_result = self.check_hyperconstraints(hyperspec.constraints, property_indices, short_evaluation)

        optimality_result = None
        if hyperspec.has_optimality and not (short_evaluation and constraints_result.feasibility is False):
            optimality_result = self.model_check_property(hyperspec.optimality)

        sched_hyper_optimality_result = None
        if hyperspec.has_scheduler_hyperoptimality and not (
                short_evaluation and constraints_result.feasibility is False):
            sched_hyper_optimality_result = self.check_scheduler_hyperoptimality(
                hyperspec.sched_hyperoptimality)

        return HyperSpecificationResult(constraints_result, optimality_result, sched_hyper_optimality_result)
