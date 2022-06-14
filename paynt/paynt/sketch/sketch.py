import stormpy

from .pc_property import PC_Property, Specification, ThresholdSpecification, DPSpecification
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

        constant_map = None

        logger.info(f"Loading sketch from {sketch_path}...")
        logger.info(f"Assuming a sketch in a PRISM format ...")
        self.prism, hole_definitions = Sketch.load_sketch(sketch_path)  # TODO: but for an hyperproperty there are no holes, hole defitnions will be an empty dictionary

        expression_parser = stormpy.storage.ExpressionParser(self.prism.expression_manager)
        expression_parser.set_identifier_mapping(dict())

        # constants that are undefined in the sketch and are not holes.
        if constant_str != '':
            logger.info(f"Assuming constant definitions: '{constant_str}' ...")
            constant_map = Sketch.map_constants(self.prism, expression_parser, constant_str)
            self.prism = self.prism.define_constants(constant_map)
            self.prism = self.prism.substitute_constants()

        if len(hole_definitions) == 0:
            logger.info("Sketch does not contain any hole definitions.")
            self.design_space = DesignSpace() # TODO: hyperproperties -> MDP without holes -> how to deal with this?
        else:
            logger.info("Processing hole definitions ...")
            self.prism, self.hole_expressions, self.design_space = Sketch.parse_holes(self.prism, expression_parser, hole_definitions)

            logger.info(f"Sketch has {self.design_space.num_holes} holes")
            # logger.info(f"Listing hole domains: {holes}"
            logger.info(f"Design space size: {self.design_space.size}")

        logger.info(f"Loading properties from {properties_path} ...")
        self.specification = Sketch.parse_specification(self.prism, constant_map, properties_path)
        logger.info(f"Found the following specification: {self.specification}")
        self.design_space.property_indices = self.specification.all_constraint_indices()
        MarkovChain.initialize(self.specification.stormpy_formulae())

        logger.info(f"Initializing the quotient ...")
        self.quotient = HyperPropertyQuotientContainer(self)

        logger.info(f"Sketch parsing complete.")
        Profiler.stop()

    # load a PRISM model into a PRISM representation with stormpy method parse_prism_program
    @classmethod
    def load_sketch(cls, sketch_path):
        # todo: add parsing of actions as holes
        hole_definitions = None
        prism = stormpy.parse_prism_program(sketch_path, prism_compat=True)
        return prism, hole_definitions

    @classmethod
    def parse_holes(cls, prism, expression_parser, hole_definitions):

        # parse hole definitions
        holes = Holes()
        hole_expressions = []
        for hole_name,definition in hole_definitions.items():
            options = definition.split(",")
            expressions = [expression_parser.parse(o) for o in options]
            hole_expressions.append(expressions)

            options = list(range(len(expressions)))
            option_labels = [str(e) for e in expressions]
            hole = Hole(hole_name, options, option_labels)
            holes.append(hole)

        # check that all undefined constants are indeed the holes
        undefined_constants = [c for c in prism.constants if not c.defined]
        assert len(undefined_constants) == len(holes), "some constants were unspecified"

        # convert single-valued holes to a defined constant
        trivial_holes_definitions = {}
        nontrivial_holes = Holes()
        nontrivial_hole_expressions = []
        for hole_index,hole in enumerate(holes):
            if hole.size == 1:
                trivial_holes_definitions[prism.get_constant(hole.name).expression_variable] = hole_expressions[hole_index][0]
            else:
                nontrivial_holes.append(hole)
                nontrivial_hole_expressions.append(hole_expressions[hole_index])
        holes = nontrivial_holes
        hole_expressions = nontrivial_hole_expressions

        # substitute trivial holes
        prism = prism.define_constants(trivial_holes_definitions)
        prism = prism.substitute_constants()

        design_space = DesignSpace(holes)

        return prism, hole_expressions, design_space

    # refactored
    @classmethod
    def parse_pc_specification(cls, prism):

        fs = Specification.string_formulae()
        properties = []
        for f in fs:
            parsed = stormpy.parse_properties_for_prism_program(f, prism)
            p = PC_Property(parsed)
            properties.append(p)

        s = Specification(properties)
        return  s