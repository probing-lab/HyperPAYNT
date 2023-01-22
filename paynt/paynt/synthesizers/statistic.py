from ..profiler import Timer,Profiler

import logging
logger = logging.getLogger(__name__)

# zero approximation to avoid zero division exception
APPROX_ZERO = 0.000001

def safe_division(dividend, divisor):
    """Safe division of dividend by operand
    :param number dividend: upper operand of the division
    :param number divisor: lower operand of the division, may be zero
    :return: safe value after division of approximated zero
    """
    try:
        return dividend / divisor
    except (ZeroDivisionError, ValueError):
        return dividend / APPROX_ZERO
    except OverflowError:
        logger.info(f"Overflow error when computing {dividend} / {divisor}, returning an integer instead of a float")
        return dividend // divisor

class Statistic:
    """General computation stats."""

    # parameters
    status_period = 3
    print_profiling = False

    
    def __init__(self, sketch, synthesizer):
        
        self.synthesizer = synthesizer
        self.sketch = sketch

        self.iterations_dtmc = 0
        self.acc_size_dtmc = 0
        self.avg_size_dtmc = 0

        self.acc_conflicts = [0 for _ in range(sketch.design_space.num_holes +1)]
        self.avg_conflict_size = 0
        self.cegis_sat_members = 0
        self.cegis_unsat_members = 0

        self.iterations_mdp = 0
        self.acc_size_mdp = 0
        self.avg_size_mdp = 0

        self.acc_decided_families = 0
        self.acc_decided_families_size = 0
        self.avg_decided_families_size = 0
        self.ar_unsat_members = 0
        self.ar_sat_members = 0

        self.feasible = None
        self.assignment = None

        self.synthesis_time = Timer()
        self.status_horizon = Statistic.status_period


    def start(self):
        self.synthesis_time.start()

    
    def iteration_dtmc(self, size_dtmc):
        self.iterations_dtmc += 1
        self.acc_size_dtmc += size_dtmc
        self.print_status()

    def iteration_mdp(self, size_mdp):
        self.iterations_mdp += 1
        self.acc_size_mdp += size_mdp
        self.print_status()

    def add_conflict(self, conflict):
        self.acc_conflicts[len(conflict)] += 1

    def add_decided_family(self, family, feasible):
        self.acc_decided_families += 1
        self.acc_decided_families_size += family.size
        if feasible:
            self.ar_sat_members += family.size
        else:
            self.ar_unsat_members += family.size

    def add_dtmc_sat_result(self, sat):
        if sat:
            self.cegis_sat_members += 1
        else:
            self.cegis_unsat_members += 1

    def status(self):
        fraction_rejected = (self.synthesizer.explored + self.synthesizer.sketch.quotient.discarded) / self.sketch.design_space.size
        time_estimate = safe_division(self.synthesis_time.read(), fraction_rejected)
        percentage_rejected = int(fraction_rejected * 1000000) / 10000.0
        # percentage_rejected = fraction_rejected * 100
        time_elapsed = round(self.synthesis_time.read(),1)
        time_estimate = round(time_estimate,1)
        iters = (self.iterations_mdp,self.iterations_dtmc)
        avg_size_mdp = safe_division(self.acc_size_mdp, self.iterations_mdp)
        
        # sat_size = "-"
        # ds = self.synthesizer.sketch.design_space
        # if ds.use_cvc:
        #     sat_size = len(ds.solver.getAssertions())
        # elif ds.use_python_z3:
        #     sat_size = len(ds.solver.assertions())

        return f"> Progress {percentage_rejected}%, elapsed {time_elapsed} s, iters = {iters}"

    def print_status(self):
        if not self.synthesis_time.read() > self.status_horizon:
            return

        if Statistic.print_profiling:
            Profiler.print_all()
        print(self.status(), flush=True)
        self.status_horizon += Statistic.status_period


    def finished(self, assignment):

        self.synthesis_time.stop()
        self.feasible = False
        self.assignment = None
        if assignment is not None:
            self.feasible = True
            self.assignment = str(assignment)

        self.avg_size_dtmc = safe_division(self.acc_size_dtmc, self.iterations_dtmc)
        self.avg_size_mdp = safe_division(self.acc_size_mdp, self.iterations_mdp)
        self.avg_conflict_size = safe_division(sum([i*k for i,k in enumerate(self.acc_conflicts)]), sum(self.acc_conflicts))
        self.avg_decided_families_size = safe_division(self.acc_decided_families_size, self.acc_decided_families)

    def get_summary(self):
        spec = self.sketch.specification
        specification = "\n".join([f"constraint {i + 1}: {str(f)}" for i,f in enumerate(spec.constraints)]) + "\n"
        disjoint_indexes = f" Indexes of formulae in OR relation with each other: {spec.disjoint_indexes}\n"

        fraction_explored = int((self.synthesizer.explored / self.sketch.design_space.size) * 100)
        explored = f"explored: {fraction_explored} %"

        super_quotient_states = self.sketch.quotient.quotient_mdp.nr_states
        super_quotient_actions = self.sketch.quotient.quotient_mdp.nr_choices

        cegis_sat_stats = f"CEGIS Sat members found: {self.cegis_sat_members}, CEGIS Unsat Members found: {self.cegis_unsat_members}"
        ar_sat_stats = f"AR Sat members found: {self.ar_sat_members}, AR Unsat Members found: {self.ar_unsat_members}"

        design_space = f"number of holes: {self.sketch.design_space.num_holes}, family size: {self.sketch.design_space.size}, " \
                       f"super quotient: {super_quotient_states} states / {super_quotient_actions} actions "
        timing = f"method: {self.synthesizer.method_name}, synthesis time: {round(self.synthesis_time.time, 2)} s"

        family_stats = ""
        ar_stats = f"AR stats: avg MDP size: {round(self.avg_size_mdp)}, iterations: {self.iterations_mdp}" \
                   f", decided families: {self.acc_decided_families}, average decided families size: {self.avg_decided_families_size}" \
                   f", {ar_sat_stats}"
        conflict_stats = ";\n".join([ f"{counter} conflicts of size {i}" for i, counter in enumerate (self.acc_conflicts)])
        cegis_stats = f"CEGIS stats: avg DTMC size: {round(self.avg_size_dtmc)}, iterations: {self.iterations_dtmc}" \
                      f", conflicts: {sum(self.acc_conflicts)}, average conflict size: {self.avg_conflict_size}\n" \
                      f"{conflict_stats},\n {cegis_sat_stats}"



        if self.iterations_mdp > 0:
            family_stats += f"{ar_stats}\n"
        if self.iterations_dtmc > 0:
            family_stats += f"{cegis_stats}\n"

        feasible = "yes" if self.feasible else "no"
        result = f"feasible: {feasible}"
        # assignment = f"hole assignment: {str(self.assignment)}\n" if self.assignment else ""
        assignment = ""

        sep = "--------------------\n"
        summary = f"{sep}Synthesis summary\n" \
                f"{specification}{disjoint_indexes}\n{timing}\n{design_space}\n{explored}\n" \
                f"{family_stats}\n{result}\n{assignment}" \
                f"{sep}"
        return summary

    
    def print(self):    
        if Statistic.print_profiling:
            Profiler.print_all()
        print(self.get_summary())
