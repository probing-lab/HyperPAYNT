import sys
import click
import os

from . import version

from .sketch.sketch import Sketch
from .sketch.pc_property import PC_Property
from .synthesizers.synthesizer import *
from .sketch.ta_property import TA_Property
from .sketch.pw_property import PW_Property
from .sketch.ts_property import TS_Property

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
@click.option("--method", type=click.Choice(['onebyone', 'cegis', 'ar', 'hybrid'], case_sensitive=False), default="ar")
@click.option("--hp", type=click.Choice(['pc', 'ta', 'pw', 'ts'], case_sensitive=False), default="pc")

def paynt(
        project, sketch, method, hp
):
    logger.info("This is Paynt version {}.".format(version()))

    # parse sketch
    if not os.path.isdir(project):
        raise ValueError(f"The project folder {project} is not a directory")
    sketch_path = os.path.join(project, sketch)

    # choose experiment name
    if hp == "ta":
        prop = TA_Property
    elif hp == "pc":
        prop = PC_Property
    elif hp == "pw":
        prop = PW_Property
    elif hp == 'ts':
        prop = TS_Property

    sketch = Sketch(sketch_path, prop)
    logger.info("Synthetizing an MDP scheduler wrt a hyperproperty")


    #choose synthesis method
    if method == "onebyone":
        synthesizer = Synthesizer1By1(sketch)
    elif method == "cegis":
        synthesizer = SynthesizerCEGIS(sketch)
    elif method == "ar":
        synthesizer = SynthesizerAR(sketch)
    elif method == "hybrid":
        synthesizer = SynthesizerHybrid(sketch)
    elif method == "evo":
        raise NotImplementedError
    else:
        assert None

    synthesizer.run()

def main():
    # setup_logger("paynt.log")
    setup_logger()
    paynt()


if __name__ == "__main__":
    main()
