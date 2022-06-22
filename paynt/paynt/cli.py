import sys
import click
import os

from . import version

from .sketch.sketch import Sketch
from .synthesizers.synthesizer import *

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
@click.option("--sketch", default="sketch.templ", help="name of the sketch file")

def paynt(
        project, sketch
):
    logger.info("This is Paynt version {}.".format(version()))

    # parse sketch
    if not os.path.isdir(project):
        raise ValueError(f"The project folder {project} is not a directory")
    sketch_path = os.path.join(project, sketch)
    sketch = Sketch(sketch_path)
    logger.info("Synthetizing an MDP scheduler wrt a hyperproperty")
    #synthesizer = SynthesizerHybrid(sketch)
    synthesizer = Synthesizer1By1(sketch)
    synthesizer.run()

def main():
    # setup_logger("paynt.log")
    setup_logger()
    paynt()


if __name__ == "__main__":
    main()
