# Sammie Roto Flame Export
# Copyright (c) 2026 Michael Vaglienty
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# License:       GNU General Public License v3.0 (GPL-3.0)
#                https://www.gnu.org/licenses/gpl-3.0.en.html

"""
Script Name: Sammie Roto Flame Export
Script Version: 1.0.0
Written by: Michael Vaglienty
Creation Date: 10.07.26
Update Date: 10.07.26

License: GNU General Public License v3.0 (GPL-3.0) - see license file for details

Description:

    Exports rendered mattes from Sammie Roto to a running Flame session.

    For macOS and Linux. So far it has only been tested on macOS.

Requirements:

    - Sammie Roto 2.4.1 or later
    - Flame 2025.2 or later
    - Logik Backdoor 1.0.0 or later

Usage:
  
    Adds a "Flame Export" option to Sammie Roto's Export Video and Export Image
    windows.
    Logik Backdoor must be installed and a Flame session must be running.
    Check "Import to Flame after export" to have exported mattes automatically
    imported into a running Flame session. The destination for the import can
    be set to either a Library or the current batch.

To install:

    Install the Logik Backdoor in Flame first.

    Logik Backdoor can be found in the Logik Portal Flame app or here:
    https://logik-portal.com/scripts/logik_backdoor

    Run install.py(Linux) or install.command(MacOS) from this folder. It copies this module into <sammie>/sammie/ and patches Sammie's two export dialogs.
 
    To uninstall run: python3 install.py --uninstall

Updates:

    v1.0.0 10.07.26
        - Initial release.
"""

# ==============================================================================
# [Imports]
# ==============================================================================

import json
import os
import re
import sys

# ==============================================================================
# [Constants]
# ==============================================================================

# Folder holding logik_backdoor_client.py. The installer rewrites this line, so
# keep it on its own line exactly in this form
LOGIK_BACKDOOR_DIR = '/opt/Autodesk/shared/python/logik_backdoor'

# Default Library or Batch reel name, overridable in the export dialog
DEFAULT_DESTINATION_NAME = 'Sammie_Roto_Imports'

# Status line colours: good, problem, unknown
STATUS_GREEN = '#6fbf6f'
STATUS_RED = '#b06060'
STATUS_GREY = '#888888'

# Remembered import choices, kept in home so Sammie updates don't wipe them
PREFS_FILE = os.path.expanduser('~/.sammie_roto_flame_export.json')

# ==============================================================================
# [Helpers]
# ==============================================================================

def _warn(parent, text: str) -> None:
    """
    Warn
    ====

    Show a warning message box and return, never raising.

    Every non-fatal failure in this module ends the same way: the artist is
    told what went wrong in a dialog and the export dialog carries on.

    Args
    ----
        parent (QWidget):
            Optional Qt parent widget for the dialog.

        text (str):
            Message to show the artist.
    """

    from PySide6.QtWidgets import QMessageBox

    QMessageBox.warning(parent, 'Sammie Roto Flame Export', text)

def _has_backdoor(folder: str) -> bool:
    """
    Has Backdoor
    ============

    Report whether a folder holds logik_backdoor_client.py.

    Args
    ----
        folder (str): Candidate folder path, possibly empty.

    Returns
    -------
        has_backdoor (bool): True if folder is set and contains logik_backdoor_client.py.
    """

    return bool(folder) and os.path.isfile(os.path.join(folder, 'logik_backdoor_client.py'))

def _resolve_backdoor_dir(parent):
    """
    Resolve Backdoor Dir
    ====================

    Return the folder holding logik_backdoor_client.py, or None if it cannot be found.

    The baked LOGIK_BACKDOOR_DIR is tried first and is the normal case. Only when
    it does not hold the client does the artist get a one-off folder picker. A
    picked folder is validated the same way and deliberately not persisted: the
    installer is the persistence mechanism, and the picker only rescues the
    current import.

    Args
    ----
        parent (QWidget): Optional Qt parent widget for the folder picker.

    Returns
    -------
        backdoor_dir (str | None): The validated folder, or None if it could not be resolved.
    """

    from PySide6.QtWidgets import QFileDialog

    # Trust the installer's path when it is actually there
    if _has_backdoor(LOGIK_BACKDOOR_DIR):
        return LOGIK_BACKDOOR_DIR

    # Baked path is wrong, so let the artist point at the folder for this import
    picked = QFileDialog.getExistingDirectory(parent, 'Locate the Logik Backdoor folder')
    if _has_backdoor(picked):
        return picked

    return None

def _sequence_bracket(path: str) -> str:
    """
    Sequence Bracket
    ================

    Turn a Sammie sequence base into a Flame bracket path, or pass a file through.

    Sammie writes an image sequence as base.####.ext frames but hands over the
    extensionless base (e.g. /out/matte), which Flame cannot import. When such
    frames are found beside the base this returns Flame's bracket notation,
    base.[first-last].ext, which Flame imports as a single clip. A real file (a
    video or single image) is returned unchanged, and if no frames are found the
    path is returned as-is so the caller still reports a clean failure.

    Args
    ----
        path (str): A Sammie output path -- a real file, or a sequence base.

    Returns
    -------
        media_path (str): A file path, or a Flame bracket-notation sequence path.
    """

    # Real files need no translation
    if os.path.isfile(path):
        return path

    directory = os.path.dirname(path) or '.'
    base = os.path.basename(path)
    if not os.path.isdir(directory):
        return path

    # Match Sammie's frame naming: <base>.<frame>.<ext>
    pattern = re.compile(r'^' + re.escape(base) + r'\.(\d+)\.([A-Za-z0-9]+)$')
    numbers = []
    width = 4
    ext = None
    for name in os.listdir(directory):
        match = pattern.match(name)
        if match:
            numbers.append(int(match.group(1)))
            width = len(match.group(1))
            ext = match.group(2)

    # No frames beside the base, so leave it alone rather than guess
    if not numbers or ext is None:
        return path

    first, last = min(numbers), max(numbers)

    return f'{path}.[{first:0{width}d}-{last:0{width}d}].{ext}'

def _to_flame_media(paths):
    """
    To Flame Media
    ==============

    Resolve one path or a list of paths into Flame-importable media.

    A single path resolves to a single value; a list resolves element by element,
    so a batch of exported objects keeps its shape. See _sequence_bracket for the
    per-path rule.

    Args
    ----
        paths (str | list): One Sammie output path, or a list of them.

    Returns
    -------
        media (str | list): The resolved path(s), matching the input shape.
    """

    if isinstance(paths, (list, tuple)):
        return [_sequence_bracket(p) for p in paths]

    return _sequence_bracket(paths)

# ==============================================================================
# [Flame Import]
# ==============================================================================

def send_to_flame(paths, target: str, name=None, parent=None) -> None:
    """
    Send To Flame
    =============

    Import Sammie's exported file(s) into a running Flame session.

    Locates the logik_backdoor client, imports it, confirms a Flame session is
    live, then asks it to bring the media into a Library or the open Batch. The
    result is reported to the artist in a message box either way. This function
    never raises into Sammie: every failure becomes a dialog so a bad import
    cannot crash the export dialog that called it.

    PySide6 is imported lazily inside the body so the module can be imported and
    AST-checked outside Sammie, where Qt is not present.

    Args
    ----
        paths (str | list):
            A single path, or a list of paths, for the exported file(s) or
            sequence. Passed straight through to the logik_backdoor tool, which
            accepts either form.

        target (str):
            'Library' to import into a Library, or 'Batch' to import onto a reel
            in the open Batch.

        name (str):
            Destination name to use. Blank falls back to the default for the
            chosen target (DEFAULT_DESTINATION_NAME).
            (Default: `None`)

        parent (QWidget):
            Optional Qt parent widget for the message dialogs.
            (Default: `None`)
    """

    # Find the client, skipping the import if it can't be resolved
    backdoor_dir = _resolve_backdoor_dir(parent)
    if backdoor_dir is None:
        _warn(
            parent,
            'Logik Backdoor not found -- import skipped. Re-run the Sammie Roto Flame '
            'Export installer to set the path.',
            )

        return

    # Import the client from this install; a missing or broken client skips the import
    if backdoor_dir not in sys.path:
        sys.path.insert(0, backdoor_dir)

    try:
        import logik_backdoor_client as backdoor
    except ImportError as error:
        _warn(parent, f'Could not load Logik Backdoor -- import skipped.\n\n{error}')

        return

    # Don't send anything if no Flame session with the backdoor is running
    if not backdoor.available():
        _warn(
            parent,
            'No running Flame session found -- is Flame open with Logik Backdoor '
            'installed?',
            )

        return

    # Translate sequence bases into Flame bracket notation; files pass through
    paths = _to_flame_media(paths)

    # Import with the matching tool, falling back to the shared default name
    destination = name or DEFAULT_DESTINATION_NAME
    if target == 'Library':
        result = backdoor.call('import_image_to_library', timeout=600, path=paths, library_name=destination)
    else:
        result = backdoor.call('import_image_to_batch', timeout=600, path=paths, reel_name=destination)

    from PySide6.QtWidgets import QMessageBox

    # Report the destination and clips on success, or the tool's error on failure
    if result.get('ok'):
        clips = result.get('clips') or []
        names = '\n'.join(clips) if clips else '(no clip names returned)'
        QMessageBox.information(
            parent,
            'Sammie Roto Flame Export',
            f'Flame Import Complete\n\nImported into {destination}:\n\n{names}',
            )
    else:
        QMessageBox.critical(
            parent,
            'Sammie Roto Flame Export',
            f'Import failed:\n\n{result.get("error")}',
            )

# ==============================================================================
# [Preferences]
# ==============================================================================

def _load_prefs() -> dict:
    """
    Load Prefs
    ==========

    Read the remembered import choices, or an empty dict if none are saved.
    Never raises.

    Returns
    -------
        prefs (dict): Saved preferences, possibly empty.
    """

    try:
        with open(PREFS_FILE, 'r') as handle:
            data = json.load(handle)

        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def _save_prefs(enabled: bool, destination: str, name: str) -> None:
    """
    Save Prefs
    ==========

    Remember the current import choices for next time. Never raises.

    Args
    ----
        enabled (bool):
            Whether 'Import to Flame after export' is ticked.

        destination (str):
            The chosen destination, 'Library' or 'Batch'.

        name (str):
            The destination name typed by the artist (may be blank).
    """

    try:
        with open(PREFS_FILE, 'w') as handle:
            json.dump(
                {'enabled': bool(enabled), 'destination': str(destination), 'name': str(name)},
                handle,
                )
    except OSError:
        pass

def restore_prefs(checkbox, combo, name_edit) -> None:
    """
    Restore Prefs
    =============

    Apply the remembered checkbox, destination and name on dialog open.

    Args
    ----
        checkbox (QCheckBox):
            The 'Import to Flame after export' checkbox.

        combo (QComboBox):
            The Library / Batch destination combo.

        name_edit (QLineEdit):
            The destination-name field.
    """

    prefs = _load_prefs()
    checkbox.setChecked(bool(prefs.get('enabled', False)))
    destination = prefs.get('destination')
    if destination in ('Library', 'Batch'):
        combo.setCurrentText(destination)
    name_edit.setText(str(prefs.get('name', DEFAULT_DESTINATION_NAME)))

def remember_prefs(checkbox, combo, name_edit) -> None:
    """
    Remember Prefs
    ==============

    Save the checkbox, destination and name whenever the artist changes them.

    Args
    ----
        checkbox (QCheckBox):
            The 'Import to Flame after export' checkbox.

        combo (QComboBox):
            The Library / Batch destination combo.

        name_edit (QLineEdit):
            The destination-name field.
    """

    _save_prefs(checkbox.isChecked(), combo.currentText(), name_edit.text())

# ==============================================================================
# [Flame Status]
# ==============================================================================

def flame_status() -> tuple:
    """
    Flame Status
    ============

    Report whether a Flame/Flare session is reachable, and its version, silently.

    Reads the session metadata the backdoor already records, so the version is
    had without a round-trip to the running app. When more than one session is
    open it reports the newest, which is the one an import would target. It never
    shows a dialog and never raises: a bad backdoor path, a client that will not
    import, or no live session all read as not running. Only the baked path is
    consulted, so the folder picker used by send_to_flame is not involved here.

    Returns
    -------
        status (tuple): (running, version) -- a bool and the version string, or
            (False, None) when nothing is reachable.
    """

    if not _has_backdoor(LOGIK_BACKDOOR_DIR):
        return (False, None)

    # Make the client importable, then read its live sessions
    if LOGIK_BACKDOOR_DIR not in sys.path:
        sys.path.insert(0, LOGIK_BACKDOOR_DIR)

    try:
        import logik_backdoor_client as backdoor
        found = backdoor.sessions()
        if found:
            return (True, found[0].get('version'))

        return (False, None)
    except BaseException:
        return (False, None)

def flame_is_running() -> bool:
    """
    Flame Is Running
    ================

    Report whether a Flame/Flare session is reachable. Thin wrapper on
    flame_status for callers that only need the boolean.

    Returns
    -------
        running (bool): True if a live session was found.
    """

    return flame_status()[0]

def _set_status(label, text: str, colour: str) -> None:
    """
    Set Status
    ==========

    Set a status label's text and colour in one call.

    Args
    ----
        label (QLabel):
            The label to update.

        text (str):
            Text to show.

        colour (str):
            CSS colour, e.g. one of the STATUS_* constants.
    """

    label.setText(text)
    label.setStyleSheet(f'color: {colour};')

def refresh_flame_status(backdoor_label, flame_label, checkbox, combo, name_edit) -> None:
    """
    Refresh Flame Status
    ====================

    Update the two status lines and the enabled state of the Flame Export
    controls.

    Two things have to be true to import: the logik_backdoor client must be
    found, and a Flame session must be running. Each gets its own status line so
    the artist can see which one is missing. The controls are usable only when
    both are good; otherwise the whole section is greyed out. The export dialog
    calls this on a timer, so the state tracks the client and Flame coming and
    going while the dialog is up.

    Args
    ----
        backdoor_label (QLabel):
            Label showing whether the logik_backdoor client was found.

        flame_label (QLabel):
            Label showing whether Flame is running.

        checkbox (QCheckBox):
            The 'Import to Flame after export' checkbox.

        combo (QComboBox):
            The Library / Batch destination combo.

        name_edit (QLineEdit):
            The destination-name field.
    """

    installed = _has_backdoor(LOGIK_BACKDOOR_DIR)
    running, version = flame_status()

    # Logik Backdoor line
    if installed:
        _set_status(backdoor_label, 'Found', STATUS_GREEN)
    else:
        _set_status(backdoor_label, 'Not found', STATUS_RED)

    # Flame line: unknown without the client, else the targeted session's version
    if not installed:
        _set_status(flame_label, 'unknown', STATUS_GREY)
    elif running:
        text = f'Running ({version})' if version else 'Running'
        _set_status(flame_label, text, STATUS_GREEN)
    else:
        _set_status(flame_label, 'Not running', STATUS_RED)

    # Enable the checkbox only when both are good; destination and name follow the checkbox
    usable = installed and running
    checkbox.setEnabled(usable)
    active = usable and checkbox.isChecked()
    combo.setEnabled(active)
    name_edit.setEnabled(active)
