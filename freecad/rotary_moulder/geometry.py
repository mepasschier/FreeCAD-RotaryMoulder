# -*- coding: utf-8 -*-
"""Rotary Moulder cavity geometry.

Features:
  * Drafted cookie cavity via curved-chunk method (sleeve intersected with
    tapered prism).
  * Cavity Details (text/decoration). Each face's outer wire and each hole
    wire is built as its own _build_chunk. Outer chunks are applied with
    the natural boolean for the mode (cut for engrave, fuse for emboss).
    Hole chunks are applied with the inverse operation so the hole is
    preserved through the letter.
  * Pattern of cavities around the drum, with details inherited from a
    source Cavity and/or added directly to the pattern.

Sketch dimension policy:
  * Cavity: sketch matches at the drum surface (r_top).
  * Detail: sketch matches at the cavity floor (r_bot) - this is the
    visible side on the resulting cookie.

Letters with tricky geometry are handled via fallback paths:
  * Direct face offset (clean precise geometry) - try first
  * Manual vertex-bisector offset on a polyline source - for letters with
    sharp inner corners (M, V, A) that break makeOffset2D
  * Sleeve cut-cut workaround (A.common(B) = A - (A - B)) - for letters
    with continuous curves (S, C, G) where sleeve.common() returns 0
    due to tangent geometry
  * Largest-solid filtering after cut-cut, to remove tiny numerical
    fragments while keeping the visible letter body
"""

import math
import FreeCAD
import Part


# ===========================================================================
# Debug intermediates - shows construction shapes in tree for diagnostics
# ===========================================================================
# Set to True to add intermediate shapes (wires, cones, clipped solids, etc.)
# DEBUG_INTERMEDIATES: when True, _debug_show adds intermediate shapes
# as document objects under a "RM_Debug" group. Useful when geometry fails.
# Stored in FreeCAD's user parameters so it persists between sessions
# and can be toggled from the toolbar.

def _get_debug_flag():
    """Read the debug-intermediates flag from FreeCAD's user parameters."""
    try:
        params = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/RotaryMoulder")
        return params.GetBool("DebugIntermediates", False)
    except Exception:
        return False


def _set_debug_flag(value):
    """Persist the debug flag to FreeCAD's user parameters."""
    try:
        params = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/RotaryMoulder")
        params.SetBool("DebugIntermediates", bool(value))
    except Exception:
        pass


def _debug_show(shape, label):
    """Add `shape` as a Part::Feature to the active document under a
    RM_Debug group, with the given label, when DebugIntermediates is on.
    Silently no-ops if disabled or there's no active document."""
    if not _get_debug_flag():
        return
    if shape is None:
        return
    try:
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return
        # Find or create the RM_Debug group
        grp = doc.getObject("RM_Debug")
        if grp is None:
            grp = doc.addObject("App::DocumentObjectGroup", "RM_Debug")
        obj = doc.addObject("Part::Feature", "RM_" + label)
        obj.Shape = shape
        grp.addObject(obj)
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: debug_show failed for '{0}': {1}\n".format(
                label, exc))


def _debug_clear():
    """Remove the RM_Debug group and all its children. Called at start of
    each build to avoid accumulating shapes from previous runs."""
    if not _get_debug_flag():
        return
    try:
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return
        grp = doc.getObject("RM_Debug")
        if grp is None:
            return
        # Remove all children
        for child in list(grp.Group):
            try:
                doc.removeObject(child.Name)
            except Exception:
                pass
        doc.removeObject(grp.Name)
    except Exception:
        pass


# ===========================================================================
# Wire / face helpers
# ===========================================================================

# ===========================================================================
# SoS (Sketch_On_Surface) mapping helpers
# ===========================================================================
#
# The Curves workbench's Sketch_On_Surface object maps a flat 2D sketch onto
# a cylindrical surface via:
#   theta = sketch_x * (2*pi / sketch_W)      where sketch_W is sketch boundary width
#   drum_y = sketch_y * (L_drum / sketch_L)   where sketch_L is sketch boundary height
#
# This means the cavity outline (which goes through SoS) ends up at a specific
# place on the drum that depends on the sketch boundary dimensions. The detail
# outline (ShapeString) uses raw sketch coords directly, but we need the
# resulting prism to land at the SAME theta as the SoS-projected outline.
#
# Strategy: pre-scale the sketch coords so that 1 unit becomes 1 arc-length
# unit on the drum. Then _build_chunk's existing theta = u / R_drum gives
# the same theta as SoS.


def _get_sos_mapping(outline_obj, drum_obj):
    """If outline_obj is a Sketch_On_Surface (or wraps one), return the
    mapping needed to convert raw sketch coords into drum coords.
    Returns (theta_per_sketch_x, drum_y_per_sketch_y, x_origin, y_origin)
    tuple, or None if no SoS mapping is detected.

    The mapping is applied as:
        theta = (sketch_x - x_origin) * theta_per_sketch_x  (radians)
        drum_y = (sketch_y - y_origin) * drum_y_per_sketch_y
    """
    if not hasattr(outline_obj, "Sketch"):
        return None
    src = outline_obj.Sketch
    if src is None:
        return None
    geom = getattr(src, "Geometry", None)
    if not geom:
        return None
    xs = []
    ys = []
    for g in geom[:4]:
        if hasattr(g, "StartPoint") and hasattr(g, "EndPoint"):
            xs.extend([g.StartPoint.x, g.EndPoint.x])
            ys.extend([g.StartPoint.y, g.EndPoint.y])
    if len(xs) < 8 or len(ys) < 8:
        return None
    sketch_W = max(xs) - min(xs)
    sketch_L = max(ys) - min(ys)
    if sketch_W < 1e-6 or sketch_L < 1e-6:
        return None
    sketch_x_min = min(xs)
    sketch_y_min = min(ys)

    L_drum = float(drum_obj.Length)
    # SoS convention: sketch_W maps to 2*pi radians around the drum
    theta_per_x = 2.0 * math.pi / sketch_W
    # Y scales linearly: sketch_L maps to L_drum
    drum_y_per_y = L_drum / sketch_L
    return (theta_per_x, drum_y_per_y, sketch_x_min, sketch_y_min)


def _all_closed_wires(shape):
    if shape is None:
        return []
    out = []

    def _already_have(candidate):
        for existing in out:
            try:
                if existing.isSame(candidate):
                    return True
            except Exception:
                pass
            # Fallback geometric dedupe: same vertex count and near-equal
            # bounding boxes + length (handles distinct-but-identical refs)
            try:
                if (len(existing.Vertexes) == len(candidate.Vertexes)
                        and abs(existing.Length - candidate.Length) < 1e-6):
                    eb, cb = existing.BoundBox, candidate.BoundBox
                    if (abs(eb.XMin - cb.XMin) < 1e-6
                            and abs(eb.YMin - cb.YMin) < 1e-6
                            and abs(eb.XMax - cb.XMax) < 1e-6
                            and abs(eb.YMax - cb.YMax) < 1e-6):
                        return True
            except Exception:
                pass
        return False

    if shape.ShapeType == "Wire" and shape.isClosed():
        out.append(shape)
    for w in getattr(shape, "Wires", []):
        if w.isClosed() and not _already_have(w):
            out.append(w)
    return out


def _resolve_flat_outline_all(outline_obj):
    if hasattr(outline_obj, "Sketch") and outline_obj.Sketch is not None:
        src = outline_obj.Sketch
        if hasattr(src, "Shape") and src.Shape and src.Shape.Wires:
            wires = [w for w in src.Shape.Wires if w.isClosed()]
            if wires:
                return wires, "wrapped via Sketch_On_Surface"
    shape = getattr(outline_obj, "Shape", None)
    if shape is None:
        return [], "no shape"
    wires = _all_closed_wires(shape)
    return (wires, "direct sketch") if wires else ([], "no closed wire")


def _resolve_flat_outline(outline_obj):
    wires, label = _resolve_flat_outline_all(outline_obj)
    if not wires:
        return None, label
    wires.sort(key=lambda w: w.BoundBox.DiagonalLength, reverse=True)
    return wires[0], label


# ===========================================================================
# Curved chunk builder
# ===========================================================================

def _build_chunk(input_obj_or_wires, drum_obj, r_top, r_bot,
                 depth, offset_dist, margin=5.0, sketch_at_bot=False,
                 center_override=None, eps_override=None, mapping=None):
    """Build a chunk that conforms to the drum's cylinder via the
    cone-frustum method:

      1. Project the 2D outline onto the drum cylinder at r_top
         -> curved 3D wire on the cylinder surface
      2. Loft this wire to an apex point on the cookie's axial centerline.
         The apex position determines the draft angle.
      3. Clip the cone with the drum-radius cylinder (outer boundary)
      4. Subtract the inner cylinder at r_bot to get the cavity-floor surface

    The resulting solid has:
      - Curved top face matching r_top (drum surface for cavity, or
        cavity-floor-plus-depth for emboss detail)
      - Curved bot face matching r_bot
      - Sloped side walls with the configured draft angle
      - Both caps are portions of cylinder surfaces (clean for booleans)

    For floor_narrower: apex is BELOW r_bot (toward drum axis).
    For rim_narrower: apex is ABOVE r_top (outside the drum).

    Parameters:
      offset_dist: signed offset; positive = floor_narrower direction.
      sketch_at_bot: True -> sketch matches at r_bot (detail emboss);
                     False -> sketch matches at r_top (cavity).
      mapping: optional SoS mapping (theta_per_x, y_per_y, x_orig, y_orig).
      center_override, eps_override, margin: ignored.
    """
    R_drum = float(drum_obj.Diameter) / 2.0

    # --- Gather faces from input ---
    faces = []
    if hasattr(input_obj_or_wires, "Faces") and input_obj_or_wires.Faces:
        faces = list(input_obj_or_wires.Faces)
    elif hasattr(input_obj_or_wires, "Wires") and input_obj_or_wires.Wires:
        wires = [w for w in input_obj_or_wires.Wires if w.isClosed()]
        for w in wires:
            try:
                faces.append(Part.Face(w))
            except Exception:
                pass
    elif isinstance(input_obj_or_wires, list):
        for w in input_obj_or_wires:
            try:
                faces.append(Part.Face(w))
            except Part.OCCError:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: couldn't build face from wire.\n")
    if not faces:
        raise ValueError("No usable faces")

    # --- Projection helper ---
    if mapping is not None:
        theta_per_x, drum_y_per_y, x_origin, y_origin = mapping
        def project(p, r):
            sx = p.x - x_origin
            sy = p.y - y_origin
            theta = sx * theta_per_x
            y_drum = sy * drum_y_per_y
            return FreeCAD.Vector(r * math.sin(theta), y_drum,
                                   r * math.cos(theta))
    else:
        def project(p, r):
            theta = p.x / R_drum
            return FreeCAD.Vector(r * math.sin(theta), p.y,
                                   r * math.cos(theta))

    # --- Build one chunk per face's outer wire (holes handled by subtraction) ---
    chunk_solids = []
    for face in faces:
        outer_wire = face.OuterWire
        hole_wires = [w for w in face.Wires if not w.isSame(outer_wire)]

        outer_solid = _build_cone_frustum(
            outer_wire, drum_obj, r_top, r_bot, depth, offset_dist,
            sketch_at_bot, project, R_drum, is_hole=False,
        )
        if outer_solid is None:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: outer cone-frustum failed for a face.\n")
            continue

        # Cut holes (with inverted offset sign for proper draft direction)
        for hw in hole_wires:
            hole_solid = _build_cone_frustum(
                hw, drum_obj, r_top, r_bot, depth, -offset_dist,
                sketch_at_bot, project, R_drum, is_hole=True,
            )
            if hole_solid is None:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: hole cone-frustum failed.\n")
                continue
            try:
                cut_result = outer_solid.cut(hole_solid)
                if cut_result.Volume > 1e-6:
                    outer_solid = cut_result
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: hole cut failed: {0}\n".format(exc))

        chunk_solids.append(outer_solid)

    if not chunk_solids:
        raise RuntimeError("No chunk solids could be built")

    if len(chunk_solids) == 1:
        combined = chunk_solids[0]
    else:
        combined = chunk_solids[0]
        for s in chunk_solids[1:]:
            try:
                fused = combined.fuse(s)
                if fused.Volume > 1e-6:
                    combined = fused
            except Exception:
                pass

    try:
        combined = combined.removeSplitter()
    except Exception:
        pass

    if combined.Volume <= 1e-9:
        raise RuntimeError("Chunk has zero volume.")

    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: built cone-frustum chunk "
        "(vol={0:.3f}, valid={1})\n".format(
            combined.Volume, combined.isValid()))
    return combined


def _build_cone_frustum(wire, drum_obj, r_top, r_bot, depth, offset_dist,
                        sketch_at_bot, project, R_drum, is_hole=False):
    """Build one chunk by lofting a projected wire to an apex, then
    clipping with inner/outer cylinders to form a frustum with curved
    cylindrical top and bot faces.

    Steps:
      1. Project the wire onto the cylinder at the SKETCH-MATCHING radius
         (r_top for cavity, r_bot for detail emboss).
      2. Compute apex position: on the cookie's centerline (axially), at a
         radial position chosen so the cone wall makes the configured
         draft angle.
      3. Loft wire -> apex => cone solid
      4. Clip with outer cylinder (R_drum or r_top for details)
      5. Subtract inner cylinder (r_bot - margin)
    """
    try:
        # Step 1: project the wire to its sketch-matching radius
        # For cavity (sketch_at_top): sketch matches at r_top
        # For detail emboss (sketch_at_bot): sketch matches at r_bot
        if sketch_at_bot:
            r_sketch = r_bot
        else:
            r_sketch = r_top

        # Get the wire's points and project
        wire_pts_2d = _polyline_from_wire(wire, num_segments=128)
        if wire_pts_2d is None or len(wire_pts_2d) < 4:
            return None

        wire_pts_3d = [project(p, r_sketch) for p in wire_pts_2d]
        wire_3d = _wire_from_3d_points(wire_pts_3d)
        if wire_3d is None:
            return None

        # Step 2: compute apex position for the configured draft.
        # Centerline = midpoint of the wire in (theta, y) space.
        # Find theta_center, y_center from the wire's 2D bbox.
        x_min = min(p.x for p in wire_pts_2d)
        x_max = max(p.x for p in wire_pts_2d)
        y_min = min(p.y for p in wire_pts_2d)
        y_max = max(p.y for p in wire_pts_2d)
        x_center_2d = (x_min + x_max) / 2.0
        y_center_2d = (y_min + y_max) / 2.0

        # Project center to 3D at the sketch radius
        center_3d_at_sketch = project(
            FreeCAD.Vector(x_center_2d, y_center_2d, 0), r_sketch)

        # Max distance from center to wire (in 3D space) - this is `d`
        # for the draft angle calculation.
        max_dist = 0.0
        for p3 in wire_pts_3d:
            d = (p3 - center_3d_at_sketch).Length
            if d > max_dist:
                max_dist = d

        if max_dist < 1e-6:
            return None

        # offset_dist = depth * tan(angle), so tan(angle) = offset_dist/depth
        # Draft angle (positive value, absolute):
        tan_draft = abs(offset_dist) / depth
        if tan_draft < 1e-6:
            tan_draft = 1e-6

        # Radial distance from r_sketch to apex:
        # For floor_narrower (offset_dist > 0): apex is on the far side
        #   of the sketch radius from where we want the cone to open.
        #   For cavity (sketch at r_top): apex is TOWARD the axis (smaller r)
        #   For detail (sketch at r_bot): apex is TOWARD the axis too (deeper)
        # For rim_narrower (offset_dist < 0): apex is on the other side
        radial_dist_to_apex = max_dist / tan_draft

        # Direction: toward axis if offset_dist > 0 and sketch_at_top (cavity)
        # In both common cases (cavity floor_narrower, detail floor_narrower)
        # the apex goes TOWARD the drum axis.
        # For sketch_at_top + offset>0 (cavity floor_narrower): apex toward axis
        # For sketch_at_bot + offset>0 (detail floor_narrower): apex toward axis
        # (the cookie-floor side, beyond r_bot)
        # For sketch_at_top + offset<0 (rim_narrower): apex away from axis
        # For sketch_at_bot + offset<0 (rim_narrower): apex away from axis
        if offset_dist > 0:
            r_apex = r_sketch - radial_dist_to_apex
        else:
            r_apex = r_sketch + radial_dist_to_apex

        # Apex position: at the cookie's centerline (x,z) scaled to r_apex,
        # at the cookie's y_center.
        # Use the center_3d_at_sketch direction but at r_apex
        cs = center_3d_at_sketch
        cs_r = math.hypot(cs.x, cs.z)
        if cs_r < 1e-9:
            # Center is exactly on axis; apex at (0, y, 0)
            apex = FreeCAD.Vector(0, cs.y, 0)
        else:
            apex = FreeCAD.Vector(
                r_apex * cs.x / cs_r, cs.y, r_apex * cs.z / cs_r)

        # Step 3: loft wire to apex
        apex_vertex = Part.Vertex(apex)
        try:
            cone = Part.makeLoft([wire_3d, apex_vertex], True, False, False)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: cone loft failed: {0}\n".format(exc))
            return None

        if cone.Volume < 1e-6:
            return None

        # Step 4: clip with outer cylinder at r_top
        # Use a tall enough cylinder
        y_margin = 20.0
        y_axial_lo = y_min - y_margin
        y_axial_hi = y_max + y_margin
        # But we need drum coords; use mapped y_center range
        # The apex.y is already in drum y. Use it.
        cy_lo = cs.y - 50  # generous
        cy_hi = cs.y + 50
        outer_cyl = Part.makeCylinder(r_top, cy_hi - cy_lo,
                                       FreeCAD.Vector(0, cy_lo, 0),
                                       FreeCAD.Vector(0, 1, 0))
        try:
            clipped = cone.common(outer_cyl)
            if clipped.Volume < 1e-6:
                return None
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: outer clip failed: {0}\n".format(exc))
            return None

        # Step 5: subtract inner cylinder at r_bot
        if r_bot > 0.1:
            inner_cyl = Part.makeCylinder(r_bot, cy_hi - cy_lo,
                                           FreeCAD.Vector(0, cy_lo, 0),
                                           FreeCAD.Vector(0, 1, 0))
            try:
                frustum = clipped.cut(inner_cyl)
                if frustum.Volume < 1e-6:
                    return None
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: inner cut failed: {0}\n".format(exc))
                return None
        else:
            frustum = clipped

        return frustum
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: _build_cone_frustum exception: {0}\n".format(exc))
        return None


# === Conformal helpers ===

def _polyline_from_wire(wire, num_segments=128):
    """Discretize a closed wire to a uniform polyline (list of Vectors,
    last point equals first to close)."""
    try:
        wl = wire.Length
        if wl < 1e-6:
            return None
        pts = []
        for edge in wire.Edges:
            n = max(4, int(num_segments * edge.Length / wl) + 1)
            ep = edge.discretize(Number=n)
            if edge.Orientation == "Reversed":
                ep = list(reversed(ep))
            pts.extend(ep[:-1])
        # Close
        if (pts[-1] - pts[0]).Length > 1e-6:
            pts.append(pts[0])
        return pts
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: polyline discretize failed: {0}\n".format(exc))
        return None


def _wire_from_3d_points(pts3d):
    """Build a closed wire from a list of 3D points (last duplicates first)."""
    try:
        edges = []
        for i in range(len(pts3d) - 1):
            p1 = pts3d[i]
            p2 = pts3d[i + 1]
            if (p2 - p1).Length > 1e-9:
                edges.append(Part.LineSegment(p1, p2).toShape())
        if not edges:
            return None
        wire = Part.Wire(edges)
        if not wire.isClosed():
            return None
        return wire
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: 3D wire failed: {0}\n".format(exc))
        return None


# ===========================================================================
# Public entry points
# ===========================================================================

def build_cavity_solid(outline_obj, drum_obj, depth, angle_deg, direction):
    _debug_clear()
    if depth <= 0:
        raise ValueError("Cavity depth must be positive")
    if not (0 <= angle_deg < 90):
        raise ValueError("Draft angle must be in [0, 90) degrees")
    R_outer = float(drum_obj.Diameter) / 2.0
    R_inner = R_outer - depth
    if R_inner < 0.5:
        raise ValueError("Cavity depth too close to drum radius")
    offset_dist = depth * math.tan(math.radians(angle_deg))
    if direction == "rim_narrower":
        offset_dist = -offset_dist
    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: building cavity\n")

    # Check if outline is a Sketch_On_Surface - if so use its already-projected
    # wire on the drum surface directly (avoids re-projection issues).
    is_sos = (hasattr(outline_obj, "Sketch") and
              outline_obj.Sketch is not None and
              hasattr(outline_obj, "Shape"))

    if is_sos:
        # SoS produces a Compound with projected wires on the drum.
        sos_shape = outline_obj.Shape
        projected_wires = [w for w in sos_shape.Wires if w.isClosed()]
        if not projected_wires:
            raise ValueError("SoS shape has no projected wires.")
        FreeCAD.Console.PrintMessage(
            "RotaryMoulder: using {0} SoS-projected wire(s)\n".format(
                len(projected_wires)))
        return _build_cavity_from_projected_wires(
            projected_wires, drum_obj, R_outer, R_inner,
            depth, offset_dist,
        )
    else:
        # Non-SoS path: project manually via mapping
        flat_wire, label = _resolve_flat_outline(outline_obj)
        if flat_wire is None:
            raise ValueError("Could not find a closed wire in the outline.")
        FreeCAD.Console.PrintMessage(
            "RotaryMoulder: building cavity from {0}\n".format(label))
        shape = getattr(outline_obj, "Shape", None)
        if shape is None or not shape.Faces:
            input_for_chunk = [flat_wire]
        else:
            input_for_chunk = shape
        return _build_chunk(
            input_for_chunk, drum_obj,
            r_top=R_outer, r_bot=R_inner,
            depth=depth, offset_dist=offset_dist,
            sketch_at_bot=False,
            mapping=None,
        )


def _build_cavity_from_projected_wires(projected_wires, drum_obj,
                                        R_outer, R_inner, depth, offset_dist):
    """Build cavity solid using already-projected wires (from SoS).
    Each wire is on the drum surface. We loft each to an apex point
    inside the drum, clip with outer cylinder, subtract inner cylinder."""
    # Process outer (largest area) + holes
    # For wires on the drum surface, "area" doesn't work directly; sort by
    # 3D bounding box diagonal as a proxy for size.
    sized = []
    for w in projected_wires:
        bb = w.BoundBox
        diag = math.sqrt((bb.XMax-bb.XMin)**2 + (bb.YMax-bb.YMin)**2 +
                          (bb.ZMax-bb.ZMin)**2)
        sized.append((diag, w))
    sized.sort(reverse=True, key=lambda x: x[0])
    outer_wire = sized[0][1]
    hole_wires = [s[1] for s in sized[1:]]

    # Build outer frustum
    outer_frustum = _frustum_from_projected_wire(
        outer_wire, R_outer, R_inner, depth, offset_dist)
    if outer_frustum is None:
        raise RuntimeError("Outer frustum construction failed")

    # Build and subtract holes
    for hw in hole_wires:
        hole_frustum = _frustum_from_projected_wire(
            hw, R_outer, R_inner, depth, -offset_dist)
        if hole_frustum is None:
            continue
        try:
            outer_frustum = outer_frustum.cut(hole_frustum)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: hole cut failed: {0}\n".format(exc))

    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: cavity frustum vol={0:.3f} valid={1}\n".format(
            outer_frustum.Volume, outer_frustum.isValid()))
    return outer_frustum


def _solid_from_rim_floor_wires(rim_wire, floor_wire, R_rim, R_floor,
                                 debug_prefix="chunk"):
    """Build a closed solid from two wires on cylindrical surfaces:
      - rim_wire on cylinder at R_rim
      - floor_wire on cylinder at R_floor
    Side walls via loft, caps via generalFuse on cylinder faces, sewn
    into a closed solid. The two wires should be topologically matched
    (same number of edges) for the loft to give clean side faces.
    """
    try:
        # Side loft (shell)
        try:
            side_shell = Part.makeLoft(
                [rim_wire, floor_wire], False, False, False)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RM solid: side loft failed: {0}\n".format(exc))
            return None
        _debug_show(side_shell, debug_prefix + "_side_shell")

        # Caps via generalFuse on cylinder faces
        top_cap = _cyl_cap(rim_wire, R_rim)
        bot_cap = _cyl_cap(floor_wire, R_floor)
        if top_cap is None or bot_cap is None:
            FreeCAD.Console.PrintWarning(
                "RM solid: cap construction failed\n")
            return None
        _debug_show(top_cap, debug_prefix + "_top_cap")
        _debug_show(bot_cap, debug_prefix + "_bot_cap")
        FreeCAD.Console.PrintMessage(
            "RM solid: top cap area={0:.3f}, bot cap area={1:.3f}\n".format(
                top_cap.Area, bot_cap.Area))

        # Sew faces into a shell
        all_faces = [top_cap, bot_cap] + list(side_shell.Faces)
        cmp = Part.Compound(all_faces)
        cmp_sewed = cmp.copy()
        cmp_sewed.sewShape(0.01)
        if not cmp_sewed.Shells:
            FreeCAD.Console.PrintWarning(
                "RM solid: sewing did not produce a shell\n")
            return None
        shell = cmp_sewed.Shells[0]

        try:
            solid = Part.Solid(shell)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RM solid: solid build failed: {0}\n".format(exc))
            return None

        if solid.Volume < 0:
            try:
                solid = solid.reversed()
            except Exception:
                pass

        if abs(solid.Volume) < 1e-6:
            return None
        _debug_show(solid, debug_prefix + "_solid")
        FreeCAD.Console.PrintMessage(
            "RM solid: vol={0:.3f}, valid={1}\n".format(
                solid.Volume, solid.isValid()))
        return solid
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RM solid: failed: {0}\n".format(exc))
        return None


def _frustum_from_projected_wire(wire, R_outer, R_inner, depth, offset_dist,
                                  debug_prefix="cav"):
    """Build a cavity chunk by:
      1. Reading the rim wire's UV coords on the outer cylinder
      2. Building a floor wire in UV space (uniform scale-toward-center
         for proportional draft)
      3. Constructing floor wire on inner cylinder as proper arcs/lines
      4. Side loft (shell) between rim and floor wires
      5. Caps via generalFuse on cylinder faces
      6. Sew into closed solid
    """
    try:
        _debug_show(wire, debug_prefix + "_rim_wire")

        # Build outer cylinder face at origin so V = drum_y
        outer_cyl = Part.makeCylinder(
            R_outer, 200, FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0))
        outer_cyl_face = None
        for f in outer_cyl.Faces:
            if f.Surface.__class__.__name__ == "Cylinder":
                outer_cyl_face = f
                break
        if outer_cyl_face is None:
            FreeCAD.Console.PrintWarning(
                "RM frustum: outer cyl face not found\n")
            return None
        outer_surf = outer_cyl_face.Surface

        # Get UV bounds of rim wire on outer cylinder
        u_min = math.inf; u_max = -math.inf
        v_min = math.inf; v_max = -math.inf
        for edge in wire.Edges:
            n = max(8, int(edge.Length * 4))
            pts = edge.discretize(Number=n)
            for p in pts:
                u, v = outer_surf.parameter(p)
                if u < u_min: u_min = u
                if u > u_max: u_max = u
                if v < v_min: v_min = v
                if v > v_max: v_max = v
        FreeCAD.Console.PrintMessage(
            "RM frustum: rim UV bounds u=[{0:.4f}, {1:.4f}] "
            "v=[{2:.3f}, {3:.3f}]\n".format(u_min, u_max, v_min, v_max))

        # Compute UV center and max distance (in (R*u, v) space - arc-length, y)
        u_cen = (u_min + u_max) / 2.0
        v_cen = (v_min + v_max) / 2.0
        # max distance is half the diagonal in arc-length × y space
        du_max = R_outer * (u_max - u_cen)
        dv_max = v_max - v_cen
        max_dist = math.hypot(du_max, dv_max)
        FreeCAD.Console.PrintMessage(
            "RM frustum: max UV dist={0:.3f}, offset_dist={1:.4f}\n".format(
                max_dist, offset_dist))

        if max_dist < 1e-6:
            return None

        # Scale toward center: shrink so max-distance point moves in by offset_dist
        scale = (max_dist - offset_dist) / max_dist
        FreeCAD.Console.PrintMessage(
            "RM frustum: scale={0:.4f}\n".format(scale))
        if scale <= 0:
            FreeCAD.Console.PrintWarning(
                "RM frustum: scale non-positive; offset too large\n")
            return None

        # Floor wire UV bounds
        new_u_min = u_cen + (u_min - u_cen) * scale
        new_u_max = u_cen + (u_max - u_cen) * scale
        new_v_min = v_cen + (v_min - v_cen) * scale
        new_v_max = v_cen + (v_max - v_cen) * scale

        # Build floor wire generically: for each rim edge, scale its UV
        # samples toward (u_cen, v_cen), then build a BSpline on the inner
        # cylinder. This handles rectangles, circles, ovals, and any other
        # shape - the floor wire is topologically identical to the rim.
        def pt_on_cyl(theta, y, r):
            return FreeCAD.Vector(r * math.sin(theta),
                                   y,
                                   r * math.cos(theta))

        try:
            floor_edges_list = []
            for edge in wire.Edges:
                # Sample edge in UV space
                n_samples = max(16, int(edge.Length * 4))
                pts3d = edge.discretize(Number=n_samples)
                if edge.Orientation == "Reversed":
                    pts3d = list(reversed(pts3d))
                # Convert each 3D point to UV, scale, project to inner cyl
                scaled_pts3d = []
                for p in pts3d:
                    u, v = outer_surf.parameter(p)
                    new_u = u_cen + (u - u_cen) * scale
                    new_v = v_cen + (v - v_cen) * scale
                    scaled_pts3d.append(pt_on_cyl(new_u, new_v, R_inner))
                # Build BSpline edge through the scaled points
                bs = Part.BSplineCurve()
                bs.interpolate(scaled_pts3d)
                floor_edges_list.append(bs.toShape())
            floor_wire = Part.Wire(floor_edges_list)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RM frustum: floor wire build failed: {0}\n".format(exc))
            return None
        _debug_show(floor_wire, debug_prefix + "_floor_wire")

        if not floor_wire.isClosed():
            FreeCAD.Console.PrintWarning(
                "RM frustum: floor wire not closed\n")
            return None

        # Side loft + caps + sew + solid (shared helper)
        return _solid_from_rim_floor_wires(
            wire, floor_wire, R_outer, R_inner, debug_prefix=debug_prefix)
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: frustum build failed: {0}\n".format(exc))
        return None


def _cyl_cap(wire, radius, reverse_normal=False):
    """Build a cap face bounded by `wire` on a cylinder of given radius.

    Strategy:
      1. First try generalFuse to split the cylinder face by the wire.
         This produces a cap that lies EXACTLY on the cylinder surface
         (important for clean boolean with drum surface). But it can
         fail for certain wire shapes by returning negative-area faces
         that break volume calculations.
      2. If generalFuse gives a positive-area cap, use it.
      3. Otherwise fall back to Part.makeFilledFace which always
         produces a positive-area face but may be slightly recessed
         from the cylinder (typically ~0.03mm for small caps on large
         drums - usually not visible).
    """
    # Try generalFuse first
    gf_cap = _cyl_cap_via_generalfuse(wire, radius, reverse_normal=False)
    if gf_cap is not None and gf_cap.Area > 1e-6:
        # Positive area → good orientation. Apply reverse if requested.
        if reverse_normal:
            try:
                gf_cap = gf_cap.reversed()
            except Exception:
                pass
        return gf_cap

    # Fallback: makeFilledFace (always positive orientation)
    try:
        cap = Part.makeFilledFace(wire.Edges)
        if cap is None or not cap.isValid() or cap.Area < 1e-6:
            return None
        if reverse_normal:
            try:
                cap = cap.reversed()
            except Exception:
                pass
        return cap
    except Exception:
        return None


def _cyl_cap_via_generalfuse(wire, radius, reverse_normal=False):
    """Fallback: build cap by splitting the cylinder face via generalFuse.
    Used only when makeFilledFace fails."""
    try:
        cyl_solid = Part.makeCylinder(radius, 200,
                                       FreeCAD.Vector(0, 0, 0),
                                       FreeCAD.Vector(0, 1, 0))
        cyl_face = None
        for f in cyl_solid.Faces:
            if f.Surface.__class__.__name__ == "Cylinder":
                cyl_face = f
                break
        if cyl_face is None:
            return None
        fuse_result, _ = cyl_face.generalFuse([wire])
        if not hasattr(fuse_result, "Faces") or len(fuse_result.Faces) < 2:
            return None
        target_length = wire.Length

        def score(f):
            n_wires = len(f.Wires)
            try:
                outer_len = f.OuterWire.Length
            except Exception:
                outer_len = 0
            len_diff = abs(outer_len - target_length) / max(target_length, 1e-9)
            return len_diff + (10 if n_wires > 1 else 0)

        cap = min(fuse_result.Faces, key=score)
        if abs(cap.Area) < 1e-6:
            return None
        if reverse_normal:
            try:
                cap = cap.reversed()
            except Exception:
                pass
        return cap
    except Exception:
        return None
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RM _cyl_cap failed: {0}\n".format(exc))
        return None


def build_docker_pins(outline_obj, drum_obj, parent_cavity_floor_radius,
                       tip_diameter, angle_deg,
                       parent_cavity_outline=None):
    """Build docker pin solids from a sketch's vertex/point positions.

    Each point in the input sketch becomes one pin. Pins are truncated
    cones with a hemispherical (rounded) tip:
      - Tip diameter = `tip_diameter` (e.g. 0.2mm)
      - Tip is filleted into a hemisphere (radius = tip_diameter/2)
      - Pin height = cavity depth (tip reaches drum surface level)
      - Base diameter = tip_diameter + 2 * height * tan(draft_angle)
      - Base sits on cavity floor at parent_cavity_floor_radius
      - Pin axis points OUTWARD (away from drum axis)

    Returns a list of (pin_solid, False) tuples (is_hole=False) so it
    can be processed by _apply_detail_chunks with mode='emboss'.

    The sketch's points/vertices are read in flat 2D coords (sketch X,Y)
    and projected onto the drum surface using the parent cavity's SoS
    mapping - same mapping used for cavity details.
    """
    R_outer = float(drum_obj.Diameter) / 2.0
    r_floor = parent_cavity_floor_radius
    depth = R_outer - r_floor
    if depth <= 0:
        raise ValueError("Cavity floor must be inside drum")
    if tip_diameter <= 0:
        raise ValueError("Pin tip diameter must be positive")

    # Get parent cavity's SoS mapping (theta_per_x, y_per_y, origins)
    if parent_cavity_outline is None:
        raise ValueError(
            "Docker pins need a parent_cavity_outline for placement.")
    mapping = _get_sos_mapping(parent_cavity_outline, drum_obj)
    if mapping is None:
        raise ValueError(
            "Could not read parent cavity SoS mapping for docker pins.")
    theta_per_x, y_per_y, x_origin, y_origin = mapping

    # Collect 2D point positions from the input shape
    # Accept: explicit vertices, Sketch vertices, points
    points_2d = []
    shape = getattr(outline_obj, "Shape", None)
    sketch = getattr(outline_obj, "Sketch", None)
    if sketch is not None and hasattr(sketch, "Shape"):
        shape = sketch.Shape

    if shape is not None:
        # Use vertex positions from the shape
        for v in shape.Vertexes:
            points_2d.append((v.Point.x, v.Point.y))

    if not points_2d:
        raise ValueError(
            "Docker outline must contain points/vertices.")

    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: building {0} docker pin(s)\n".format(len(points_2d)))

    # Compute pin geometry
    tan_a = math.tan(math.radians(angle_deg))
    pin_height = depth  # tip at drum surface, base at cavity floor
    tip_r = tip_diameter / 2.0
    base_r = tip_r + pin_height * tan_a

    # Pin construction: cone from cavity floor upward + sphere at tip.
    # The pin must fit ENTIRELY WITHIN the cavity volume (from r_floor
    # to drum surface) so that cut-from-master and fuse-to-drum
    # operations work cleanly. We use slight retraction (pin tip stops
    # just BEFORE drum surface) to avoid tangent contact at the top.
    retract = 0.05  # retract from drum surface by 0.05mm
    pin_eff_height = pin_height - retract

    # Cone goes from base (at r_floor) up by (pin_eff_height - tip_r)
    # so the sphere center sits at (pin_height - retract - tip_r) from
    # the base, and the sphere top is at (pin_height - retract).
    cone_height = pin_eff_height - tip_r
    if cone_height < 0:
        cone_height = 0

    pins = []
    for (sx, sy) in points_2d:
        # Project to drum: sketch X -> theta, sketch Y -> drum Y
        theta = (sx - x_origin) * theta_per_x
        drum_y = (sy - y_origin) * y_per_y
        # Pin axis direction: outward radial from drum axis at angle theta
        axis_dir = FreeCAD.Vector(math.sin(theta), 0, math.cos(theta))
        # Base center: on cavity floor surface
        base_center = FreeCAD.Vector(
            r_floor * math.sin(theta), drum_y,
            r_floor * math.cos(theta))

        try:
            # Build truncated cone (base wider, top narrower)
            if cone_height > 1e-6:
                cone = Part.makeCone(
                    base_r, tip_r, cone_height,
                    base_center, axis_dir)
            else:
                cone = None
            # Dome at cone top, fully inside cavity (just below drum surface)
            dome_center = base_center + axis_dir * cone_height
            sphere = Part.makeSphere(tip_r, dome_center)
            # Fuse cone + sphere → mushroom-shaped pin
            if cone is not None:
                pin = cone.fuse(sphere)
            else:
                pin = sphere
            # Clean up
            try:
                pin = pin.removeSplitter()
            except Exception:
                pass
            pins.append((pin, False))
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: pin at ({0:.2f},{1:.2f}) failed: {2}\n"
                .format(sx, sy, exc))

    return pins


def build_detail_solid(outline_obj, drum_obj, parent_cavity_floor_radius,
                       depth, angle_deg, direction, mode,
                       parent_cavity_outline=None):
    """Build detail chunks for an outline using the conformal approach
    with proper 2D wire offsetting in flat sketch space.

    Returns list of (chunk, is_hole) tuples (with is_hole always False
    since holes are pre-cut from the outer chunks).

    Strategy:
      1. For each face of the input outline:
         a. Take the OUTER wire in flat 2D coords
         b. Apply 2D offset via makeOffset2D (handles concave regions
            correctly with perpendicular offset on every wall section).
         c. Project the original wire to cylinder at r_floor (rim).
         d. Project the offset wire to cylinder at r_other (floor).
         e. Build the chunk: side loft + caps + sew.
         f. Do the same for each hole wire (with opposite offset sign)
            and cut from the outer chunk.

    The 2D offset approach gives:
      - Perpendicular offset on every wall (correct draft on concave
        regions like S, C, A's inner cuts)
      - Locally constant draft angle on every wall
    """
    if depth <= 0:
        raise ValueError("Detail depth must be positive")
    if not (0 <= angle_deg < 90):
        raise ValueError("Draft angle must be in [0, 90) degrees")

    if mode not in ("engrave", "emboss"):
        raise ValueError("Mode must be 'engrave' or 'emboss'")

    offset_dist = depth * math.tan(math.radians(angle_deg))
    if direction == "rim_narrower":
        offset_dist = -offset_dist
    # offset_dist > 0 means: in _build_detail_chunk, the floor wire
    # (at r_other) is SMALLER than the rim wire (at cavity floor level).
    # For engrave: floor wire = indent bottom. Floor smaller = indent
    #              narrower at bottom = floor_narrower ✓
    # For emboss: floor wire = bump top. Floor smaller = bump top
    #             narrower than base = rim_narrower (release-friendly) ✓
    # So in BOTH modes, positive offset_dist produces the release-friendly
    # taper. No mode-based flip needed.

    # Get parent cavity's SoS mapping
    if parent_cavity_outline is None:
        raise ValueError(
            "Detail requires a parent_cavity_outline for placement.")
    mapping = _get_sos_mapping(parent_cavity_outline, drum_obj)
    if mapping is None:
        raise ValueError(
            "Could not derive SoS mapping from parent cavity outline.")
    theta_per_x, y_per_y, x_origin, y_origin = mapping
    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: detail using parent SoS mapping "
        "(theta/x={0:.4f}, y/y={1:.4f})\n".format(theta_per_x, y_per_y))

    # Detail radii. Sketch matches at r_floor; the "other" radius depends
    # on mode.
    r_floor = parent_cavity_floor_radius
    if mode == "engrave":
        r_other = r_floor - depth
        if r_other < 0.5:
            raise ValueError("Engrave depth too close to drum axis")
    else:  # emboss
        r_other = r_floor + depth

    # Projection helper
    def project_to_cyl(p, r):
        sx = p.x - x_origin
        sy = p.y - y_origin
        theta = sx * theta_per_x
        drum_y = sy * y_per_y
        return FreeCAD.Vector(r * math.sin(theta), drum_y,
                              r * math.cos(theta))

    # Get the input shape's faces (or fall back to wires)
    shape = getattr(outline_obj, "Shape", None)
    if hasattr(outline_obj, "Sketch") and outline_obj.Sketch is not None:
        shape = outline_obj.Sketch.Shape

    if shape is not None and shape.Faces:
        face_entries = []
        for face in shape.Faces:
            outer_w = face.OuterWire
            hole_ws = [w for w in face.Wires if not w.isSame(outer_w)]
            face_entries.append((outer_w, hole_ws))
        FreeCAD.Console.PrintMessage(
            "RotaryMoulder: detail has {0} face(s)\n".format(
                len(face_entries)))
    else:
        wires, _ = _resolve_flat_outline_all(outline_obj)
        if not wires:
            raise ValueError("Detail outline has no closed wires.")
        face_entries = [(w, []) for w in wires]

    chunks = []
    for face_idx, (outer_w, hole_ws) in enumerate(face_entries):
        # Build the outer chunk: rim from outer_w, floor from offset of outer_w
        outer_chunk = _build_detail_chunk(
            outer_w, offset_dist, r_floor, r_other,
            project_to_cyl,
            debug_prefix="det_f{0}_outer".format(face_idx),
        )
        if outer_chunk is None:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: detail face {0} outer chunk failed\n".format(
                    face_idx))
            continue

        # Cut each hole with REVERSED offset sign (so the hole's walls
        # slope the same way as the outer's walls relative to release dir)
        for hole_idx, hw in enumerate(hole_ws):
            hole_chunk = _build_detail_chunk(
                hw, -offset_dist, r_floor, r_other,
                project_to_cyl,
                debug_prefix="det_f{0}_h{1}".format(face_idx, hole_idx),
            )
            if hole_chunk is None:
                continue
            try:
                cut_result = outer_chunk.cut(hole_chunk)
                if cut_result.Volume > 1e-6:
                    outer_chunk = cut_result
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: hole cut failed: {0}\n".format(exc))

        if outer_chunk.Volume > 1e-6:
            chunks.append((outer_chunk, False))

    if not chunks:
        raise RuntimeError("No detail chunks could be built")
    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: built {0} detail chunk(s)\n".format(len(chunks)))
    return chunks




def _build_detail_chunk(flat_wire, offset_dist, r_rim, r_floor,
                         project_func, debug_prefix="det"):
    """Build a single detail chunk using a uniform-sampling approach
    that gives ONE smooth side surface (no diagonal patch boundaries).

    Steps:
      1. Offset flat_wire in 2D by offset_dist (proper perpendicular
         offset via makeOffset2D - handles concave regions).
      2. Sample BOTH the rim flat wire AND the offset floor flat wire
         uniformly along their lengths (200 points each).
      3. Project both sample sets onto cylinders at r_rim and r_floor.
      4. Build each 3D wire as a SINGLE periodic BSpline through its
         points - this gives single-edge wires.
      5. Loft between rim_wire and floor_wire → produces ONE smooth
         BSpline side surface with NO internal patch boundaries.
      6. Caps via generalFuse on cylinder faces (single edge to split).
      7. Sew faces into a closed solid.
    """
    # Step 1: 2D offset
    try:
        offset_wire_flat = _shrink_wire_2d(flat_wire, abs(offset_dist),
                                            shrink=(offset_dist > 0))
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: 2D offset failed: {0}\n".format(exc))
        return None
    if offset_wire_flat is None:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: 2D offset returned None\n")
        return None

    _debug_show(flat_wire, debug_prefix + "_flat_rim")
    _debug_show(offset_wire_flat, debug_prefix + "_flat_floor")

    # Step 2: uniform sampling along each wire's perimeter
    n_samples = 400

    def sample_wire_uniform(wire, n):
        """Sample n points uniformly along wire's perimeter (does not
        include closing duplicate - the BSpline interpolation with
        PeriodicFlag handles closure)."""
        L = wire.Length
        if L < 1e-9:
            return None
        try:
            edges = wire.OrderedEdges
        except Exception:
            edges = list(wire.Edges)
        cum = [0.0]
        for e in edges:
            cum.append(cum[-1] + e.Length)
        pts = []
        for i in range(n):
            s = (i / n) * L
            for j in range(len(edges)):
                if cum[j + 1] >= s - 1e-9:
                    edge = edges[j]
                    local_s = s - cum[j]
                    if edge.Orientation == "Reversed":
                        t = edge.LastParameter - (
                            local_s / edge.Length
                        ) * (edge.LastParameter - edge.FirstParameter)
                    else:
                        t = edge.FirstParameter + (
                            local_s / edge.Length
                        ) * (edge.LastParameter - edge.FirstParameter)
                    pts.append(edge.valueAt(t))
                    break
        return pts

    rim_pts_2d = sample_wire_uniform(flat_wire, n_samples)
    if rim_pts_2d is None:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: rim sampling failed\n")
        return None

    # For each rim point, find the closest point on the OFFSET wire (the
    # floor outline in 2D space). This gives proper geometric
    # correspondence: each rim point maps to where it would project
    # perpendicularly inward to the floor wire. This handles corners and
    # length differences correctly - the linear interpolation between
    # corresponding points gives a clean straight chamfer wall.
    floor_pts_2d = []
    for rim_pt in rim_pts_2d:
        # Convert to a Vertex shape to use distToShape
        try:
            v = Part.Vertex(rim_pt)
            dist, pts, _ = v.distToShape(offset_wire_flat)
            # pts is a list of (point_on_v, point_on_wire) pairs
            floor_pt = pts[0][1]  # closest point on offset wire
            floor_pts_2d.append(FreeCAD.Vector(
                floor_pt.x, floor_pt.y, floor_pt.z))
        except Exception:
            # Fallback: just use the rim point (wall will be vertical
            # at this position)
            floor_pts_2d.append(rim_pt)

    # Filter consecutive duplicates with awareness that the rim AND
    # floor must both have unique consecutive points at EVERY blended
    # level. At sharp corners, multiple rim points map to one floor
    # corner point - we collapse those rim points to one (using the
    # first), and similarly for floor.
    # Key: skip a pair if EITHER rim[i]≈rim[i-1] OR floor[i]≈floor[i-1].
    # Tolerance is larger (1e-5) to ensure no near-duplicates remain that
    # could fail at intermediate levels.
    rim_clean = [rim_pts_2d[0]]
    floor_clean = [floor_pts_2d[0]]
    tol = 1e-5
    for i in range(1, len(rim_pts_2d)):
        r = rim_pts_2d[i]
        f = floor_pts_2d[i]
        if ((r - rim_clean[-1]).Length > tol and
                (f - floor_clean[-1]).Length > tol):
            rim_clean.append(r)
            floor_clean.append(f)
    # Also check the wrap-around closing pair: if last pair is too close
    # to first, drop the last.
    while len(rim_clean) > 4 and (
        (rim_clean[-1] - rim_clean[0]).Length < tol or
        (floor_clean[-1] - floor_clean[0]).Length < tol
    ):
        rim_clean.pop()
        floor_clean.pop()
    rim_pts_2d = rim_clean
    floor_pts_2d = floor_clean
    if len(rim_pts_2d) < 8:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: too few points after cleaning\n")
        return None
    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: detail using {0} corresponding rim/floor points\n"
        .format(len(rim_pts_2d)))

    # Step 3: project to cylinders
    rim_pts_3d = [project_func(p, r_rim) for p in rim_pts_2d]
    floor_pts_3d = [project_func(p, r_floor) for p in floor_pts_2d]

    # Build intermediate wires at evenly-spaced heights between rim and
    # floor. Each intermediate wire's 2D shape is a linear interpolation
    # between rim's 2D shape and floor's 2D shape (the corresponding
    # closest-point on the offset wire). Projecting to the corresponding
    # intermediate radius gives wires that constrain the loft to flat-
    # chamfered side walls. More intermediate wires → straighter chamfer.
    n_intermediate = 4

    n = len(rim_pts_2d)  # rim and floor are now aligned same-length pairs

    # Build all wires (rim + intermediates + floor)
    all_wires_3d = []
    n_total = n_intermediate + 2  # including rim and floor
    for level in range(n_total):
        t = level / (n_total - 1)  # 0 at rim, 1 at floor
        r_level = r_rim + (r_floor - r_rim) * t
        pts_2d_level = [
            rim_pts_2d[i] + (floor_pts_2d[i] - rim_pts_2d[i]) * t
            for i in range(n)
        ]
        pts_3d_level = [project_func(p, r_level) for p in pts_2d_level]
        # Clean duplicates with same tolerance used for 2D cleaning, and
        # also check wrap-around for the periodic BSpline.
        cleaned_3d = [pts_3d_level[0]]
        for p in pts_3d_level[1:]:
            if (p - cleaned_3d[-1]).Length > 1e-5:
                cleaned_3d.append(p)
        while len(cleaned_3d) > 4 and (
                cleaned_3d[-1] - cleaned_3d[0]).Length < 1e-5:
            cleaned_3d.pop()
        if len(cleaned_3d) < 4:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: level {0} too few points\n".format(level))
            return None
        # Build periodic BSpline
        try:
            bs = Part.BSplineCurve()
            bs.interpolate(cleaned_3d, PeriodicFlag=True)
            wire_level = Part.Wire([bs.toShape()])
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: level {0} BSpline failed: {1}\n"
                .format(level, exc))
            return None
        if not wire_level.isClosed():
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: level {0} wire not closed\n".format(level))
            return None
        all_wires_3d.append((wire_level, r_level))

    rim_wire_3d = all_wires_3d[0][0]
    floor_wire_3d = all_wires_3d[-1][0]
    intermediate_wires = [w for w, r in all_wires_3d[1:-1]]
    _debug_show(rim_wire_3d, debug_prefix + "_rim_3d")
    _debug_show(floor_wire_3d, debug_prefix + "_floor_3d")
    for i, w in enumerate(intermediate_wires):
        _debug_show(w, debug_prefix + "_intermediate_{0}".format(i))

    # Side loft through ALL wires (rim, intermediates, floor) - forces
    # the surface to pass through every wire, giving flat-chamfered walls
    # in multiple sections. This gives clean visible side walls; the
    # boolean with the drum may show some patch-boundary noise but the
    # geometry is functionally correct.
    try:
        all_wires_for_loft = [w for w, r in all_wires_3d]
        side_shell = Part.makeLoft(
            all_wires_for_loft, False, False, False)
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: multi-level loft failed: {0}\n".format(exc))
        return None
    _debug_show(side_shell, debug_prefix + "_side_shell")

    # Caps via generalFuse on cylinder faces. We try BOTH orientations
    # for each cap (4 combinations) and pick the one that produces a
    # valid solid with sensible volume. generalFuse cap orientation is
    # unpredictable, especially for letters like 'M' with sharp internal
    # corners.
    top_cap_base = _cyl_cap(rim_wire_3d, r_rim)
    bot_cap_base = _cyl_cap(floor_wire_3d, r_floor)
    if top_cap_base is None or bot_cap_base is None:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: cap construction failed\n")
        return None

    # Compute expected bbox volume from the rim wire's BBox + depth
    expected_bb = rim_wire_3d.BoundBox
    expected_vol_max = max(
        expected_bb.XLength, expected_bb.YLength, expected_bb.ZLength
    ) * max(expected_bb.YLength, expected_bb.ZLength
    ) * abs(r_rim - r_floor) * 2.0  # generous upper bound

    best_solid = None
    best_score = float('inf')
    for top_rev in (False, True):
        for bot_rev in (False, True):
            try:
                top_cap = top_cap_base.reversed() if top_rev else top_cap_base
                bot_cap = bot_cap_base.reversed() if bot_rev else bot_cap_base
                test_faces = [top_cap, bot_cap] + list(side_shell.Faces)
                test_cmp = Part.Compound(test_faces)
                test_sewed = test_cmp.copy()
                test_sewed.sewShape(0.01)
                if not test_sewed.Shells:
                    continue
                test_shell = test_sewed.Shells[0]
                if not test_shell.isClosed():
                    continue
                test_solid = Part.Solid(test_shell)
                if test_solid.Volume < 0:
                    test_solid = test_solid.reversed()
                if abs(test_solid.Volume) < 1e-6:
                    continue
                # Apply removeSplitter to fix face parameterization issues
                try:
                    cleaned = test_solid.removeSplitter()
                    if cleaned.Volume > 1e-6:
                        test_solid = cleaned
                except Exception:
                    pass
                # Score: prefer solids whose volume is close to the
                # expected value (cap_area × depth). We DON'T reject
                # by volume - rejection caused M to never be built.
                # Instead, we accept any valid solid and rank by closeness
                # to expected volume.
                cap_area_est = 0
                cap_count = 0
                for f in test_solid.Faces:
                    surf_name = f.Surface.__class__.__name__
                    if surf_name in ("Cylinder", "Plane"):
                        cap_area_est += abs(f.Area)
                        cap_count += 1
                if cap_count > 0:
                    cap_area_est /= cap_count
                depth = abs(r_rim - r_floor)
                expected_vol = cap_area_est * depth
                # Score: distance from expected. Lower is better.
                score = abs(abs(test_solid.Volume) - expected_vol)
                if not test_solid.isValid():
                    score += 1e6
                FreeCAD.Console.PrintMessage(
                    "RM: orient {0},{1}: vol={2:.3f}, expected={3:.3f}, "
                    "score={4:.3f}, valid={5}\n".format(
                        top_rev, bot_rev, test_solid.Volume, expected_vol,
                        score, test_solid.isValid()))
                if score < best_score:
                    best_score = score
                    best_solid = test_solid
            except Exception:
                continue

    if best_solid is None:
        FreeCAD.Console.PrintWarning(
            "RotaryMoulder: no valid cap orientation produced a solid\n")
        return None
    solid = best_solid

    # Clean up redundant edges introduced by sewing
    try:
        cleaned = solid.removeSplitter()
        if cleaned.Volume > 1e-6:
            solid = cleaned
    except Exception:
        pass
    _debug_show(solid, debug_prefix + "_solid")
    FreeCAD.Console.PrintMessage(
        "RotaryMoulder: detail chunk vol={0:.3f}, valid={1}\n".format(
            solid.Volume, solid.isValid()))
    return solid


def _shrink_wire_2d(wire, offset, shrink=True):
    """Apply a 2D offset to a closed wire by `offset` (positive). If
    shrink=True, the result is INSIDE the original; otherwise OUTSIDE.

    Tries both makeOffset2D sign conventions (since winding direction
    affects which sign shrinks), and picks the right one by comparing
    bounding-box areas. Rejects degenerate results where the offset
    wire's perimeter grew (indicates self-intersection in narrow regions).
    """
    if abs(offset) < 1e-9:
        return Part.Wire(wire.Edges)

    candidates = []
    for sign in (-1, 1):
        for join in (2, 0):  # 2 = intersection (sharp), 0 = arc
            try:
                result = wire.makeOffset2D(
                    sign * offset, join=join, fill=False,
                    openResult=False, intersection=False,
                )
                if result.ShapeType == "Wire" and result.isClosed():
                    candidates.append(result)
                else:
                    for w in getattr(result, "Wires", []):
                        if w.isClosed():
                            candidates.append(w)
            except Exception:
                continue

    if not candidates:
        return None

    orig_length = wire.Length
    obb = wire.BoundBox
    o_area = (obb.XMax - obb.XMin) * (obb.YMax - obb.YMin)

    # Pick candidate matching the shrink/grow direction.
    # CRITICAL: for shrink mode, the perimeter MUST decrease. If it
    # increases, the offset has produced a self-intersecting/folded
    # result (happens with thin features whose opposite sides converge).
    # Such candidates are degenerate and must be rejected.
    best = None
    for c in candidates:
        cbb = c.BoundBox
        c_area = (cbb.XMax - cbb.XMin) * (cbb.YMax - cbb.YMin)
        is_shrunk = c_area < o_area
        if is_shrunk != shrink:
            continue
        # Sanity: shrunk wire perimeter should be <= original. Allow 5%
        # tolerance for cases where offset rounds corners.
        if shrink and c.Length > orig_length * 1.05:
            FreeCAD.Console.PrintMessage(
                "RotaryMoulder: rejecting degenerate offset "
                "(orig_len={0:.2f}, offset_len={1:.2f})\n"
                .format(orig_length, c.Length))
            continue
        if best is None:
            best = c
        else:
            bbb = best.BoundBox
            b_area = (bbb.XMax - bbb.XMin) * (bbb.YMax - bbb.YMin)
            if abs(c_area - o_area) < abs(b_area - o_area):
                best = c
    return best


# ===========================================================================
# Apply cavity + details to a result shape
# ===========================================================================

def _apply_detail_chunks(result, detail_chunks, mode, placement=None):
    """Apply (chunk, is_hole) details to `result`. With sanity check:
    boolean results are committed only if they have positive volume.
    Accepts compound results that may need cleanup.

    Optimization: for ENGRAVE mode (cut multiple chunks from result),
    we batch all the non-hole chunks into one compound and do ONE cut.
    This avoids OCC degrading the topology of `result` after each
    successive cut, which caused later chunks to silently fail when
    the first chunk had a complex shape (e.g. letter M)."""
    mode_engrave = (mode == "engrave")

    # Apply placement (if any) to all chunks once
    placed_chunks = []
    for chunk, is_hole in detail_chunks:
        if placement is not None:
            c = chunk.copy()
            c.Placement = placement.multiply(c.Placement)
        else:
            c = chunk
        placed_chunks.append((c, is_hole))

    # Split into two groups based on the cut/fuse direction:
    # For ENGRAVE: non-holes cut from result; holes fuse into result.
    # For EMBOSS: non-holes fuse into result; holes cut from result.
    cuts = []
    fuses = []
    for c, is_hole in placed_chunks:
        if mode_engrave:
            if is_hole:
                fuses.append(c)
            else:
                cuts.append(c)
        else:
            if is_hole:
                cuts.append(c)
            else:
                fuses.append(c)

    # Batch the cuts. Combine all cut chunks into one solid via multiFuse
    # (Part.Compound doesn't work well for boolean cuts - OCC may treat
    # the compound as a single shape with degenerate topology). A fused
    # solid is well-defined for cut operations.
    if cuts:
        try:
            if len(cuts) == 1:
                combined_cut = cuts[0]
            else:
                # multiFuse merges multiple solids into one cleanly
                try:
                    combined_cut = cuts[0].multiFuse(cuts[1:])
                except Exception:
                    # Fallback: iterative fuse
                    combined_cut = cuts[0]
                    for c in cuts[1:]:
                        combined_cut = combined_cut.fuse(c)
                try:
                    combined_cut = combined_cut.removeSplitter()
                except Exception:
                    pass
            new_result = result.cut(combined_cut)
            if new_result is not None and new_result.Volume > 1e-6:
                try:
                    new_result = new_result.removeSplitter()
                except Exception:
                    pass
                result = new_result
            else:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: batched detail cut produced empty "
                    "result; falling back to per-chunk\n")
                # Fallback: one-by-one (with the corruption risk)
                for c in cuts:
                    try:
                        nr = result.cut(c)
                        if nr is not None and nr.Volume > 1e-6:
                            try:
                                nr = nr.removeSplitter()
                            except Exception:
                                pass
                            result = nr
                    except Exception as exc:
                        FreeCAD.Console.PrintWarning(
                            "RotaryMoulder: detail cut failed: {0}\n"
                            .format(exc))
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: batched detail cut failed: {0}\n"
                .format(exc))

    # Batch the fuses. Embossed detail chunks (e.g. separate letters) do
    # NOT touch each other, so the right operation is a SINGLE multiFuse
    # that includes the base result together with every chunk:
    #     result.multiFuse([letter1, letter2, ...])
    # This is more reliable than first merging the letters together and
    # then fusing onto the base: when non-touching solids are pre-merged,
    # OCC can silently drop one whose side walls are nearly tangent to a
    # neighbour's (observed: the 'N' in ZAANDAM disappearing). Fusing all
    # solids against the base in one operation keeps each one anchored.
    #
    # To detect a dropped chunk we count SOLIDS, not volume. A correct
    # emboss fuse of N separate non-touching chunks onto a single base
    # solid yields exactly 1 solid (everything connected) - but if a chunk
    # is dropped the count is unaffected, so instead we compare the fused
    # result's volume against the simple lower bound: it must be at least
    # the base volume plus the SMALLEST chunk's volume (i.e. at least one
    # full chunk's worth beyond base would be missing if one vanished).
    # This check is only meaningful with multiple chunks; a single chunk
    # is trusted as-is (its overlap with the base can legitimately make
    # the net volume gain small, e.g. a broad shallow raised panel).
    if fuses:

        def _commit(shape):
            try:
                return shape.removeSplitter()
            except Exception:
                return shape

        fused_ok = False
        try:
            new_result = result.multiFuse(fuses)
            if new_result is not None and new_result.Volume > 1e-6:
                if len(fuses) == 1:
                    # Single chunk: trust it (no neighbour to drop against).
                    result = _commit(new_result)
                    fused_ok = True
                else:
                    # Multi-chunk: detect a dropped chunk. A dropped chunk
                    # means a whole chunk's worth of material is missing.
                    # Use a lenient floor: require the gain to be at least
                    # the summed chunk volume minus one full smallest chunk
                    # (covers legitimate floor overlap) but flag larger
                    # shortfalls. The per-chunk fallback below guarantees
                    # correctness if this trips, so a false trip is only a
                    # minor performance cost, never a wrong result.
                    base_vol = result.Volume if result is not None else 0.0
                    chunk_vols = [c.Volume for c in fuses]
                    sum_chunk_vol = sum(chunk_vols)
                    min_chunk_vol = min(chunk_vols) if chunk_vols else 0.0
                    gain = new_result.Volume - base_vol
                    # Flag only if we're short by more than ~one whole chunk.
                    if gain >= sum_chunk_vol - 0.9 * min_chunk_vol:
                        result = _commit(new_result)
                        fused_ok = True
                    else:
                        FreeCAD.Console.PrintWarning(
                            "RotaryMoulder: batched emboss fuse gain "
                            "{0:.1f} below expected ~{1:.1f}; a detail may "
                            "have been dropped - retrying per-chunk\n".format(
                                gain, sum_chunk_vol))
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: batched emboss multiFuse failed: {0}\n"
                .format(exc))

        if not fused_ok:
            # Per-chunk fallback with verification. Fuse each chunk
            # individually; if a fuse doesn't increase the volume, retry
            # that chunk once after a removeSplitter on the running result.
            for idx, c in enumerate(fuses):
                before = result.Volume
                applied = False
                for attempt in range(2):
                    try:
                        nr = result.fuse(c)
                        if nr is not None and nr.Volume > before + 1e-6:
                            result = _commit(nr)
                            applied = True
                            break
                    except Exception as exc:
                        FreeCAD.Console.PrintWarning(
                            "RotaryMoulder: detail fuse (chunk {0}, "
                            "attempt {1}) failed: {2}\n".format(
                                idx, attempt, exc))
                    # Clean the running result before retrying
                    result = _commit(result)
                if not applied:
                    FreeCAD.Console.PrintWarning(
                        "RotaryMoulder: detail chunk {0} could not be "
                        "fused (likely coincident geometry)\n".format(idx))
    return result


def _apply_cavity_with_details(result, drum_obj, cavity_chunk,
                                cavity_depth, fillet_radius, details_list,
                                cavity_outline=None, dockers_list=None):
    chunk = cavity_chunk
    if fillet_radius > 0:
        R_inner = float(drum_obj.Diameter) / 2.0 - cavity_depth
        floor_edges = []
        for edge in chunk.Edges:
            pts = edge.discretize(Number=5)
            if all(abs(math.hypot(p.x, p.z) - R_inner) < 0.5 for p in pts):
                floor_edges.append(edge)
        if floor_edges:
            try:
                chunk = chunk.makeFillet(fillet_radius, floor_edges)
            except Part.OCCError as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: fillet failed: {0}\n".format(exc))
    try:
        result = result.cut(chunk)
    except Part.OCCError as exc:
        FreeCAD.Console.PrintError(
            "RotaryMoulder: cavity cut failed: {0}\n".format(exc))
        return result

    R_floor = float(drum_obj.Diameter) / 2.0 - cavity_depth
    for det in (details_list or []):
        if det is None or not hasattr(det, "Proxy"):
            continue
        if getattr(det.Proxy, "Type", "") != "RotaryMoulder::CavityDetail":
            continue
        if det.Outline is None:
            continue
        try:
            detail_chunks = build_detail_solid(
                det.Outline, drum_obj,
                parent_cavity_floor_radius=R_floor,
                depth=float(det.Depth),
                angle_deg=float(det.DraftAngle),
                direction=str(det.DraftDirection),
                mode=str(det.Mode),
                parent_cavity_outline=cavity_outline,
            )
        except (ValueError, RuntimeError) as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: detail '{0}' failed: {1}\n".format(
                    det.Label, exc))
            continue
        result = _apply_detail_chunks(result, detail_chunks, str(det.Mode))

    # Apply docker pins (always emboss-style: fuse pin to drum so it
    # protrudes INTO the cavity from the floor toward drum surface)
    for dck in (dockers_list or []):
        if dck is None or not hasattr(dck, "Proxy"):
            continue
        if getattr(dck.Proxy, "Type", "") != "RotaryMoulder::CavityDockers":
            continue
        if dck.Outline is None:
            continue
        try:
            pin_chunks = build_docker_pins(
                dck.Outline, drum_obj,
                parent_cavity_floor_radius=R_floor,
                tip_diameter=float(dck.TipDiameter),
                angle_deg=float(dck.DraftAngle),
                parent_cavity_outline=cavity_outline,
            )
        except (ValueError, RuntimeError) as exc:
            FreeCAD.Console.PrintWarning(
                "RotaryMoulder: dockers '{0}' failed: {1}\n".format(
                    dck.Label, exc))
            continue
        result = _apply_detail_chunks(result, pin_chunks, "emboss")
    return result


# ===========================================================================
# Document objects
# ===========================================================================

class Drum:
    Type = "RotaryMoulder::Drum"

    def __init__(self, obj):
        obj.addProperty("App::PropertyLength", "Diameter", "Drum",
                        "Outer diameter").Diameter = 100.0
        obj.addProperty("App::PropertyLength", "Length", "Drum",
                        "Axial length").Length = 200.0
        obj.addProperty("App::PropertyLength", "WallThickness", "Drum",
                        "Wall thickness (0 = solid)").WallThickness = 0.0
        obj.Proxy = self

    def execute(self, obj):
        r = float(obj.Diameter) / 2.0
        L = float(obj.Length)
        if r <= 0 or L <= 0:
            return
        outer = Part.makeCylinder(
            r, L, FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 1, 0))
        wall = float(obj.WallThickness)
        if wall > 0 and wall < r:
            inner = Part.makeCylinder(
                r - wall, L, FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 1, 0))
            outer = outer.cut(inner)
        obj.Shape = outer


class DrumViewProvider:
    def __init__(self, vobj): vobj.Proxy = self
    def getIcon(self): return ""
    def __getstate__(self): return None
    def __setstate__(self, _state): return None


class DraftedCavity:
    Type = "RotaryMoulder::DraftedCavity"

    def __init__(self, obj):
        obj.addProperty("App::PropertyLink", "Drum", "Cavity", "Drum")
        obj.addProperty("App::PropertyLink", "Outline", "Cavity", "Outline")
        obj.addProperty("App::PropertyLength", "Depth", "Cavity",
                        "Cavity depth").Depth = 3.1
        obj.addProperty("App::PropertyAngle", "DraftAngle", "Cavity",
                        "Side wall draft angle").DraftAngle = 16.0
        # Direction is internally needed but always "floor_narrower"
        # (normal release direction). We don't expose it as a choice.
        obj.addProperty("App::PropertyEnumeration", "DraftDirection",
                        "Cavity", "Direction")
        obj.DraftDirection = ["floor_narrower"]
        obj.DraftDirection = "floor_narrower"
        obj.addProperty("App::PropertyLength", "FilletRadius", "Cavity",
                        "Fillet radius on floor edges").FilletRadius = 0.5
        obj.addProperty("App::PropertyLinkList", "Details", "Cavity",
                        "Details on this cavity")
        obj.addProperty("App::PropertyLinkList", "Dockers", "Cavity",
                        "Docker pin groups on this cavity")
        obj.Proxy = self

    def _ensure_props(self, obj):
        """Backward compat: add new properties to older saved objects."""
        if not hasattr(obj, "Dockers"):
            obj.addProperty("App::PropertyLinkList", "Dockers", "Cavity",
                            "Docker pin groups on this cavity")

    def execute(self, obj):
        self._ensure_props(obj)
        if obj.Drum is None or obj.Outline is None:
            FreeCAD.Console.PrintError(
                "RotaryMoulder: Cavity needs Drum and Outline.\n")
            return
        drum_shape = obj.Drum.Shape
        if drum_shape is None or drum_shape.isNull():
            return
        try:
            chunk = build_cavity_solid(
                obj.Outline, obj.Drum,
                depth=float(obj.Depth),
                angle_deg=float(obj.DraftAngle),
                direction=str(obj.DraftDirection),
            )
        except (ValueError, RuntimeError) as exc:
            FreeCAD.Console.PrintError(
                "RotaryMoulder: cavity build failed: {0}\n".format(exc))
            return
        result = _apply_cavity_with_details(
            drum_shape, obj.Drum, chunk,
            cavity_depth=float(obj.Depth),
            fillet_radius=float(obj.FilletRadius),
            details_list=list(getattr(obj, "Details", []) or []),
            cavity_outline=obj.Outline,
            dockers_list=list(getattr(obj, "Dockers", []) or []),
        )
        obj.Shape = result


class DraftedCavityViewProvider:
    def __init__(self, vobj): vobj.Proxy = self
    def attach(self, vobj): self.Object = vobj.Object
    def claimChildren(self):
        obj = getattr(self, "Object", None)
        if obj is None: return []
        kids = []
        if getattr(obj, "Outline", None):
            kids.append(obj.Outline)
        for d in (getattr(obj, "Details", []) or []):
            if d is not None: kids.append(d)
        for dk in (getattr(obj, "Dockers", []) or []):
            if dk is not None: kids.append(dk)
        return kids
    def getIcon(self): return ""
    def __getstate__(self): return None
    def __setstate__(self, _state): return None


class CavityDetail:
    Type = "RotaryMoulder::CavityDetail"

    def __init__(self, obj):
        obj.addProperty("App::PropertyLink", "Cavity", "Detail",
                        "Parent Cavity or CavityPattern")
        obj.addProperty("App::PropertyLink", "Outline", "Detail",
                        "Text/decoration outline")
        obj.addProperty("App::PropertyLength", "Depth", "Detail",
                        "Depth from cavity floor").Depth = 1.0
        obj.addProperty("App::PropertyAngle", "DraftAngle", "Detail",
                        "Draft angle").DraftAngle = 10.0
        obj.addProperty("App::PropertyEnumeration", "DraftDirection",
                        "Detail", "Direction of taper")
        obj.DraftDirection = ["floor_narrower", "rim_narrower"]
        obj.DraftDirection = "floor_narrower"
        obj.addProperty("App::PropertyEnumeration", "Mode", "Detail",
                        "engrave or emboss")
        obj.Mode = ["engrave", "emboss"]
        obj.Mode = "engrave"
        obj.Proxy = self

    def execute(self, obj):
        obj.Shape = Part.Compound([])


class CavityDetailViewProvider:
    def __init__(self, vobj): vobj.Proxy = self
    def attach(self, vobj): self.Object = vobj.Object
    def claimChildren(self):
        obj = getattr(self, "Object", None)
        return [obj.Outline] if obj is not None and obj.Outline else []
    def getIcon(self): return ""
    def __getstate__(self): return None
    def __setstate__(self, _state): return None


class CavityDockers:
    """Docker pins on a cavity. Pins are raised conical protrusions on
    the cavity floor that pierce through the entire cookie thickness,
    creating dimples or perforations (like crackers).

    Each point in the Outline sketch becomes one pin. Pin geometry:
      - Tip diameter (user-set, default 2mm)
      - Hemispherical filleted tip
      - Tip reaches drum surface level (height = cavity depth)
      - Base on cavity floor, wider than tip by 2 * height * tan(draft)
    """
    Type = "RotaryMoulder::CavityDockers"

    def __init__(self, obj):
        obj.addProperty("App::PropertyLink", "Cavity", "Dockers",
                        "Parent Cavity or CavityPattern")
        obj.addProperty("App::PropertyLink", "Outline", "Dockers",
                        "Sketch with vertices marking pin positions")
        obj.addProperty("App::PropertyLength", "TipDiameter", "Dockers",
                        "Pin tip diameter (mm)").TipDiameter = 0.2
        obj.addProperty("App::PropertyAngle", "DraftAngle", "Dockers",
                        "Pin side draft angle").DraftAngle = 16.0
        obj.Proxy = self

    def execute(self, obj):
        # Dockers are applied by parent Cavity/Pattern, not standalone
        obj.Shape = Part.Compound([])


class CavityDockersViewProvider:
    def __init__(self, vobj): vobj.Proxy = self
    def attach(self, vobj): self.Object = vobj.Object
    def claimChildren(self):
        obj = getattr(self, "Object", None)
        return [obj.Outline] if obj is not None and obj.Outline else []
    def getIcon(self): return ""
    def __getstate__(self): return None
    def __setstate__(self, _state): return None


class CavityPattern:
    Type = "RotaryMoulder::CavityPattern"

    def __init__(self, obj):
        obj.addProperty("App::PropertyLink", "Drum", "Pattern", "Drum")
        obj.addProperty("App::PropertyLink", "Outline", "Pattern",
                        "Sketch outline (ignored if SourceCavity set)")
        obj.addProperty("App::PropertyLink", "SourceCavity", "Pattern",
                        "Replicate this Cavity")
        obj.addProperty("App::PropertyInteger", "CountAround", "Pattern",
                        "Cavities around the drum").CountAround = 6
        obj.addProperty("App::PropertyInteger", "CountAxial", "Pattern",
                        "Cavities along the drum length").CountAxial = 3
        obj.addProperty("App::PropertyLength", "AxialSpacing", "Pattern",
                        "Spacing").AxialSpacing = 50.0
        obj.addProperty("App::PropertyDistance", "AxialOffset", "Pattern",
                        "Offset from end").AxialOffset = 25.0
        obj.addProperty("App::PropertyLength", "Depth", "Pattern",
                        "Depth").Depth = 3.1
        obj.addProperty("App::PropertyAngle", "DraftAngle", "Pattern",
                        "Draft angle").DraftAngle = 16.0
        obj.addProperty("App::PropertyEnumeration", "DraftDirection",
                        "Pattern", "Direction")
        obj.DraftDirection = ["floor_narrower"]
        obj.DraftDirection = "floor_narrower"
        obj.addProperty("App::PropertyLength", "FilletRadius", "Pattern",
                        "Fillet").FilletRadius = 0.5
        obj.addProperty("App::PropertyEnumeration", "Layout", "Pattern",
                        "Pattern arrangement style")
        obj.Layout = ["linear", "alternating"]
        obj.Layout = "linear"
        obj.addProperty("App::PropertyLinkList", "Details", "Pattern",
                        "Details on each patterned cavity")
        obj.addProperty("App::PropertyLinkList", "Dockers", "Pattern",
                        "Docker pin groups on each patterned cavity")
        obj.Proxy = self

    def _ensure_props(self, obj):
        """Add properties to existing pattern objects loaded from older
        documents that didn't have these properties."""
        if not hasattr(obj, "Layout"):
            obj.addProperty("App::PropertyEnumeration", "Layout", "Pattern",
                            "Pattern arrangement style")
            obj.Layout = ["linear", "alternating"]
            obj.Layout = "linear"
        if not hasattr(obj, "Dockers"):
            obj.addProperty("App::PropertyLinkList", "Dockers", "Pattern",
                            "Docker pin groups on each patterned cavity")

    def execute(self, obj):
        self._ensure_props(obj)
        if obj.Drum is None:
            return

        src = getattr(obj, "SourceCavity", None)
        if src is not None and hasattr(src, "Proxy") and \
                getattr(src.Proxy, "Type", "") == "RotaryMoulder::DraftedCavity":
            outline = src.Outline
            depth = float(src.Depth)
            angle = float(src.DraftAngle)
            direction = str(src.DraftDirection)
            fillet = float(src.FilletRadius)
            inherited_details = list(getattr(src, "Details", []) or [])
            inherited_dockers = list(getattr(src, "Dockers", []) or [])
        else:
            outline = obj.Outline
            depth = float(obj.Depth)
            angle = float(obj.DraftAngle)
            direction = str(obj.DraftDirection)
            fillet = float(obj.FilletRadius)
            inherited_details = []
            inherited_dockers = []

        if outline is None:
            FreeCAD.Console.PrintError(
                "RotaryMoulder: Pattern needs Outline or SourceCavity.\n")
            return

        try:
            base_chunk = build_cavity_solid(
                outline, obj.Drum,
                depth=depth, angle_deg=angle, direction=direction,
            )
        except (ValueError, RuntimeError) as exc:
            FreeCAD.Console.PrintError("RotaryMoulder: {0}\n".format(exc))
            return

        own_details = list(getattr(obj, "Details", []) or [])
        all_details = inherited_details + own_details

        count_a = max(1, int(obj.CountAround))
        count_x = max(1, int(obj.CountAxial))
        spacing = float(obj.AxialSpacing)
        offset = float(obj.AxialOffset)
        result = obj.Drum.Shape.copy()
        R_floor = float(obj.Drum.Diameter) / 2.0 - depth

        # Build all detail chunks ONCE (at origin)
        all_detail_chunk_lists = []
        for det in all_details:
            if det is None or not hasattr(det, "Proxy"):
                all_detail_chunk_lists.append(None); continue
            if getattr(det.Proxy, "Type", "") != \
                    "RotaryMoulder::CavityDetail":
                all_detail_chunk_lists.append(None); continue
            if det.Outline is None:
                all_detail_chunk_lists.append(None); continue
            try:
                dcs = build_detail_solid(
                    det.Outline, obj.Drum,
                    parent_cavity_floor_radius=R_floor,
                    depth=float(det.Depth),
                    angle_deg=float(det.DraftAngle),
                    direction=str(det.DraftDirection),
                    mode=str(det.Mode),
                    parent_cavity_outline=outline,
                )
                all_detail_chunk_lists.append((dcs, str(det.Mode), det.Label))
            except (ValueError, RuntimeError) as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: detail '{0}' failed: {1}\n".format(
                        det.Label, exc))
                all_detail_chunk_lists.append(None)

        # OPTIMIZATION: build a "master" cavity-with-details solid ONCE
        # at origin. Then for each pattern position, just copy+rotate the
        # master and apply ONE boolean (cut master from drum) instead of
        # rebuilding all the booleans per position.
        #
        # The master is the UNION of: the cavity volume PLUS embossed
        # details PLUS holes from engraved details. We subtract this
        # master from the drum at each pattern position.
        #
        # Build master:
        FreeCAD.Console.PrintMessage(
            "RotaryMoulder: pre-building master cavity-with-details\n")
        master = base_chunk
        # Apply fillet to floor edges of master
        if fillet > 0:
            R_inner = R_floor
            floor_edges = []
            for edge in master.Edges:
                pts = edge.discretize(Number=5)
                if all(abs(math.hypot(p.x, p.z) - R_inner) < 0.5
                       for p in pts):
                    floor_edges.append(edge)
            if floor_edges:
                try:
                    master = master.makeFillet(fillet, floor_edges)
                except Part.OCCError:
                    pass

        # Apply details to the master. Details that are EMBOSS bumps add
        # material BACK into the cavity volume; details that are ENGRAVE
        # add their volume as deeper cuts (i.e. they grow the master so
        # more is cut from the drum).
        # In _apply_detail_chunks the semantics are flipped because we're
        # operating on the cavity-shaped solid, not the drum. So we
        # invert the mode interpretation here:
        for det_info in all_detail_chunk_lists:
            if det_info is None:
                continue
            dcs, det_mode, det_label = det_info
            try:
                # For master (which will be SUBTRACTED from drum):
                # - emboss bump → SUBTRACT from master (less drum cut, bump appears)
                # - engrave indent → ADD to master (more drum cut, indent appears)
                inverted_mode = "engrave" if det_mode == "emboss" else "emboss"
                master = _apply_detail_chunks(
                    master, dcs, inverted_mode)
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: detail '{0}' failed in master: {1}\n"
                    .format(det_label, exc))

        # Apply docker pins to master. Pins are always emboss-like
        # (raised material protruding from the cavity floor toward the
        # drum surface). On the master, this means SUBTRACT the pins
        # (inverted) so they appear as raised pins on the actual drum.
        own_dockers = list(getattr(obj, "Dockers", []) or [])
        all_dockers = inherited_dockers + own_dockers
        for dck in all_dockers:
            if dck is None or not hasattr(dck, "Proxy"):
                continue
            if getattr(dck.Proxy, "Type", "") != \
                    "RotaryMoulder::CavityDockers":
                continue
            if dck.Outline is None:
                continue
            try:
                pin_chunks = build_docker_pins(
                    dck.Outline, obj.Drum,
                    parent_cavity_floor_radius=R_floor,
                    tip_diameter=float(dck.TipDiameter),
                    angle_deg=float(dck.DraftAngle),
                    parent_cavity_outline=outline,
                )
                master = _apply_detail_chunks(master, pin_chunks, "engrave")
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "RotaryMoulder: dockers '{0}' failed in master: "
                    "{1}\n".format(dck.Label, exc))

        FreeCAD.Console.PrintMessage(
            "RotaryMoulder: applying master at {0} positions\n".format(
                count_a * count_x))

        # Now apply master at each pattern position with a single cut.
        # Layout: 'linear' = same angular positions on every row.
        #         'alternating' = every other row is offset by half the
        #         angular spacing (brick-like pattern wrapped on drum).
        layout = str(getattr(obj, "Layout", "linear"))
        angular_step = 360.0 / count_a
        half_step = angular_step / 2.0

        for i in range(count_x):
            y = offset + i * spacing
            # Apply alternating offset on odd rows
            row_offset = half_step if (layout == "alternating" and i % 2 == 1) else 0.0
            for j in range(count_a):
                rot_angle = angular_step * j + row_offset
                pl = FreeCAD.Placement()
                pl.Rotation = FreeCAD.Rotation(
                    FreeCAD.Vector(0, 1, 0), rot_angle)
                pl.Base = FreeCAD.Vector(0, y, 0)

                master_copy = master.copy()
                master_copy.Placement = pl.multiply(master_copy.Placement)

                try:
                    result = result.cut(master_copy)
                except Part.OCCError as exc:
                    FreeCAD.Console.PrintWarning(
                        "RotaryMoulder: pattern cut ({0},{1}) failed: "
                        "{2}\n".format(i, j, exc))
                    continue

        obj.Shape = result


class CavityPatternViewProvider:
    def __init__(self, vobj): vobj.Proxy = self
    def attach(self, vobj): self.Object = vobj.Object
    def claimChildren(self):
        obj = getattr(self, "Object", None)
        if obj is None: return []
        kids = []
        if getattr(obj, "Outline", None):
            kids.append(obj.Outline)
        if getattr(obj, "SourceCavity", None):
            kids.append(obj.SourceCavity)
        for d in (getattr(obj, "Details", []) or []):
            if d is not None: kids.append(d)
        return kids
    def getIcon(self): return ""
    def __getstate__(self): return None
    def __setstate__(self, _state): return None


# ===========================================================================
# Factories
# ===========================================================================

def make_drum(doc=None, diameter=100.0, length=200.0, wall=0.0):
    doc = doc or FreeCAD.ActiveDocument or FreeCAD.newDocument()
    obj = doc.addObject("Part::FeaturePython", "Drum")
    Drum(obj)
    obj.Diameter = diameter; obj.Length = length; obj.WallThickness = wall
    if FreeCAD.GuiUp:
        DrumViewProvider(obj.ViewObject)
    doc.recompute()
    return obj


def make_cavity(drum, outline, depth=3.1, angle=16.0,
                direction="floor_narrower", fillet=0.5):
    doc = drum.Document
    obj = doc.addObject("Part::FeaturePython", "Cavity")
    DraftedCavity(obj)
    obj.Drum = drum; obj.Outline = outline; obj.Depth = depth
    obj.DraftAngle = angle; obj.DraftDirection = direction
    obj.FilletRadius = fillet
    if FreeCAD.GuiUp:
        DraftedCavityViewProvider(obj.ViewObject)
    doc.recompute()
    return obj


def make_detail(parent, outline, depth=1.0, angle=10.0,
                direction="floor_narrower", mode="engrave"):
    doc = parent.Document
    obj = doc.addObject("Part::FeaturePython", "CavityDetail")
    CavityDetail(obj)
    obj.Cavity = parent
    obj.Outline = outline; obj.Depth = depth
    obj.DraftAngle = angle; obj.DraftDirection = direction; obj.Mode = mode
    if FreeCAD.GuiUp:
        CavityDetailViewProvider(obj.ViewObject)
    details = list(parent.Details or [])
    details.append(obj)
    parent.Details = details
    doc.recompute()
    return obj


def make_dockers(parent, outline, tip_diameter=0.2, angle=16.0):
    """Add a CavityDockers (docker pins) child to a Cavity or
    CavityPattern. `outline` is a sketch/shape whose vertices/points
    define where pins go."""
    doc = parent.Document
    obj = doc.addObject("Part::FeaturePython", "CavityDockers")
    CavityDockers(obj)
    obj.Cavity = parent
    obj.Outline = outline
    obj.TipDiameter = tip_diameter
    obj.DraftAngle = angle
    if FreeCAD.GuiUp:
        CavityDockersViewProvider(obj.ViewObject)
    dockers = list(getattr(parent, "Dockers", []) or [])
    dockers.append(obj)
    parent.Dockers = dockers
    doc.recompute()
    return obj


def make_pattern(drum, outline_or_cavity, count_around=6, count_axial=3,
                 spacing=50.0, axial_offset=25.0,
                 depth=3.1, angle=16.0,
                 direction="floor_narrower", fillet=0.5,
                 layout="linear"):
    doc = drum.Document
    obj = doc.addObject("Part::FeaturePython", "CavityPattern")
    CavityPattern(obj)
    obj.Drum = drum
    if hasattr(outline_or_cavity, "Proxy") and \
            getattr(outline_or_cavity.Proxy, "Type", "") == \
            "RotaryMoulder::DraftedCavity":
        obj.SourceCavity = outline_or_cavity
    else:
        obj.Outline = outline_or_cavity
        obj.Depth = depth
        obj.DraftAngle = angle
        obj.DraftDirection = direction
        obj.FilletRadius = fillet
    obj.CountAround = count_around
    obj.CountAxial = count_axial
    obj.AxialSpacing = spacing
    obj.AxialOffset = axial_offset
    obj.Layout = layout
    if FreeCAD.GuiUp:
        CavityPatternViewProvider(obj.ViewObject)
    doc.recompute()
    return obj
