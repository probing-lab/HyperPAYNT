import sys
import click
import os

from . import version

from .hypersketch.hypersketch import HyperSketch
from .hypersynthesizers.hypersynthesizer import *

import logging
# logger = logging.getLogger(__name__)

def setup_logger(log_path = None):
    ''' Setup routine for logging. '''
    
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # root.setLevel(logging.INFO)

    # formatter = logging.Formatter('%(asctime)s %(threadName)s - %(name)s - %(levelname)s - %(message)s')
    formatter = logging.Formatter('%(asctime)s - %(filename)s - %(message)s')

    handlers = []
    if log_path is not None:
        fh = logging.FileHandler(log_path)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        handlers.append(fh)
    ch = logging.StreamHandler(sys.stdout)
    handlers.append(ch)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    for h in handlers:
        root.addHandler(h)
    return handlers


@click.command()
@click.option("--project", required=True, help="root", )
@click.option("--sketch", default="sketch.templ", show_default=True, help="name of the sketch file")
@click.option("--props", default="sketch.props", show_default=True, help="name of the properties file in the project")
@click.option("--method", type=click.Choice(['onebyone', 'cegis', 'ar', 'hybrid'], case_sensitive=False), default="ar")
@click.option("--explore_all", is_flag=True, default=False, help="explore all the design space")

def paynt(
        project, sketch, props, method, explore_all
):
    logger.info("This is Paynt version {}.".format(version()))

    # parse sketch
    if not os.path.isdir(project):
        raise ValueError(f"The project folder {project} is not a directory")
    sketch_path = os.path.join(project, sketch)
    properties_path = os.path.join(project, props)

    sketch = HyperSketch(sketch_path, properties_path)
    logger.info("Synthetizing an MDP scheduler wrt a hyperproperty")


    #choose synthesis method
    if method == "onebyone":
        synthesizer = HyperSynthesizer1By1(sketch)
    elif method == "cegis":
        synthesizer = HyperSynthesizerCEGIS(sketch)
    elif method == "ar":
        synthesizer = HyperSynthesizerAR(sketch)
    elif method == "hybrid":
        synthesizer = SynthesizerHybrid(sketch)
    elif method == "evo":
        raise NotImplementedError
    else:
        assert None

    # if the spec has some sort of optimality property, we must of course explore all the design space
    # to establish that the assignment is the true optimum
    spec = sketch.specification
    has_some_optimality = spec.has_optimality or spec.has_hyperoptimality or spec.has_scheduler_hyperoptimality
    explore_all = explore_all or has_some_optimality

    synthesizer.run(explore_all)

def main():
    # setup_logger("paynt.log")
    setup_logger()
    paynt()


if __name__ == "__main__":
    main()
