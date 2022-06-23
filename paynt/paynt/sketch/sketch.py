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

        # initializing the Model Checking options
        MarkovChain.initialize(self.specification.stormpy_formulae())

        logger.info("Processing actions and Initializing the quotient...")
        self.quotient = HyperPropertyQuotientContainer(self)

        logger.info(f"Sketch has {self.design_space.num_holes} holes")
        logger.info(f"Design space size: {self.design_space.size}")
        logger.info(f"Sketch parsing complete.")
        Profiler.stop()

    @classmethod
    def parse_pc_specification(cls, prism):
        fs = Specification.string_formulae()
        properties = []
        for f in fs:
            p = stormpy.parse_properties_for_prism_program(fs, prism)
            # TODO: note that this works only for the PC_property, which has two initial states
            p0 = PC_Property(p, 0)
            properties.append(p0)
            p1 = PC_Property(p, 1)
            properties.append(p1)
        return Specification(properties)
