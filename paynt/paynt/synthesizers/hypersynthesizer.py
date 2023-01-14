import stormpy.synthesis

from .statistic import Statistic
from ..profiler import Timer, Profiler

from ..hypersketch.hyperproperty import HyperSpecification

import logging

logger = logging.getLogger(__name__)


class HyperSynthesizer:
    # if True, some subfamilies can be discarded and some holes can be generalized
    incomplete_search = False

    # synthesis escape criterion
    use_optimum_update_timeout = False
    optimum_update_iters_limit = 100000

    def __init__(self, sketch):
        self.sketch = sketch
        self.stat = Statistic(sketch, self)
        self.explored = 0

        self.since_last_optimum_update = 0

    @property
    def method_name(self):
        ''' to be overridden '''
        pass

    def synthesize(self, family, explore_all):
        ''' to be overridden '''
        pass

    def print_stats(self):
        self.stat.print()

    def run(self, explore_all):
        assignment = self.synthesize(self.sketch.design_space, explore_all)

        logger.info("Printing synthesized assignment below:")
        logger.info(";\n".join(str(assignment).split(",")))

        if assignment is not None:
            dtmc = self.sketch.quotient.build_chain(assignment)
            spec = dtmc.check_hyperspecification(self.sketch.specification, assignment)
            logger.info("Double-checking specification satisfiability:\n{}".format(spec))

        self.print_stats()

    def explore(self, family):
        self.explored += family.size
        fraction_explored = int((family.size / self.sketch.design_space.size) * 100)
        if fraction_explored > 1:
            logger.info(f"Pruned a non negligible family which represents the {fraction_explored}% of the design space")

    def no_optimum_update_limit_reached(self):
        self.since_last_optimum_update += 1
        return HyperSynthesizer.use_optimum_update_timeout and self.since_last_optimum_update > HyperSynthesizer.optimum_update_iters_limit


class HyperSynthesizer1By1(HyperSynthesizer):

    @property
    def method_name(self):
        return "1-by-1"

    def synthesize(self, family, explore_all):

        logger.info("Synthesis initiated.")

        Profiler.start("synthesis")
        self.stat.start()

        satisfying_assignment = None
        for hole_combination in family.all_combinations():

            assignment = family.construct_assignment(hole_combination)
            chain = self.sketch.quotient.build_chain(assignment)
            #self.stat.iteration_dtmc(chain.states)
            result = chain.check_hyperspecification(self.sketch.specification, assignment, short_evaluation=True)
            self.stat.add_dtmc_sat_result(result.constraints_result.all_sat)
            if not result.constraints_result.all_sat:
                continue

            # TODO: implement some other checks here for other sorts of optimality properties
            if not self.sketch.specification.has_scheduler_hyperoptimality and not explore_all:
                satisfying_assignment = assignment
                break

            if result.sched_hyperoptimality_result.improves_hyperoptimum:
                self.sketch.specification.sched_hyperoptimality.update_hyperoptimum(result.sched_hyperoptimality_result.value)
                satisfying_assignment = assignment


        self.stat.finished(satisfying_assignment)
        Profiler.stop()
        return satisfying_assignment


class HyperSynthesizerAR(HyperSynthesizer):
    # family exploration order: True = DFS, False = BFS
    exploration_order_dfs = True

    @property
    def method_name(self):
        return "AR"

    def analyze_family_ar(self, family):
        """
        :return (1) family feasibility (True/False/None)
        :return (2) new satisfying assignment (or None)
        """
        # logger.debug("analyzing family {}".format(family))
        Profiler.start("synthesizer::analyze_family_ar")

        self.sketch.quotient.build(family)
        self.stat.iteration_mdp(family.mdp.states)

        res = family.mdp.check_hyperspecification(self.sketch.specification,
                                                property_indices=family.property_indices, short_evaluation=True)
        family.analysis_result = res
        Profiler.resume()

        improving_assignment, improving_value, can_improve = res.improving(family)
        if improving_value is not None:
            self.sketch.specification.update_optimum(improving_value)
            self.since_last_optimum_update = 0

        return can_improve, improving_assignment

    def synthesize(self, family, explore_all):

        logger.info("Synthesis initiated.")

        Profiler.start("synthesis")
        self.stat.start()

        self.sketch.quotient.discarded = 0

        satisfying_assignment = None
        families = [family]
        while families:

            if self.no_optimum_update_limit_reached():
                break

            if HyperSynthesizerAR.exploration_order_dfs:
                family = families.pop(-1)
            else:
                family = families.pop(0)

            can_improve, improving_assignment = self.analyze_family_ar(family)
            if improving_assignment is not None:
                satisfying_assignment = improving_assignment
                if not explore_all:
                    break
            if can_improve is False:
                self.stat.add_decided_family(family, improving_assignment is not None)
                self.explore(family)
                continue

            # undecided
            subfamilies = self.sketch.quotient.split(family)
            families = families + subfamilies

        self.stat.finished(satisfying_assignment)
        Profiler.stop()
        return satisfying_assignment


class HyperSynthesizerCEGIS(HyperSynthesizer):

    @property
    def method_name(self):
        return "CEGIS"

    def generalize_conflict(self, assignment, conflict, scheduler_selection):

        if not HyperSynthesizer.incomplete_search:
            return conflict

        # filter holes set to consistent assignment
        conflict_filtered = []
        for hole in conflict:
            scheduler_options = scheduler_selection[hole]
            # if len(scheduler_options) == 1 and assignment[hole].options[0] == scheduler_options[0]:
            if len(scheduler_options) == 1:
                continue
            conflict_filtered.append(hole)

        return conflict_filtered

    def analyze_family_assignment_cegis(self, family, assignment, ce_generator):
        """
        :return (1) specification satisfiability (True/False)
        :return (2) whether this is an improving assignment
        """

        assert family.mdp is not None, "analyzed family does not have an associated quotient MPD"

        Profiler.start("CEGIS analysis")
        # print(assignment)

        # build DTMC
        dtmc = self.sketch.quotient.build_chain(assignment)
        self.stat.iteration_dtmc(dtmc.states)

        # model check all properties
        spec = dtmc.check_hyperspecification(self.sketch.specification, assignment,
                                           property_indices=family.property_indices, short_evaluation=False)

        # analyze model checking results
        improving = False
        if spec.constraints_result.all_sat:
            if not self.sketch.specification.has_optimality:
                Profiler.resume()
                return True, True
            if spec.optimality_result is not None and spec.optimality_result.improves_optimum:
                self.sketch.specification.optimality.update_optimum(spec.optimality_result.value)
                self.since_last_optimum_update = 0
                improving = True

        # construct conflict wrt each unsatisfiable property
        # pack all unsatisfiable properties as well as their MDP results (if exists)
        conflict_requests = {}
        for index in family.property_indices:
            if spec.constraints_result.isSat(index):
                continue
            prop = self.sketch.specification.constraints[index]
            property_result = family.analysis_result.constraints_result.results[index] if family.analysis_result is not None else None
            conflict_requests[index] = (prop, property_result)

        # group the conflicts based on the disjunctions
        grouped = HyperSpecification.or_group_dict(conflict_requests)

        if self.sketch.specification.has_optimality:
            index = len(self.sketch.specification.constraints)
            prop = self.sketch.specification.optimality
            property_result = family.analysis_result.optimality_result if family.analysis_result is not None else None
            grouped.append([(index, (prop, property_result))])

        # construct conflict to each unsatisfiable property
        conflicts = []
        for group in grouped:
            if not group:
                continue
            overall_conflict = []
            scheduler_selection = None
            for request in group:
                (index, (prop, property_result)) = request

                state_quant = prop.state
                other_state_quant = prop.other_state

                # prepare DTMC for CE generation
                ce_generator.prepare_dtmc(dtmc.model, dtmc.quotient_state_map, state_quant, other_state_quant)

                bounds = None
                other_bounds = None
                if property_result is not None:
                    bounds = property_result.primary.result
                    other_bounds = property_result.secondary.result
                    scheduler_selection = property_result.primary_selection

                Profiler.start("storm::construct_conflict")
                conflict = ce_generator.construct_conflict(index, bounds, other_bounds, family.mdp.quotient_state_map,
                                                           state_quant, other_state_quant, prop.strict)

                overall_conflict = list(set(overall_conflict + conflict))

                Profiler.resume()
            overall_conflict = self.generalize_conflict(assignment, overall_conflict, scheduler_selection)
            conflicts.append(overall_conflict)


        # use conflicts to exclude the generalizations of this assignment
        Profiler.start("holes::exclude_assignment")
        for conflict in conflicts:
            self.stat.add_conflict(conflict)
            family.exclude_assignment(assignment, conflict)

        Profiler.resume()
        return False, False

    def synthesize(self, family, explore_all):

        logger.info("Synthesis initiated.")

        Profiler.start("synthesis")
        self.stat.start()

        # assert that there is no reward formula
        msg = "Cannot use CEGIS for reward hyper formulae, as CEGIS cannot handle the maximization RHS -- consider using AR or hybrid methods."
        for c in self.sketch.specification.constraints:
            assert not c.reward, msg
        if self.sketch.specification.has_optimality:
            c = self.sketch.specification.optimality
            assert not c.reward, msg

        # build the quotient, map mdp states to hole indices
        self.sketch.quotient.build(family)
        self.sketch.quotient.compute_state_to_holes()
        quotient_relevant_holes = self.sketch.quotient.state_to_holes

        # initialize CE generator
        formulae = self.sketch.specification.stormpy_formulae()
        ce_generator = stormpy.synthesis.CounterexampleGenerator(
            self.sketch.quotient.quotient_mdp, self.sketch.design_space.num_holes,
            quotient_relevant_holes, formulae)

        # use sketch design space as a SAT baseline
        self.sketch.design_space.sat_initialize()

        # CEGIS loop
        satisfying_assignment = None
        assignment = family.pick_assignment()
        while assignment is not None:

            sat, improving = self.analyze_family_assignment_cegis(family, assignment, ce_generator)
            if improving:
                satisfying_assignment = assignment
            if sat:
                if not explore_all:
                    break
                else:
                    family.exclude_assignment(assignment, [i for i in range(len(assignment))])
            self.stat.add_dtmc_sat_result(sat)
            # construct next assignment
            assignment = family.pick_assignment()

        self.stat.finished(satisfying_assignment)
        Profiler.stop()
        return satisfying_assignment


# ----- AR-CEGIS adaptivity ----- #
# idea: switch between ar/cegis, allocate more time to the more efficient method

class StageControl:
    # whether only AR is performed
    only_ar = False
    # whether 1 AR followed by only CEGIS is performed
    only_cegis = False

    def __init__(self):
        # timings
        self.timer_ar = Timer()
        self.timer_cegis = Timer()

        # multiplier to derive time allocated for cegis
        # time_ar * factor = time_cegis
        # =1 is fair, >1 favours cegis, <1 favours ar
        self.cegis_efficiency = 1

    def start_ar(self):
        self.timer_cegis.stop()
        self.timer_ar.start()

    def start_cegis(self):
        self.timer_ar.stop()
        self.timer_cegis.start()

    def cegis_has_time(self):
        """
        :return True if cegis still has some time
        """

        # whether only AR is performed
        if StageControl.only_ar:
            return False

        # whether only CEGIS is performed
        if StageControl.only_cegis:
            return True

        # whether CEGIS has more time
        if self.timer_cegis.read() < self.timer_ar.read() * self.cegis_efficiency:
            return True

        # stop CEGIS
        self.timer_cegis.stop()
        return False


class SynthesizerHybrid(HyperSynthesizerAR, HyperSynthesizerCEGIS):

    @property
    def method_name(self):
        return "hybrid"

    def synthesize(self, family, explore_all):

        logger.info("Synthesis initiated.")

        Profiler.start("synthesis")
        self.stat.start()

        self.sketch.quotient.discarded = 0

        self.stage_control = StageControl()

        quotient_relevant_holes = self.sketch.quotient.state_to_holes
        formulae = self.sketch.specification.stormpy_formulae()
        ce_generator = stormpy.synthesis.CounterexampleGenerator(
            self.sketch.quotient.quotient_mdp, self.sketch.design_space.num_holes,
            quotient_relevant_holes, formulae)

        # use sketch design space as a SAT baseline
        self.sketch.design_space.sat_initialize()

        # AR loop
        satisfying_assignment = None
        families = [family]
        while families:

            if self.no_optimum_update_limit_reached():
                break

            # initiate AR analysis
            self.stage_control.start_ar()

            # choose family
            if HyperSynthesizerAR.exploration_order_dfs:
                family = families.pop(-1)
            else:
                family = families.pop(0)

            # reset SMT solver level
            if HyperSynthesizerAR.exploration_order_dfs:
                family.sat_level()

            # analyze the family
            can_improve, improving_assignment = self.analyze_family_ar(family)
            if improving_assignment is not None:
                satisfying_assignment = improving_assignment
                if not explore_all:
                    break
            if can_improve == False:
                self.stat.add_decided_family(family, improving_assignment is not None)
                self.explore(family)
                continue

            # undecided: initiate CEGIS analysis
            self.stage_control.start_cegis()

            # construct priority subfamily that corresponds to primary scheduler
            # scheduler_selection = family.analysis_result.optimality_result.primary_selection
            # priority_subfamily = family.copy()
            # priority_subfamily.assume_options(scheduler_selection)

            # explore family assignments
            sat = False
            while True:

                if not self.stage_control.cegis_has_time():
                    # CEGIS timeout
                    break

                # pick assignment
                assignment = family.pick_assignment_priority(None)
                if assignment is None:
                    break

                # analyze this assignment
                sat, improving = self.analyze_family_assignment_cegis(family, assignment, ce_generator)
                if improving:
                    satisfying_assignment = assignment
                if sat:
                    if not explore_all:
                        break
                    else:
                        family.exclude_assignment(assignment, [i for i in range(len(assignment))])

                self.stat.add_dtmc_sat_result(sat)
                # move on to the next assignment

            if sat and not explore_all:
                break

            if not family.has_assignments:
                self.stat.add_decided_family(family, False)
                self.explore(family)
                continue
            subfamilies = self.sketch.quotient.split(family)
            families = families + subfamilies

        # ce_generator.print_profiling()

        self.stat.finished(satisfying_assignment)
        Profiler.stop()
        return satisfying_assignment
