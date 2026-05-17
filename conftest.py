import sys
import os

# Allow tests to import modules from src/ without a package prefix.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
