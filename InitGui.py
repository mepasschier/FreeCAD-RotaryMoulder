# -*- coding: utf-8 -*-
"""Rotary Moulder Workbench loader for FreeCAD.

This file is required by FreeCAD to recognize the directory as a
workbench. The actual workbench class and command registration happen
in freecad/rotary_moulder/__init__.py (which is auto-loaded by
FreeCAD's namespace package discovery for ``freecad.*``).
"""
# Trigger the package __init__.py which registers the workbench.
from freecad import rotary_moulder  # noqa: F401
