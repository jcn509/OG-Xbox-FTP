"""Configuration for the tests"""

# Pylint will complain that imports here are not used when they in fact are
# pylint: disable=unused-import
from pyxboxtest.xqemu.hdd import xqemu_blank_hdd_template

pytest_plugins = ("pyxboxtest.pytest_plugin",)
