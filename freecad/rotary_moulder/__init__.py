# -*- coding: utf-8 -*-
"""Rotary Moulder Workbench package."""
import os
import FreeCAD
__version__ = "1.1.0"
ADDON_DIR = os.path.join(
    FreeCAD.getUserAppDataDir(), "Mod", "RotaryMoulder"
)
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
                "RotaryMoulder_ImportShape",
                "RotaryMoulder_PatternCavities",
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
