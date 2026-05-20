# Contributing to Rotary Moulder Workbench

Thanks for your interest in contributing! Bug reports, feature requests,
and pull requests are all welcome.

## Reporting bugs

Please open an issue at:
https://github.com/mepasschier/FreeCAD-RotaryMoulder/issues

Include:
- FreeCAD version (Help → About FreeCAD)
- Operating system
- Steps to reproduce
- Expected vs actual behaviour
- If geometry-related, the report-view output (enable "Toggle Debug
  Intermediates" first for more diagnostic info)

## Suggesting features

Open an issue describing the feature and your use case. Discussion before
coding helps everyone.

## Pull requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-thing`)
3. Make your changes
4. Test that the existing tutorial walkthrough (see `USER_GUIDE.md`)
   still works end-to-end
5. Open a pull request describing what you changed and why

Code style: match the existing `geometry.py` conventions (4-space
indentation, snake_case, type hints where reasonable, docstrings for
new public functions).

## Development setup

1. Clone the repo into your FreeCAD `Mod` folder:
   - Windows: `%APPDATA%\FreeCAD\v1-1\Mod\`
   - macOS: `~/Library/Application Support/FreeCAD/v1-1/Mod/`
   - Linux: `~/.local/share/FreeCAD/v1-1/Mod/`
2. Restart FreeCAD
3. Edit files in place; restart FreeCAD to pick up changes
4. Enable the "Toggle Debug Intermediates" button to see geometry
   construction intermediates when something goes wrong

## Contact

Maintainer: Mike Passchier <hello@mikesprototype.com>
