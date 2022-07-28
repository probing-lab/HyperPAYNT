import stormpy

from .pc_property import PC_Property
from .spec import Specification
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

    def __init__(self, sketch_path, prop):

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
        self.prism = prop.parse_program(sketch_path)

        #formulae loading
        logger.info(f"Loading properties ...")
        self.specification = prop.parse_specification(self.prism)
        logger.info(f"Found the following specification: {self.specification}")

        # initializing the Model Checking options
        MarkovChain.initialize(self.specification.stormpy_formulae())

        logger.info("Processing actions and Initializing the quotient...")
        self.quotient = HyperPropertyQuotientContainer(self)

        logger.info(f"Sketch has {self.design_space.num_holes} holes")
        logger.info(f"Design space size: {self.design_space.size}")
        logger.info(f"Sketch parsing complete.")
        Profiler.stop()
