# -*- coding: utf-8 -*-
"""GUI commands for the Rotary Moulder workbench."""

import os
import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

from . import geometry

ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "Resources", "icons",
)


def _icon(name):
    path = os.path.join(ICON_DIR, name)
    return path if os.path.exists(path) else ""


# ---------------------------------------------------------------------------

class CreateDrumCommand:
    """Create a new parametric drum."""

    def GetResources(self):
        return {
            "Pixmap": _icon("Drum.svg"),
            "MenuText": "Create Drum",
            "ToolTip": "Create a new rotary moulder drum",
        }

    def IsActive(self):
        return True

    def Activated(self):
        diameter, ok = QtGui.QInputDialog.getDouble(
            None, "Drum diameter", "Outer diameter (mm):",
            100.0, 10.0, 1000.0, 2,
        )
        if not ok:
            return
        length, ok = QtGui.QInputDialog.getDouble(
            None, "Drum length", "Axial length (mm):",
            200.0, 10.0, 5000.0, 2,
        )
        if not ok:
            return
        wall, ok = QtGui.QInputDialog.getDouble(
            None, "Wall thickness",
            "Wall thickness (mm, 0 = solid):",
            0.0, 0.0, diameter / 2.0 - 1.0, 2,
        )
        if not ok:
            return

        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("RotaryMoulder")
        FreeCAD.setActiveDocument(doc.Name)
        geometry.make_drum(doc, diameter=diameter, length=length, wall=wall)


FreeCADGui.addCommand("RotaryMoulder_CreateDrum", CreateDrumCommand())


# ---------------------------------------------------------------------------

def _select_drum_and_outline():
    """Return (drum, outline) from the current selection, or (None, None)."""
    sel = FreeCADGui.Selection.getSelection()
    drum = None
    outline = None
    for obj in sel:
        if hasattr(obj, "Proxy") and getattr(obj.Proxy, "Type", "") == \
                "RotaryMoulder::Drum":
            drum = obj
        elif hasattr(obj, "Shape"):
            outline = obj
    # Fallback: find a single drum in the document
    if drum is None:
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            drums = [o for o in doc.Objects
                     if hasattr(o, "Proxy")
                     and getattr(o.Proxy, "Type", "") == "RotaryMoulder::Drum"]
            if len(drums) == 1:
                drum = drums[0]
    return drum, outline


class AddCavityFromSketchCommand:
    """Add a drafted cavity to a drum, using the selected sketch as outline."""

    def GetResources(self):
        return {
            "Pixmap": _icon("Cavity.svg"),
            "MenuText": "Add Cavity From Sketch",
            "ToolTip": "Select a drum and a sketch (cookie outline), "
                       "then run this command to cut a drafted cavity.",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        drum, outline = _select_drum_and_outline()
        if drum is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "No drum found. Create a drum first, then select it together "
                "with your cookie outline sketch."
            )
            return
        if outline is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "Select a sketch or shape with a closed wire to use as the "
                "cookie outline, along with the drum."
            )
            return

        depth, ok = QtGui.QInputDialog.getDouble(
            None, "Cavity depth", "Depth into drum (mm):",
            3.1, 0.1, 100.0, 2,
        )
        if not ok:
            return
        angle, ok = QtGui.QInputDialog.getDouble(
            None, "Draft angle", "Side-wall draft angle (degrees):",
            16.0, 0.0, 60.0, 2,
        )
        if not ok:
            return
        # Direction is always floor_narrower (normal release direction).
        # The rim_narrower option (undercut) is not exposed - it would
        # prevent cookie release.
        direction = "floor_narrower"
        fillet, ok = QtGui.QInputDialog.getDouble(
            None, "Fillet radius",
            "Fillet on cavity floor edges (mm, 0 = none):",
            0.5, 0.0, 20.0, 2,
        )
        if not ok:
            return

        geometry.make_cavity(
            drum, outline,
            depth=depth, angle=angle,
            direction=direction, fillet=fillet,
        )


FreeCADGui.addCommand(
    "RotaryMoulder_AddCavityFromSketch", AddCavityFromSketchCommand()
)


# ---------------------------------------------------------------------------

def _select_cavity_and_outline():
    """Return (cavity_or_pattern, outline) from current selection."""
    sel = FreeCADGui.Selection.getSelection()
    cavity = None
    outline = None
    for obj in sel:
        if hasattr(obj, "Proxy") and getattr(obj.Proxy, "Type", "") in (
                "RotaryMoulder::DraftedCavity",
                "RotaryMoulder::CavityPattern"):
            cavity = obj
        elif hasattr(obj, "Shape"):
            outline = obj
    # Fallback: if there's only one cavity/pattern in the document
    if cavity is None:
        doc = FreeCAD.ActiveDocument
        if doc is not None:
            cavs = [o for o in doc.Objects
                    if hasattr(o, "Proxy")
                    and getattr(o.Proxy, "Type", "") in (
                        "RotaryMoulder::DraftedCavity",
                        "RotaryMoulder::CavityPattern")]
            if len(cavs) == 1:
                cavity = cavs[0]
    return cavity, outline


class AddDetailCommand:
    """Add a detail (engraved or embossed shape) to a cavity."""

    def GetResources(self):
        return {
            "Pixmap": _icon("Detail.svg"),
            "MenuText": "Add Detail to Cavity",
            "ToolTip": "Select a cavity (or pattern) and a sketch/shape for "
                       "the detail outline, then run this command to add "
                       "an engraved or embossed feature.",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        cavity, outline = _select_cavity_and_outline()
        if cavity is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "Select a Cavity (or Pattern) together with a sketch/shape "
                "for the detail outline."
            )
            return
        if outline is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "Select a sketch or shape with a closed wire to use as the "
                "detail outline, along with the cavity."
            )
            return

        mode, ok = QtGui.QInputDialog.getItem(
            None, "Detail type",
            "Detail mode:",
            ["engrave (indent into cavity floor)",
             "emboss (raised bump on cavity floor)"],
            0, False,
        )
        if not ok:
            return
        mode = mode.split()[0]

        depth, ok = QtGui.QInputDialog.getDouble(
            None, "Detail depth", "Depth (mm):",
            0.5, 0.05, 20.0, 2,
        )
        if not ok:
            return
        angle, ok = QtGui.QInputDialog.getDouble(
            None, "Detail draft angle",
            "Side-wall draft angle (degrees):",
            16.0, 0.0, 60.0, 2,
        )
        if not ok:
            return

        geometry.make_detail(
            cavity, outline,
            depth=depth, angle=angle,
            direction="floor_narrower", mode=mode,
        )


FreeCADGui.addCommand(
    "RotaryMoulder_AddDetail", AddDetailCommand()
)


# ---------------------------------------------------------------------------

class AddDockersCommand:
    """Add docker pins (perforation pins) to a cavity."""

    def GetResources(self):
        return {
            "Pixmap": _icon("Dockers.svg"),
            "MenuText": "Add Docker Pins to Cavity",
            "ToolTip": "Select a cavity (or pattern) and a sketch "
                       "containing points/vertices for pin positions. "
                       "Each point becomes one pin going through the "
                       "entire cookie thickness.",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        cavity, outline = _select_cavity_and_outline()
        if cavity is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "Select a Cavity (or Pattern) together with a sketch "
                "containing points/vertices for pin positions."
            )
            return
        if outline is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "Select a sketch with points (vertices) for pin positions, "
                "along with the cavity."
            )
            return

        tip_d, ok = QtGui.QInputDialog.getDouble(
            None, "Docker pin tip diameter",
            "Tip diameter (mm) - pin top is hemispherical at this radius:",
            0.2, 0.05, 20.0, 3,
        )
        if not ok:
            return
        angle, ok = QtGui.QInputDialog.getDouble(
            None, "Docker pin draft angle",
            "Side draft angle (degrees):",
            16.0, 0.0, 60.0, 2,
        )
        if not ok:
            return

        geometry.make_dockers(
            cavity, outline,
            tip_diameter=tip_d, angle=angle,
        )


FreeCADGui.addCommand(
    "RotaryMoulder_AddDockers", AddDockersCommand()
)


# ---------------------------------------------------------------------------

class ImportShapeCommand:
    """Import an SVG or DXF file and turn it into a usable outline."""

    def GetResources(self):
        return {
            "Pixmap": _icon("Import.svg"),
            "MenuText": "Import Cookie Outline (SVG/DXF)",
            "ToolTip": "Import an SVG or DXF file as the cookie outline.",
        }

    def IsActive(self):
        return True

    def Activated(self):
        path, _ = QtGui.QFileDialog.getOpenFileName(
            None, "Import outline", "",
            "Vector files (*.svg *.dxf);;SVG (*.svg);;DXF (*.dxf)",
        )
        if not path:
            return

        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("RotaryMoulder")
        before = set(o.Name for o in doc.Objects)
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".svg":
                import importSVG
                importSVG.insert(path, doc.Name)
            elif ext == ".dxf":
                try:
                    import importDXF
                    importDXF.insert(path, doc.Name)
                except ImportError:
                    import Import
                    Import.insert(path, doc.Name)
            else:
                QtGui.QMessageBox.warning(
                    None, "Rotary Moulder",
                    "Unsupported file type: {0}".format(ext)
                )
                return
        except Exception as exc:
            QtGui.QMessageBox.critical(
                None, "Rotary Moulder",
                "Import failed: {0}".format(exc)
            )
            return

        new_objs = [o for o in doc.Objects if o.Name not in before]
        if not new_objs:
            return

        # Try to consolidate imported edges into a single Draft Wire
        try:
            import Draft
            edges = []
            for o in new_objs:
                if hasattr(o, "Shape"):
                    edges.extend(o.Shape.Edges)
            if edges:
                import Part
                try:
                    wire = Part.Wire(Part.__sortEdges__(edges))
                except Exception:
                    wire = Part.Wire(edges)
                if wire.isClosed():
                    feature = doc.addObject("Part::Feature", "CookieOutline")
                    feature.Shape = wire
                    FreeCADGui.Selection.clearSelection()
                    FreeCADGui.Selection.addSelection(feature)
                    FreeCAD.Console.PrintMessage(
                        "RotaryMoulder: imported outline as 'CookieOutline'. "
                        "Select it with the drum and use 'Add Cavity'.\n"
                    )
                    return
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: could not consolidate import: {0}\n".format(exc)
            )

        FreeCAD.Console.PrintMessage(
            "RotaryMoulder: file imported. If it is open or fragmented, "
            "use Draft > Upgrade to merge edges into a closed wire.\n"
        )


FreeCADGui.addCommand("RotaryMoulder_ImportShape", ImportShapeCommand())


# ---------------------------------------------------------------------------

class PatternCavitiesCommand:
    """Create a patterned set of cavities around (and along) a drum.

    Selection modes:
      A) Drum + Cavity (or CavityPattern): replicate the existing cavity
         (with all its details) around the drum. Cavity parameters are
         taken from the source cavity.
      B) Drum + Sketch/Shape: create a new pattern from the outline.
         Cavity parameters (depth, draft, fillet) are configured in
         the dialog.
    """

    def GetResources(self):
        return {
            "Pixmap": _icon("Pattern.svg"),
            "MenuText": "Pattern Cavities Around Drum",
            "ToolTip": "Create multiple cavities arranged around and along "
                       "the drum. Select drum + outline OR drum + existing "
                       "cavity.",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        # Find drum and the secondary input (cavity OR outline)
        sel = FreeCADGui.Selection.getSelection()
        drum = None
        source_cavity = None
        outline = None
        for obj in sel:
            t = getattr(getattr(obj, "Proxy", None), "Type", "")
            if t == "RotaryMoulder::Drum":
                drum = obj
            elif t in ("RotaryMoulder::DraftedCavity",
                       "RotaryMoulder::CavityPattern"):
                source_cavity = obj
            elif hasattr(obj, "Shape"):
                outline = obj

        # Fallback: single drum in doc
        if drum is None:
            doc = FreeCAD.ActiveDocument
            if doc is not None:
                drums = [o for o in doc.Objects
                         if getattr(getattr(o, "Proxy", None), "Type", "")
                         == "RotaryMoulder::Drum"]
                if len(drums) == 1:
                    drum = drums[0]

        if drum is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "No drum found. Select a drum together with either an "
                "existing cavity OR a sketch outline."
            )
            return
        if source_cavity is None and outline is None:
            QtGui.QMessageBox.warning(
                None, "Rotary Moulder",
                "Select either: (a) a drum + an existing cavity to replicate, "
                "or (b) a drum + a sketch outline to create a new pattern."
            )
            return

        # Use cavity if available; otherwise outline
        use_cavity = (source_cavity is not None)
        dlg = _PatternDialog(drum, show_cavity_params=not use_cavity)
        if dlg.exec_() != QtGui.QDialog.Accepted:
            return
        params = dlg.values()

        target = source_cavity if use_cavity else outline
        if use_cavity:
            # Cavity params come from source; pass only layout/count/spacing
            geometry.make_pattern(
                drum, target,
                count_around=params["count_around"],
                count_axial=params["count_axial"],
                spacing=params["spacing"],
                axial_offset=params["axial_offset"],
                layout=params["layout"],
            )
        else:
            geometry.make_pattern(
                drum, target,
                count_around=params["count_around"],
                count_axial=params["count_axial"],
                spacing=params["spacing"],
                axial_offset=params["axial_offset"],
                depth=params["depth"],
                angle=params["angle"],
                direction="floor_narrower",
                fillet=params["fillet"],
                layout=params["layout"],
            )


class _PatternDialog(QtGui.QDialog):
    def __init__(self, drum, show_cavity_params=True, parent=None):
        super().__init__(parent)
        self.show_cavity_params = show_cavity_params
        title = "Pattern Cavities"
        if not show_cavity_params:
            title += " (using existing cavity)"
        self.setWindowTitle(title)
        layout = QtGui.QFormLayout(self)

        self.count_around = QtGui.QSpinBox()
        self.count_around.setRange(1, 200)
        self.count_around.setValue(6)
        layout.addRow("Count around drum:", self.count_around)

        self.count_axial = QtGui.QSpinBox()
        self.count_axial.setRange(1, 200)
        self.count_axial.setValue(3)
        layout.addRow("Count along length:", self.count_axial)

        self.spacing = QtGui.QDoubleSpinBox()
        self.spacing.setRange(0.0, 10000.0)
        self.spacing.setDecimals(2)
        self.spacing.setValue(50.0)
        self.spacing.setSuffix(" mm")
        layout.addRow("Axial spacing:", self.spacing)

        self.axial_offset = QtGui.QDoubleSpinBox()
        self.axial_offset.setRange(0.0, 10000.0)
        self.axial_offset.setDecimals(2)
        self.axial_offset.setValue(25.0)
        self.axial_offset.setSuffix(" mm")
        layout.addRow("Offset from drum end:", self.axial_offset)

        self.layout_combo = QtGui.QComboBox()
        self.layout_combo.addItem("linear", "linear")
        self.layout_combo.addItem("alternating (brick pattern)",
                                  "alternating")
        layout.addRow("Layout:", self.layout_combo)

        # Cavity-specific fields, only shown when creating a new pattern
        # directly from an outline.
        if show_cavity_params:
            self.depth = QtGui.QDoubleSpinBox()
            self.depth.setRange(0.1, 200.0)
            self.depth.setDecimals(2)
            self.depth.setValue(3.1)
            self.depth.setSuffix(" mm")
            layout.addRow("Cavity depth:", self.depth)

            self.angle = QtGui.QDoubleSpinBox()
            self.angle.setRange(0.0, 60.0)
            self.angle.setDecimals(2)
            self.angle.setValue(16.0)
            self.angle.setSuffix(" °")
            layout.addRow("Draft angle:", self.angle)

            self.fillet = QtGui.QDoubleSpinBox()
            self.fillet.setRange(0.0, 50.0)
            self.fillet.setDecimals(2)
            self.fillet.setValue(0.5)
            self.fillet.setSuffix(" mm")
            layout.addRow("Fillet radius:", self.fillet)
        else:
            self.depth = None
            self.angle = None
            self.fillet = None

        btns = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self):
        v = {
            "count_around": self.count_around.value(),
            "count_axial": self.count_axial.value(),
            "spacing": self.spacing.value(),
            "axial_offset": self.axial_offset.value(),
            "layout": self.layout_combo.currentData(),
        }
        if self.show_cavity_params:
            v["depth"] = self.depth.value()
            v["angle"] = self.angle.value()
            v["fillet"] = self.fillet.value()
        return v


FreeCADGui.addCommand("RotaryMoulder_PatternCavities", PatternCavitiesCommand())


# ---------------------------------------------------------------------------

class ToggleDebugCommand:
    """Toggle the storage of intermediate debug shapes (in an RM_Debug
    group) during geometry construction. When ON, helpful for inspecting
    what's happening when geometry fails. When OFF, faster builds and
    cleaner trees - recommended for production use."""

    def GetResources(self):
        return {
            "Pixmap": _icon("Debug.svg"),
            "MenuText": "Toggle Debug Intermediates",
            "ToolTip": "Toggle saving intermediate debug shapes during "
                       "geometry construction. Useful for diagnosing "
                       "failures; disable for cleaner builds. The button "
                       "stays highlighted/checked while debug mode is ON.",
            "Checkable": geometry._get_debug_flag(),
        }

    def IsActive(self):
        return True

    def Activated(self, index=None):
        # When a command is Checkable, FreeCAD calls Activated(self, index)
        # with index = the new checked state (1 or 0). When called as a
        # plain command (no index), fall back to reading+flipping the flag.
        if index is None:
            new_state = not geometry._get_debug_flag()
        else:
            new_state = bool(index)
        geometry._set_debug_flag(new_state)
        msg = "Debug intermediates: {0}\n".format(
            "ON" if new_state else "OFF")
        FreeCAD.Console.PrintMessage("RotaryMoulder: " + msg)
        # Show a status-bar message so the user gets immediate feedback
        try:
            FreeCADGui.getMainWindow().statusBar().showMessage(
                "Rotary Moulder: Debug " + ("ON" if new_state else "OFF"),
                3000)
        except Exception:
            pass


FreeCADGui.addCommand("RotaryMoulder_ToggleDebug", ToggleDebugCommand())
