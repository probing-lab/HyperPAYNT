import stormpy

from ..sketch.property import *
from ..profiler import Profiler

from collections import OrderedDict

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
    def initial_state(self):
        return self.model.initial_states[0]

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

    def model_check_property(self, prop, alt = False):
        Profiler.start(f"  MC {alt}")
        # get hint
        hint = None
        if self.analysis_hints is not None:
            hint_prim,hint_seco = self.analysis_hints[prop]
            hint = hint_prim if not alt else hint_seco
            # hint = self.analysis_hints[prop]

        formula = prop.formula if not alt else prop.formula_alt
        if hint is None:
            result = self.model_check_formula(formula)
        else:
            result = self.model_check_formula_hint(formula, hint)
        value = result.at(self.initial_state)
        Profiler.resume()
        return PropertyResult(prop, result, value)


class DTMC(MarkovChain):

    def check_constraints(self, properties, property_indices = None, short_evaluation = False):
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
        
        # check selected properties
        results = [None for prop in properties]
        for index in property_indices:
            prop = properties[index]
            result = self.model_check_property(prop)
            results[index] = result
            if short_evaluation and not result.sat:
                break

        return ConstraintsResult(results)

    def check_specification(self, specification, property_indices = None, short_evaluation = False):
        constraints_result = self.check_constraints(specification.constraints, property_indices, short_evaluation)
        optimality_result = None
        if specification.has_optimality and not (short_evaluation and not constraints_result.all_sat):
            optimality_result = self.model_check_property(specification.optimality)
        return SpecificationResult(constraints_result, optimality_result)



class MDP(MarkovChain):

    def __init__(self, model, quotient_container, quotient_state_map, quotient_choice_map, design_space):
        super().__init__(model, quotient_container, quotient_state_map, quotient_choice_map)

        self.design_space = design_space
        self.scheduler_results = OrderedDict()
        self.analysis_hints = None

    def check_property(self, prop):
        # check primary direction
        primary = self.model_check_property(prop, alt = False)
        
        # no need to check secondary direction if primary direction yields UNSAT
        if not primary.sat:
            return MdpPropertyResult(prop, primary, None, False)

        # primary direction is SAT
        # check if the primary scheduler is consistent
        consistent = True
        if not self.is_dtmc:
            assignment,scores,consistent = self.quotient_container.scheduler_consistent(self, prop, primary.result)
            if not consistent:
                self.scheduler_results[prop] = (assignment,scores)
        
        # primary scheduler is sufficient
        if consistent:
            return MdpPropertyResult(prop, primary, None, True)
        
        # primary direction is not sufficient
        secondary = self.model_check_property(prop, alt = True)
        feasibility = True if secondary.sat else None
        return MdpPropertyResult(prop, primary, secondary, feasibility)

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

        # def __init__(self, prop, primary, secondary, improving_assignment, can_improve):
        
        if not primary.improves_optimum:
            # OPT <= LB
            return MdpOptimalityResult(prop, primary, None, None, False)

        # LB < OPT
        # check if LB is tight

        selection = None
        if self.is_dtmc:
            consistent = True
        else:
            selection,scores,consistent = self.quotient_container.scheduler_consistent(self, prop, primary.result)
        
        if consistent:
            if selection is None:
                assignment = self.design_space.pick_any()
            else:
                assignment = self.design_space.copy()
                assignment.assume_options(selection)

            # LB is tight and LB < OPT
            improving_assignment = self.quotient_container.double_check_assignment(assignment, prop)
            return MdpOptimalityResult(prop, primary, None, improving_assignment, False)

        # UB might improve the optimum
        secondary = self.model_check_property(prop, alt = True)

        if not secondary.improves_optimum:
            # LB < OPT < UB
            if not primary.sat:
                # T < LB < OPT < UB
                return MdpOptimalityResult(prop, primary, secondary, None, False)
            else:
                # LB < T < OPT < UB
                self.scheduler_results[prop] = (selection,scores)
                return MdpOptimalityResult(prop, primary, secondary, None, True)

        # LB < UB < OPT
        # this family definitely improves the optimum
        assignment = self.design_space.pick_any()
        improving_assignment = self.quotient_container.double_check_assignment(assignment, prop)
        if not primary.sat:
            # T < LB < UB < OPT
            return MdpOptimalityResult(prop, primary, secondary, improving_assignment, False)
        else:
            # LB < T, LB < UB < OPT
            self.scheduler_results[prop] = (selection,scores)
            return MdpOptimalityResult(prop, primary, secondary, improving_assignment, True)


    def check_specification(self, specification, property_indices = None, short_evaluation = False):
        constraints_result = self.check_constraints(specification.constraints, property_indices, short_evaluation)
        optimality_result = None
        if specification.has_optimality and not (short_evaluation and constraints_result.feasibility == False):
            optimality_result = self.check_optimality(specification.optimality)
        return SpecificationResult(constraints_result, optimality_result)
