import logging

def configure_logging(level=logging.INFO):
    logging.basicConfig(level=level,format="[%(levelname)s] %(message)s")
