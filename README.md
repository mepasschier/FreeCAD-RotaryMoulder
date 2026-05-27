# Rotary Moulder Workbench
A FreeCAD workbench for designing **rotary cookie moulder drums** — the
cylindrical drums used in industrial biscuit-and-cracker production to
form raw dough into shaped cookies.
## What it does
You sketch a cookie outline (and optional letter/shape details, plus
docker pin positions) on a flat sketch. The workbench wraps that
sketch around a cylindrical drum surface and cuts a drafted cavity so
the dough releases cleanly. Patterning replicates the cavity around
the drum and along its axis into a full production-ready mould.
Features:
- **Drafted cavities** — proper release-angle taper, conformal floor
- **Wall-to-floor chamfer** — parametric `ChamferDistance` for clean
  dough release; keeps draft and 45° chamfer angles when adjusted
- **Letter / shape details** — engrave or emboss inside cavities
- **Docker pins** — perforation pins (e.g. for crackers) with conical
  geometry and rounded tips
- **Roster (lattice) details** — turn a centerline sketch into a grid
  of drafted bars on the cavity or cutting-cup floor; emboss (raised
  bars) or engrave (recessed grooves). Bars are cylinder-conformal and
  blend cleanly at crossings; engraved rosters are automatically
  clipped to the flat floor so grooves never tunnel under the wall.
- **Patterns** — linear or alternating, with optimized boolean path
- **Cutting roll cutting cups** — build the cookie as a raised body on
  the drum with a sharp cutting edge (CuttingCup). Supports details,
  docker pins, rosters, and patterning, with an inner-corner chamfer
  and an outward-growing cutting-edge flat.
- **Toggle debug** — view intermediate construction shapes
## Installation
Copy the `RotaryMoulder` folder into your FreeCAD `Mod` directory:
| OS      | Path                                                            |
|---------|-----------------------------------------------------------------|
| Windows | `%APPDATA%\FreeCAD\v1-1\Mod\RotaryMoulder`                      |
| macOS   | `~/Library/Application Support/FreeCAD/v1-1/Mod/RotaryMoulder`  |
| Linux   | `~/.local/share/FreeCAD/v1-1/Mod/RotaryMoulder`                 |
Restart FreeCAD. Select **Rotary Moulder** from the workbench
dropdown.
## Quick start
1. Click **Create Drum** — sets default 100 mm diameter, 200 mm length
2. Make a flat sketch on the **XY plane** with your cookie outline
3. Switch to the **Curves Workbench** and use **Sketch_On_Surface** to
   project that sketch onto the drum's cylindrical face
4. Switch back to **Rotary Moulder**, select drum + the Sketch_On_Surface
   object → click **Add Cavity From Sketch**
5. (Optional) Add text details with **ShapeString** (font
   `verdanab.ttf` recommended). For text to read correctly on the
   formed cookie, attach the ShapeString to the SoS's `Mapped_Sketch`
   with **Map Mode = InertialCS** and **Map Reversed = Yes**. Then
   select cavity + sketch → click **Add Detail to Cavity**
6. (Optional) Make a flat sketch with points for pin positions →
   select cavity + sketch → click **Add Docker Pins to Cavity**
7. (Optional) Add a **roster / lattice**. Make a flat sketch of
   **centerlines** (each line becomes one bar — draw centerlines only,
   not closed bar outlines). Select the cavity + the centerline sketch
   → click **Add Roster (Lattice) to Cavity / Cup**, then set bar
   width, depth, draft, and mode (emboss = raised bars, engrave =
   recessed grooves). Works on cutting cups too.
8. To replicate around the drum: select drum + cavity → click
   **Pattern Cavities Around Drum**.
See `USER_GUIDE.md` for a full tutorial with screenshots.
## Compatibility
- FreeCAD 1.1 (also tested with 1.0)
- Requires the **Curves Workbench** (used internally for projection
  onto the drum cylinder via Sketch_On_Surface)
## License
LGPL-2.1-or-later
## Authors & contact
Created by **Mike Passchier** with **Claude.ai** (Anthropic).
Questions, bug reports, or feedback: **hello@mikesprototype.com**
