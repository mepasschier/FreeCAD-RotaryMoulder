# -*- coding: utf-8 -*-
"""Rotary Moulder Workbench package."""
import os
import FreeCAD

__version__ = "1.3.0"

# Find the addon root. This file lives at <addon>/freecad/rotary_moulder/__init__.py
# so two parents up gets us to the addon root, regardless of whether the
# addon folder is named "RotaryMoulder", "FreeCAD-RotaryMoulder", or
# anything else (Addon Manager installs may use different names).
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
ICON_PATH = os.path.join(ADDON_DIR, "Resources", "icons",
                         "RotaryMoulder.svg")

if FreeCAD.GuiUp:
    import FreeCADGui

    class RotaryMoulderWorkbench(FreeCADGui.Workbench):
        """Workbench for designing rotary cookie moulder drums."""
        MenuText = "Rotary Moulder"
        ToolTip = "Design rotary cookie moulders with drafted cavities"
        Icon = ICON_PATH

        def Initialize(self):
            from freecad.rotary_moulder import commands  # noqa: F401
            cmds = [
                "RotaryMoulder_CreateDrum",
                "RotaryMoulder_AddCavityFromSketch",
                "RotaryMoulder_AddDetail",
                "RotaryMoulder_AddDockers",
                "RotaryMoulder_AddRoster",
                "RotaryMoulder_ImportShape",
                "RotaryMoulder_PatternCavities",
                "RotaryMoulder_AddCuttingCup",
                "RotaryMoulder_PatternCuttingCups",
                "RotaryMoulder_ToggleDebug",
            ]
            self.appendToolbar("Rotary Moulder", cmds)
            self.appendMenu("Rotary Moulder", cmds)

        def Activated(self):
            FreeCAD.Console.PrintMessage(
                "Rotary Moulder workbench activated.\n"
            )

        def Deactivated(self):
            FreeCAD.Console.PrintMessage(
                "Rotary Moulder workbench deactivated.\n"
            )

        def GetClassName(self):
            return "Gui::PythonWorkbench"

    FreeCADGui.addWorkbench(RotaryMoulderWorkbench())
