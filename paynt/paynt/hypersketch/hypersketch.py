from ..synthesizers.quotient import *
from ..profiler import Profiler
from .hyperparser import *

import logging

logger = logging.getLogger(__name__)


class HyperSketch:

    def __init__(self, sketch_path, properties_path):
        Profiler.initialize()
        Profiler.start("sketch")

        self.prism = None
        self.hole_expressions = None

        self.design_space = None
        self.specification = None
        self.quotient = None

        sketch_parser = HyperParser()

        # parsing the specification
        specification, prism = sketch_parser.parse_properties(sketch_path, properties_path)
        self.specification = specification
        self.prism = prism

        # initializing the Model Checking options
        MarkovChain.initialize(self.specification.stormpy_formulae())

        # setting the correct design space (done in the initialization of the quotient)
        logger.info("Processing actions and Initializing the quotient and the design space...")
        self.quotient = HyperPropertyQuotientContainer(self, sketch_parser)

        logger.info(f"Sketch has {self.design_space.num_holes} holes")
        logger.info(f"Design space size: {self.design_space.size}")
        logger.info(f"Design space: {self.design_space}")
        logger.info(f"Sketch parsing complete.")

        logger.info(f"Matching holes: {DesignSpace.matching_hole_indexes.values()}")
        Profiler.stop()
