import stormpy

from .pc_property import PC_Property, Specification
from .holes import Hole, Holes, DesignSpace
from ..synthesizers.models import MarkovChain
from ..synthesizers.quotient import *
from ..profiler import Profiler

import os
import re
import operator
import uuid

import logging
logger = logging.getLogger(__name__)

class Sketch:

    def __init__(self, sketch_path):

        Profiler.initialize()
        Profiler.start("sketch")

        self.prism = None
        self.hole_expressions = None

        self.design_space = None
        self.specification = None
        self.quotient = None

        # sketch loading
        logger.info(f"Loading sketch from {sketch_path}...")
        logger.info(f"Assuming a sketch in a PRISM format ...")
        self.prism = stormpy.parse_prism_program(sketch_path, prism_compat=True)

        #formulae loading (only PC formulae for proof of concept)
        logger.info(f"Loading pc_properties ...")
        self.specification = Sketch.parse_pc_specification(self.prism)
        logger.info(f"Found the following specification: {self.specification}")


        logger.info("Processing actions...")
        self.design_space = Sketch.parse_holes(self.prism, self.specification.stormpy_properties())

        logger.info(f"Sketch has {self.design_space.num_holes} holes")
        logger.info(f"Design space size: {self.design_space.size}")

        # TODO: working from here
        self.design_space.property_indices = self.specification.all_constraint_indices()
        MarkovChain.initialize(self.specification.stormpy_formulae())

        logger.info(f"Initializing the quotient ...")
        self.quotient = HyperPropertyQuotientContainer(self)

        logger.info(f"Sketch parsing complete.")
        Profiler.stop()

    @classmethod
    def parse_holes(cls, program, properties):

        # building the MDP
        model = stormpy.build_model(program, properties)

        # parse holes (i.e, actions of the model)
        holes = Holes()
        for state in model.states:
            options = []
            for action in state.actions:
                options.append(action)
            if (options.size() > 1):
                hole = Hole(state, options)
                holes.append(hole)

        design_space = DesignSpace(holes)
        return design_space

    @classmethod
    def parse_pc_specification(cls, prism):
        fs = Specification.string_formulae()
        properties = []
        for f in fs:
            parsed = stormpy.parse_properties_for_prism_program(f, prism)
            p = PC_Property(parsed)
            properties.append(p)
        return Specification(properties)

    # TODO: do we need this? ( I have no idea at the moment)
    def restrict_prism(self, assignment):
        assert assignment.size == 1
        substitution = {}
        for hole_index,hole in enumerate(assignment):
            ev = self.prism.get_constant(hole.name).expression_variable
            expr = self.hole_expressions[hole_index][hole.options[0]]
            substitution[ev] = expr
        program = self.prism.define_constants(substitution)
        model = stormpy.build_sparse_model_with_options(program, MarkovChain.builder_options)
        return model