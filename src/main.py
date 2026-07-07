"""
main.py — placeholder entry point.
Currently only verifies that the reorganized package structure imports correctly.
TODO: wire up device_registry, run_logger, and real extract/transform/load logic.
"""

from general import utils as general_utils
from extract import utils as extract_utils
from transform import utils as transform_utils
# from load import utils as load_utils # no need rn

if __name__ == "__main__":
    print("hello from main.py. Also, all src utils imported successfully.")