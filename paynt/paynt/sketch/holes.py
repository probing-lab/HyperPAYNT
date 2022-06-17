import math
import itertools

import z3

from ..profiler import Profiler

import logging

logger = logging.getLogger(__name__)


class Hole:
    '''
    Hole with a name and a list of options. Each hole correspond to a state with a nondeterministic
    choice in the MDP, and each option corresponds to the choice of an available action in the MDP.
    This choice resolves thus the nondeterminism.

    The name of a hole is the name of the corresponding state.

    Each hole is identified by its position hole_index in Holes, therefore,
      this order must be preserved in the refining process.
    '''

    def __init__(self, name, options, original_size=None):
        self.name = name
        self.options = options
        if original_size is not None:
            self.original_size = original_size
        else:
            self.original_size = original_size

    @property
    def size(self):
        return len(self.options)

    @property
    def is_trivial(self):
        return self.size == 1

    @property
    def is_unrefined(self):
        return self.size == self.original_size

    def __str__(self):
        if self.size == 1:
            return "{}={}".format(self.name, self.options[0])
        else:
            return self.name + ": {" + ",".join(self.options) + "}"

    def assume_options(self, options):
        assert len(options) > 0
        self.options = options

    def copy(self):
        # TODO: is this true? I'm not an expert of Python pass-by-reference or pass-by-value rules
        # note that the copy is shallow, but after assuming some options
        # the options pointer points to the new list, hence the original hole is not modified.
        return Hole(self.name, self.options, self.original_size)


class Holes(list):
    ''' List of holes. '''

    def __init__(self, *args):
        super().__init__(*args)

    @property
    def num_holes(self):
        return len(self)

    @property
    def hole_indices(self):
        return list(range(len(self)))

    @property
    def size(self):
        ''' Family size. '''
        return math.prod([hole.size for hole in self])

    def __str__(self):
        return ", ".join([str(hole) for hole in self])

    def copy(self):
        ''' Create a shallow copy of this list of holes. '''
        return Holes([hole.copy() for hole in self])

    def assume_hole_options(self, hole_index, options):
        ''' Assume suboptions of a certain hole. '''
        self[hole_index].assume_options(options)

    # param: a dictionary hole-index : list of options to assume.
    def assume_options(self, hole_options):
        ''' Assume suboptions for each hole. '''
        for hole_index, hole in enumerate(self):
            hole.assume_options(hole_options[hole_index])

    def pick_any(self):
        suboptions = [[hole.options[0]] for hole in self]
        holes = self.copy()
        holes.assume_options(suboptions)
        return holes

    def includes(self, hole_assignment):
        '''
        :return True if this family contains hole_assignment
        '''
        for hole_index, option in hole_assignment.items():
            if not option in self[hole_index].options:
                return False
        return True

    def all_combinations(self):
        '''
        :return iteratable Cartesian product of hole options
        '''
        return itertools.product(*[hole.options for hole in self])

    def construct_assignment(self, combination):
        ''' Convert hole option combination to a hole assignment. '''
        combination = list(combination)
        suboptions = [[option] for option in combination]
        holes = self.copy()
        holes.assume_options(suboptions)
        return holes

    #TODO: do we need this?
    def subholes(self, hole_index, options):
        '''
        Construct a semi-shallow copy of self with only one modified hole
          @hole_index having selected @options
        :note this is a performance/memory optimization associated with creating
          subfamilies wrt one splitter having restricted options
        '''
        subhole = self[hole_index].copy()
        subhole.assume_options(options)

        shallow_copy = Holes(self)
        shallow_copy[hole_index] = subhole
        return shallow_copy


class ParentInfo():
    '''
    Container for stuff to be remembered when splitting an undecided family
    into subfamilies. Generally used to speed-up work with the subfamilies.
    :note it is better to store these things in a separate container instead
      of having a reference to the parent family (that will never be considered
      again) for the purposes of memory efficiency.
    '''

    def __init__(self):
        # list of constraint indices still undecided in this family
        self.property_indices = None
        # for each undecided property contains analysis results
        self.analysis_hints = None

        # how many refinements were needed to create this family
        self.refinement_depth = None

        # explicit list of all non-default actions in the MDP
        self.selected_actions = None
        # for each hole and for each option explicit list of all non-default actions in the MDP
        self.hole_selected_actions = None
        # index of a hole used to split the family
        self.splitter = None


class DesignSpace(Holes):
    '''
    List of holes supplied with
    - a list of constraint indices to investigate in this design space
    - (optionally) z3 encoding of this design space
    :note z3 (re-)encoding construction must be invoked manually
    '''

    # z3 solver containing description of the complete design space
    solver = None
    # for each hole contains a corresponding solver variable
    solver_vars = None
    # for each hole contains a list of equalities [h==opt1,h==opt2,...]
    solver_clauses = None

    # current depth of push/pop solving
    solver_depth = 0

    # whether hints will be stored for subsequent MDP model checking
    store_hints = True

    def __init__(self, holes=[], parent_info=None):
        super().__init__(holes)

        self.mdp = None
        self.hole_clauses = None
        self.encoding = None

        self.has_assignments = True

        self.hole_selected_actions = None
        self.selected_actions = None
        self.refinement_depth = 0
        self.property_indices = None

        self.analysis_result = None
        self.splitter = None
        self.parent_info = parent_info
        if parent_info is not None:
            self.refinement_depth = parent_info.refinement_depth + 1
            self.property_indices = parent_info.property_indices

    def copy(self):
        return DesignSpace(super().copy())

    def sat_initialize(self):
        ''' Use this design space as a baseline for future refinements. '''

        DesignSpace.solver_depth = 0

        DesignSpace.solver_clauses = []
        logger.debug("Using Python Z3 for SMT solving.")
        DesignSpace.solver = z3.Solver()
        DesignSpace.solver_vars = [z3.Int(hole_index) for hole_index in self.hole_indices]
        for hole_index, hole in enumerate(self):
            var = DesignSpace.solver_vars[hole_index]
            clauses = [var == option for option in hole.options]
            DesignSpace.solver_clauses.append(clauses)

    @property
    def encoded(self):
        return self.encoding is not None

    def encode(self):
        ''' Encode this design space. '''
        self.hole_clauses = []
        for hole_index, hole in enumerate(self):
            all_clauses = DesignSpace.solver_clauses[hole_index]
            clauses = [all_clauses[option] for option in hole.options]
            if len(clauses) == 1:
                or_clause = clauses[0]
            else:
                or_clause = z3.Or(clauses)
            self.hole_clauses.append(or_clause)

        if len(self.hole_clauses) == 1:
            self.encoding = self.hole_clauses[0]
        else:
            self.encoding = z3.And(self.hole_clauses)

        self.has_assignments = True

    def pick_assignment(self):
        '''
        Pick any (feasible) hole assignment.
        :return None if no instance remains
        '''
        # get satisfiable assignment within this design space
        if not self.encoded:
            self.encode()

        if not self.has_assignments:
            return None

        Profiler.start("SMT solving")
        solver_result = DesignSpace.solver.check(self.encoding)
        Profiler.resume()
        if solver_result == z3.unsat:
            self.has_assignments = False
            return None
        sat_model = DesignSpace.solver.model()
        hole_options = []
        for hole_index, var in enumerate(DesignSpace.solver_vars):
            option = sat_model[var].as_long()
            hole_options.append([option])

        assignment = self.copy()
        assignment.assume_options(hole_options)

        return assignment

    def pick_assignment_priority(self, priority_subfamily):
        if priority_subfamily is None:
            return self.pick_assignment()

        # explore priority subfamily first
        assignment = priority_subfamily.pick_assignment()
        if assignment is not None:
            return assignment

        # explore remaining members
        return self.pick_assignment()

    def exclude_assignment(self, assignment, conflict):
        '''
        Exclude assignment from the design space using provided conflict.
        :param assignment hole assignment that yielded unsatisfiable DTMC
        :param conflict indices of relevant holes in the corresponding counterexample
        :return estimate of pruned assignments
        '''
        if not self.encoded:
            self.encode()

        pruning_estimate = 1
        counterexample_clauses = []
        for hole_index, var in enumerate(DesignSpace.solver_vars):
            if hole_index in conflict:
                option = assignment[hole_index].options[0]
                counterexample_clauses.append(DesignSpace.solver_clauses[hole_index][option])
            else:
                if not self[hole_index].is_unrefined:
                    counterexample_clauses.append(self.hole_clauses[hole_index])  # generalization step
                pruning_estimate *= self[hole_index].size

        assert len(counterexample_clauses) > 0  # TODO handle this
        counterexample_encoding = z3.Not(z3.And(counterexample_clauses))
        DesignSpace.solver.add(counterexample_encoding)

        return pruning_estimate

    def sat_level(self):
        ''' Reset solver depth level to correspond to refinement level. '''

        if self.refinement_depth == 0:
            # fresh family, nothing to do
            return

        # reset to the scope of the parent (refinement_depth - 1)
        while DesignSpace.solver_depth >= self.refinement_depth:
            DesignSpace.solver.pop()
            DesignSpace.solver_depth -= 1

        # create new scope
        DesignSpace.solver.push()
        DesignSpace.solver_depth += 1

    def generalize_hint(self, hint):
        hint_global = dict()
        hint = list(hint.get_values())
        for state in range(self.mdp.states):
            hint_global[self.mdp.quotient_state_map[state]] = hint[state]
        return hint_global

    def generalize_hints(self, result):
        prop = result.property
        hint_prim = self.generalize_hint(result.primary.result)
        hint_seco = self.generalize_hint(result.secondary.result) if result.secondary is not None else None
        return prop, (hint_prim, hint_seco)

    def collect_analysis_hints(self):
        Profiler.start("holes::collect_analysis_hints")
        res = self.analysis_result
        analysis_hints = dict()
        for index in res.constraints_result.undecided_constraints:
            prop, hints = self.generalize_hints(res.constraints_result.results[index])
            analysis_hints[prop] = hints
        if res.optimality_result is not None:
            prop, hints = self.generalize_hints(res.optimality_result)
            analysis_hints[prop] = hints
        Profiler.resume()
        return analysis_hints

    def translate_analysis_hint(self, hint):
        if hint is None:
            return None
        translated_hint = [0] * self.mdp.states
        for state in range(self.mdp.states):
            global_state = self.mdp.quotient_state_map[state]
            translated_hint[state] = hint[global_state]
        return translated_hint

    def translate_analysis_hints(self):
        if not DesignSpace.store_hints or self.parent_info is None:
            return None

        Profiler.start("holes::translate_analysis_hints")
        analysis_hints = dict()
        for prop, hints in self.parent_info.analysis_hints.items():
            hint_prim, hint_seco = hints
            translated_hint_prim = self.translate_analysis_hint(hint_prim)
            translated_hint_seco = self.translate_analysis_hint(hint_seco)
            analysis_hints[prop] = (translated_hint_prim, translated_hint_seco)

        Profiler.resume()
        return analysis_hints

    def collect_parent_info(self):
        pi = ParentInfo()
        pi.hole_selected_actions = self.hole_selected_actions
        pi.selected_actions = self.selected_actions
        pi.refinement_depth = self.refinement_depth
        pi.analysis_hints = self.collect_analysis_hints()
        cr = self.analysis_result.constraints_result
        pi.property_indices = cr.undecided_constraints if cr is not None else []
        pi.splitter = self.splitter
        pi.mdp = self.mdp
        return pi


class CombinationColoring:
    '''
    Dictionary of colors associated with different hole combinations.
    Note: color 0 is reserved for general hole-free objects.
    '''

    def __init__(self, holes):
        '''
        :param holes of the initial design space
        '''
        self.holes = holes
        self.coloring = {}
        self.reverse_coloring = {}

    @property
    def colors(self):
        return len(self.coloring)

    def get_or_make_color(self, hole_assignment):
        new_color = self.colors + 1
        color = self.coloring.get(hole_assignment, new_color)
        if color == new_color:
            self.coloring[hole_assignment] = color
            self.reverse_coloring[color] = hole_assignment
        return color

    def subcolors(self, subspace):
        ''' Collect colors that are valid within the provided design subspace. '''
        colors = set()
        for combination, color in self.coloring.items():
            contained = True
            for hole_index, hole in enumerate(subspace):
                if combination[hole_index] is None:
                    continue
                if combination[hole_index] not in hole.options:
                    contained = False
                    break
            if contained:
                colors.add(color)

        return colors

    def subcolors_proper(self, hole_index, options):
        colors = set()
        for combination, color in self.coloring.items():
            if combination[hole_index] in options:
                colors.add(color)
        return colors

    def get_hole_assignments(self, colors):
        ''' Collect all hole assignments associated with provided colors. '''
        hole_assignments = [set() for hole in self.holes]

        for color in colors:
            if color == 0:
                continue
            combination = self.reverse_coloring[color]
            for hole_index, assignment in enumerate(combination):
                if assignment is None:
                    continue
                hole_assignments[hole_index].add(assignment)
        hole_assignments = [list(assignments) for assignments in hole_assignments]

        return hole_assignments
