# -*- coding: utf-8 -*-
# Rotary Moulder Workbench for FreeCAD
import os
import FreeCAD
import FreeCADGui

ADDON_DIR = os.path.dirname(__file__)
ICON_DIR = os.path.join(ADDON_DIR, "Resources", "icons")


class RotaryMoulderWorkbench(FreeCADGui.Workbench):
    """Workbench for designing rotary cookie moulder drums."""

    MenuText = "Rotary Moulder"
    ToolTip = "Design rotary cookie moulders with drafted cavities"
    Icon = os.path.join(ICON_DIR, "RotaryMoulder.svg")

    def Initialize(self):
        # Import commands so they register with FreeCADGui
        from freecad.rotary_moulder import commands  # noqa: F401

        cmds = [
            "RotaryMoulder_CreateDrum",
            "RotaryMoulder_AddCavityFromSketch",
            "RotaryMoulder_AddDetail",
            "RotaryMoulder_AddDockers",
            "RotaryMoulder_ImportShape",
            "RotaryMoulder_PatternCavities",
            "RotaryMoulder_ToggleDebug",
        ]
        self.appendToolbar("Rotary Moulder", cmds)
        self.appendMenu("Rotary Moulder", cmds)

    def Activated(self):
        FreeCAD.Console.PrintMessage("Rotary Moulder workbench activated.\n")

    def Deactivated(self):
        FreeCAD.Console.PrintMessage("Rotary Moulder workbench deactivated.\n")

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(RotaryMoulderWorkbench())
