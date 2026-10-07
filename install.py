#!/usr/bin/env python3
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
Script Version: 1.1.0
Written by: Michael Vaglienty
Creation Date: 09.13.26
Update Date: 10.02.26

License: GNU General Public License v3.0 (GPL-3.0) - see license file for details

Description:

    Installer for the Sammie Roto Flame Export integration. Runs standalone and
    makes three small, reversible changes to a Sammie Roto (PySide6 Qt) install:

        1. Copies the sibling 'sammie_roto_flame_export.py' into
           <sammie>/sammie/, rewriting its LOGIK_BACKDOOR_DIR line to point at
           the logik_backdoor folder you name during install.

        2. Patches <sammie>/sammie/export_dialog.py (video export) to add a
           'Import to Flame after export' checkbox and a destination combo, and
           to hand the finished output paths to send_to_flame().

        3. Patches <sammie>/sammie/export_image_dialog.py (image export) with the
           same option for single-image saves.

    Every patch is guarded: the original file is backed up to <file>.orig before
    anything is written, the patched result must pass ast.parse() before it is
    saved, and re-running upgrades an already-patched file from its .orig backup.
    If an expected anchor line is not found the file is left untouched.

    Once both dialogs are patched, an install from before the rename is tidied
    up: the old 'flame_import.py' module is removed, and the old
    ~/.sammie_flame_import.json prefs are renamed to
    ~/.sammie_roto_flame_export.json (unless that file already exists).

Usage:

    Double-click 'install.command' (the macOS entry point), or from a terminal:

        python3 install.py                    # install
        python3 install.py --uninstall        # reverse everything
        python3 install.py --sammie-dir PATH  # override Sammie location

    Uninstall restores each dialog file from its .orig backup and removes the
    copied module (and any pre-rename flame_import.py), leaving Sammie exactly
    as it was.

To install:

    Keep install.py beside sammie_roto_flame_export.py and run it from there.

Updates:

    v1.1.0 10.02.26
        - Renamed from Sammie Roto Flame Import to Sammie Roto Flame Export.
        - Installs the module as sammie_roto_flame_export.py instead of flame_import.py.
        - Removes the old flame_import.py module on install and uninstall.
        - Migrates the old ~/.sammie_flame_import.json prefs to ~/.sammie_roto_flame_export.json.
        - User messages now say Logik Backdoor instead of logik_backdoor.
"""

# ==============================================================================
# [Imports]
# ==============================================================================

import argparse
import ast
import os
import re
import shutil
import sys

# ==============================================================================
# [Constants]
# ==============================================================================

# Module copied in beside the Sammie dialogs
MODULE_NAME = 'sammie_roto_flame_export.py'

# Module name before the 09.27.26 rename, removed by install and uninstall
LEGACY_MODULE_NAME = 'flame_import.py'

# Prefs file and its pre-rename name, migrated so the artist's choices carry over
PREFS_FILE = os.path.expanduser('~/.sammie_roto_flame_export.json')
LEGACY_PREFS_FILE = os.path.expanduser('~/.sammie_flame_import.json')

# Sammie Roto folder accepted by pressing Return at the prompt
SAMMIE_DIR_DEFAULT = '/Applications/Sammie-Roto-2'

# Logik Backdoor folder accepted by pressing Return at the prompt
BACKDOOR_DIR_DEFAULT = '/opt/Autodesk/shared/python/logik_backdoor'

# Tag in every injected block, marking a file as patched so a re-run upgrades it
MARKER = '[logik_backdoor]'

# Oldest supported Sammie; earlier export dialogs may be structured differently
MIN_SAMMIE_VERSION = (2, 4, 1)

# Dialog files patched under <sammie>/sammie/
TARGET_DIALOGS = ('export_dialog.py', 'export_image_dialog.py')

# ------------------------------------------------------------------------------
# [Injected Blocks]
# ------------------------------------------------------------------------------

# Each block is inserted verbatim right after the line holding its anchor. The
# leading blank line is intentional, and the code matches Sammie's own style

# Flame Export group box, added after the settings group in both dialogs. Relies
# on their shared layout/settings_group names and QGroupBox/QFormLayout imports
BLOCK_FLAME_GROUP = '''
        # [logik_backdoor] Flame Export options in their own group box
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QLineEdit
        from sammie.sammie_roto_flame_export import refresh_flame_status, restore_prefs, remember_prefs
        flame_group = QGroupBox("Flame Export")
        flame_layout = QFormLayout(flame_group)
        self.flame_status_label = QLabel("checking...")
        flame_layout.addRow("Flame:", self.flame_status_label)
        self.flame_backdoor_label = QLabel("checking...")
        flame_layout.addRow("Logik Backdoor:", self.flame_backdoor_label)
        self.flame_import_checkbox = QCheckBox("Import to Flame after export")
        flame_layout.addRow("", self.flame_import_checkbox)
        self.flame_target_combo = QComboBox()
        self.flame_target_combo.addItems(["Library", "Batch"])
        flame_layout.addRow("Flame Destination:", self.flame_target_combo)
        self.flame_name_edit = QLineEdit()
        self.flame_name_edit.setPlaceholderText("Sammie_Roto_Imports")
        # Twice the width of the default name, so the field is comfortably wide.
        self.flame_name_edit.setMinimumWidth(
            self.flame_name_edit.fontMetrics().horizontalAdvance("Sammie_Roto_Imports") * 2)
        flame_layout.addRow("Destination Name:", self.flame_name_edit)
        # Destination follows the checkbox; whether the whole box is usable is
        # decided by refresh_flame_status, based on whether Flame is running.
        self.flame_import_checkbox.toggled.connect(self.flame_target_combo.setEnabled)
        self.flame_import_checkbox.toggled.connect(self.flame_name_edit.setEnabled)
        # Restore the last-used choices, then remember any change the artist makes.
        restore_prefs(self.flame_import_checkbox, self.flame_target_combo, self.flame_name_edit)
        self.flame_import_checkbox.toggled.connect(
            lambda *_: remember_prefs(self.flame_import_checkbox, self.flame_target_combo, self.flame_name_edit))
        self.flame_target_combo.currentTextChanged.connect(
            lambda *_: remember_prefs(self.flame_import_checkbox, self.flame_target_combo, self.flame_name_edit))
        self.flame_name_edit.textChanged.connect(
            lambda *_: remember_prefs(self.flame_import_checkbox, self.flame_target_combo, self.flame_name_edit))
        # Poll Flame's status so the box greys out when Flame is not open and
        # lights up when it is, without reopening the dialog.
        self._flame_status_timer = QTimer(self)
        self._flame_status_timer.timeout.connect(
            lambda: refresh_flame_status(
                self.flame_backdoor_label, self.flame_status_label,
                self.flame_import_checkbox, self.flame_target_combo, self.flame_name_edit))
        self._flame_status_timer.start(3000)
        refresh_flame_status(
            self.flame_backdoor_label, self.flame_status_label,
            self.flame_import_checkbox, self.flame_target_combo, self.flame_name_edit)
        layout.addWidget(flame_group)'''

# export_dialog.py A2: stash the output paths for _export_finished
BLOCK_A2 = '''
        # [logik_backdoor] remember the output paths so _export_finished can send them to Flame
        self._flame_output_paths = output_paths'''

# export_dialog.py A3: send the finished export to Flame if the box is ticked
BLOCK_A3 = '''
        # [logik_backdoor] import the finished export into Flame if the option was ticked
        if success and getattr(self, "flame_import_checkbox", None) and self.flame_import_checkbox.isEnabled() and self.flame_import_checkbox.isChecked():
            from sammie.sammie_roto_flame_export import send_to_flame
            send_to_flame(self._flame_output_paths, self.flame_target_combo.currentText(),
                          name=self.flame_name_edit.text(), parent=self)'''

# export_image_dialog.py B2: send the saved image to Flame, indented 12 spaces to
# stay inside the same try block
BLOCK_B2 = '''
            # [logik_backdoor] import the saved image into Flame if the option was ticked
            if getattr(self, "flame_import_checkbox", None) and self.flame_import_checkbox.isEnabled() and self.flame_import_checkbox.isChecked():
                from sammie.sammie_roto_flame_export import send_to_flame
                send_to_flame(output_path, self.flame_target_combo.currentText(),
                              name=self.flame_name_edit.text(), parent=self)'''

# Anchor substring -> injected block, per dialog file, inserted after the first
# matching line only
INSERTIONS = {
    'export_dialog.py': [
        ('layout.addWidget(settings_group)', BLOCK_FLAME_GROUP),
        ('output_paths, object_ids = self._generate_output_paths(settings)', BLOCK_A2),
        ('            show_message_dialog(self, title="Export Failed", message=message, type="critical")', BLOCK_A3),
    ],
    'export_image_dialog.py': [
        ('layout.addWidget(settings_group)', BLOCK_FLAME_GROUP),
        ('            show_message_dialog(self, title="Export Complete", message=f"Image saved successfully to:\\n{output_path}", type=\'information\')', BLOCK_B2),
    ],
}

# ==============================================================================
# [Argument Parsing]
# ==============================================================================

def parse_args() -> argparse.Namespace:
    """
    Parse Args
    ==========

    Parse the installer's command-line arguments.

    Returns
    -------
        args (argparse.Namespace): Parsed arguments with uninstall (bool) and
            sammie_dir (str or None) attributes.
    """

    parser = argparse.ArgumentParser(
        description='Install (or uninstall) the Sammie Roto Flame Export integration.'
    )
    parser.add_argument(
        '--uninstall',
        action='store_true',
        help='Reverse the install: restore .orig backups and remove the copied module.'
    )
    parser.add_argument(
        '--sammie-dir',
        default=None,
        help='Sammie Roto install location (otherwise the installer prompts for it).'
    )

    return parser.parse_args()

# ==============================================================================
# [Sammie Discovery]
# ==============================================================================

def verify_sammie_dir(sammie_dir: str):
    """
    Verify Sammie Dir
    =================

    Confirm that <sammie>/sammie/ holds both target dialog files.

    Args
    ----
        sammie_dir (str): Path to the Sammie Roto install.

    Returns
    -------
        paths (dict | None): Mapping of dialog filename -> absolute path if both
            files exist, otherwise None.
    """

    # Sammie package lives under <sammie>/sammie/
    sammie_pkg = os.path.join(sammie_dir, 'sammie')
    paths = {name: os.path.join(sammie_pkg, name) for name in TARGET_DIALOGS}

    # Bail out clearly if either dialog file is missing
    missing = [p for p in paths.values() if not os.path.isfile(p)]
    if missing:
        print('ERROR: could not find the Sammie dialog files under:')
        print(f'    {sammie_pkg}')
        for p in missing:
            print(f'    missing: {p}')
        print('Check --sammie-dir, or that this is a Sammie Roto install.')

        return None

    return paths

# ==============================================================================
# [Folder Prompts]
# ==============================================================================

def prompt_for_sammie_dir():
    """
    Prompt For Sammie Dir
    =====================

    Loop on stdin until the user supplies a folder that holds the Sammie export
    dialogs. Pressing Return accepts SAMMIE_DIR_DEFAULT; entering 'q' quits.

    Returns
    -------
        sammie_dir (str | None): Absolute path to a valid Sammie install, or None
            if the user quit.
    """

    while True:
        entered = input(
            'Path to the Sammie Roto install\n'
            f"  [Return for default: {SAMMIE_DIR_DEFAULT}, or 'q' to quit]: "
        ).strip()

        # Quit on 'q'
        if entered.lower() == 'q':
            return None

        # Blank accepts the default
        candidate = entered or SAMMIE_DIR_DEFAULT
        expanded = os.path.abspath(os.path.expanduser(candidate))

        # Accept a folder with both dialog files under <dir>/sammie/
        sammie_pkg = os.path.join(expanded, 'sammie')
        if all(os.path.isfile(os.path.join(sammie_pkg, name)) for name in TARGET_DIALOGS):
            return expanded

        print(f'  No Sammie export dialogs found under: {sammie_pkg}')
        print("  Try again, or type 'q' to quit.")

def prompt_for_backdoor_dir():
    """
    Prompt For Backdoor Dir
    =======================

    Loop on stdin until the user supplies a folder that contains
    'logik_backdoor_client.py'. Pressing Return accepts BACKDOOR_DIR_DEFAULT, so
    the usual install needs no typing; entering 'q' aborts.

    Returns
    -------
        backdoor_dir (str | None): Absolute path to a valid logik_backdoor folder,
            or None if the user aborted.
    """

    while True:
        entered = input(
            'Path to the Logik Backdoor folder\n'
            f"  [Return for default: {BACKDOOR_DIR_DEFAULT}, or 'q' to quit]: "
        ).strip()

        # Quit on 'q'
        if entered.lower() == 'q':
            return None

        # Blank accepts the default
        candidate = entered or BACKDOOR_DIR_DEFAULT
        expanded = os.path.abspath(os.path.expanduser(candidate))

        # Accept a folder that actually holds the client
        if os.path.isfile(os.path.join(expanded, 'logik_backdoor_client.py')):
            return expanded

        print(f'  No logik_backdoor_client.py found in: {expanded}')
        print("  Try again, or type 'q' to abort.")

# ==============================================================================
# [Module Install]
# ==============================================================================

def install_module(script_dir: str, dialog_paths: dict, backdoor_dir: str) -> str:
    """
    Install Module
    ==============

    Copy sammie_roto_flame_export.py into Sammie with the baked-in backdoor path.

    Reads the sibling module, rewrites its single LOGIK_BACKDOOR_DIR assignment
    to the validated backdoor folder, and writes the result beside the Sammie
    dialogs.

    Args
    ----
        script_dir (str):
            Directory holding this installer and the sibling module.

        dialog_paths (dict):
            Mapping produced by verify_sammie_dir(), used to locate the
            destination <sammie>/sammie/ folder.

        backdoor_dir (str):
            Validated path to the logik_backdoor folder.

    Returns
    -------
        dest (str): Absolute path of the module that was written.

    Raises
    ------
        FileNotFoundError:
            If the sibling module is missing.

        AssertionError:
            If the module does not have exactly one LOGIK_BACKDOOR_DIR line.
    """

    # Module ships next to this installer
    source = os.path.join(script_dir, MODULE_NAME)
    if not os.path.isfile(source):
        raise FileNotFoundError(f'Sibling module not found: {source}')

    # Destination sits beside the dialog files
    dest_dir = os.path.dirname(next(iter(dialog_paths.values())))
    dest = os.path.join(dest_dir, MODULE_NAME)

    with open(source, 'r') as handle:
        content = handle.read()

    # Rewrite exactly the one line that assigns LOGIK_BACKDOOR_DIR
    pattern = re.compile(r'^LOGIK_BACKDOOR_DIR = .*$', re.MULTILINE)
    replacement = f"LOGIK_BACKDOOR_DIR = '{backdoor_dir}'"
    new_content, count = pattern.subn(replacement, content)

    # Refuse to guess if there isn't exactly one such line
    assert count == 1, f'Expected exactly one LOGIK_BACKDOOR_DIR line, found {count}'

    with open(dest, 'w') as handle:
        handle.write(new_content)

    return dest

# ==============================================================================
# [Dialog Patching]
# ==============================================================================

def apply_insertions(content: str, insertions: list) -> tuple:
    """
    Apply Insertions
    ================

    Insert each block immediately after the first line that contains its anchor
    substring.

    Args
    ----
        content (str):
            Original file text.

        insertions (list):
            List of (anchor_substring, block_text) tuples.

    Returns
    -------
        result (tuple): (new_content, missing) -- the patched text and the list
            of anchor substrings that were not found.
    """

    lines = content.split('\n')
    missing = []

    for anchor, block in insertions:
        # Find the first line that contains this anchor
        idx = None
        for i, line in enumerate(lines):
            if anchor in line:
                idx = i
                break

        # Never guess: record a missing anchor and move on
        if idx is None:
            missing.append(anchor)
            continue

        # Splice the block in right after the anchor line
        block_lines = block.split('\n')
        lines[idx + 1:idx + 1] = block_lines

    return '\n'.join(lines), missing

def patch_file(path: str, insertions: list) -> tuple:
    """
    Patch File
    ==========

    Safely patch a single dialog file. Upgrade-aware and validated.

    If the file already carries the marker it was patched by an earlier run, so
    the pristine <file>.orig backup is restored first and the current blocks are
    applied to that -- re-running the installer upgrades to the latest injected
    code rather than skipping or stacking. A never-patched file is backed up to
    <file>.orig before it is touched. In both cases the patched result must pass
    ast.parse() before anything is written, and a missing anchor aborts that
    file untouched.

    Args
    ----
        path (str):
            Absolute path to the dialog file.

        insertions (list):
            List of (anchor_substring, block_text) tuples.

    Returns
    -------
        result (tuple): (status, message) where status is one of 'patched',
            're-patched' or 'error'.
    """

    name = os.path.basename(path)
    orig_path = path + '.orig'

    with open(path, 'r') as handle:
        current = handle.read()

    # Re-patch an already-patched file from its pristine .orig so new blocks replace old ones
    if MARKER in current:
        if not os.path.exists(orig_path):
            return 'error', f'{name} is already patched but has no .orig backup; not touching it'
        with open(orig_path, 'r') as handle:
            base = handle.read()
        action = 're-patched'
    else:
        base = current
        action = 'patched'

    new_content, missing = apply_insertions(base, insertions)

    # Missing anchor means Sammie may have changed, so leave the file alone
    if missing:
        detail = '; '.join(repr(a) for a in missing)

        return 'error', f'anchor not found in {name}; Sammie may have changed; aborting this file ({detail})'

    # Patched result must be valid Python before anything is written
    try:
        ast.parse(new_content)
    except SyntaxError as exc:
        return 'error', f'patched {name} did not parse, wrote nothing ({exc})'

    # Back up the pristine original the first time only; on a re-patch .orig already holds it
    if not os.path.exists(orig_path):
        shutil.copy2(path, orig_path)

    with open(path, 'w') as handle:
        handle.write(new_content)

    return action, f'{name} {action} (backup: {os.path.basename(orig_path)})'

# ==============================================================================
# [Version Check]
# ==============================================================================

def sammie_version(sammie_dir: str):
    """
    Sammie Version
    ==============

    Parse __version__ from sammie_main.py into a tuple of ints.

    Args
    ----
        sammie_dir (str): Path to the Sammie Roto install.

    Returns
    -------
        version (tuple | None): e.g. (2, 4, 1), or None if it could not be read.
    """

    main_py = os.path.join(sammie_dir, 'sammie_main.py')
    try:
        with open(main_py, 'r') as handle:
            text = handle.read()
    except OSError:
        return None

    match = re.search(r"__version__\s*=\s*['\"]([0-9]+(?:\.[0-9]+)*)['\"]", text)
    if not match:
        return None

    try:
        return tuple(int(part) for part in match.group(1).split('.'))
    except ValueError:
        return None

def check_version(sammie_dir: str) -> bool:
    """
    Check Version
    =============

    Compare the install's version to MIN_SAMMIE_VERSION. A version below the
    minimum is refused. An unreadable version is a warning, not a block, so a
    future version-string change does not stop a valid install.

    Args
    ----
        sammie_dir (str): Path to the Sammie Roto install.

    Returns
    -------
        proceed (bool): True to proceed, False to abort.
    """

    version = sammie_version(sammie_dir)
    minimum = '.'.join(str(n) for n in MIN_SAMMIE_VERSION)

    if version is None:
        print('  WARNING: could not read the Sammie Roto version; proceeding anyway.')

        return True

    found = '.'.join(str(n) for n in version)
    if version < MIN_SAMMIE_VERSION:
        print(f'  ERROR: Sammie Roto {found} found, but this needs at least {minimum}.')
        print(f'  Please update Sammie Roto to {minimum} or newer, then run the installer again.')

        return False

    print(f'  Sammie Roto {found} -- meets the {minimum} minimum.')

    return True

# ==============================================================================
# [Install / Uninstall Flows]
# ==============================================================================

def install(sammie_dir, script_dir: str) -> int:
    """
    Install
    =======

    Verify Sammie, prompt for the backdoor folder, copy in the module and patch
    both dialogs, then print a summary.

    Args
    ----
        sammie_dir (str | None):
            Path to the Sammie Roto install, or None to prompt for it.

        script_dir (str):
            Directory holding this installer.

    Returns
    -------
        exit_code (int): 0 on success, 1 on abort/failure.
    """

    print('Sammie Roto Flame Export -- installer')

    # 1. Resolve the Sammie install, prompting if it wasn't given on the command line
    if sammie_dir is None:
        sammie_dir = prompt_for_sammie_dir()
        if sammie_dir is None:
            print('Quit: no Sammie Roto folder given.')

            return 1
    print(f'Sammie dir: {sammie_dir}')

    # 2. Confirm the dialog files are present
    dialog_paths = verify_sammie_dir(sammie_dir)
    if dialog_paths is None:
        return 1

    # 3. Refuse Sammie versions older than the supported minimum
    if not check_version(sammie_dir):
        return 1

    # 4. Ask where the Logik Backdoor folder lives
    backdoor_dir = prompt_for_backdoor_dir()
    if backdoor_dir is None:
        print('Aborted: no Logik Backdoor folder given.')

        return 1

    # 5. Copy the module in with the baked-in backdoor path
    module_dest = install_module(script_dir, dialog_paths, backdoor_dir)

    # 6. Patch each dialog file, collecting per-file results
    results = []
    for name in TARGET_DIALOGS:
        status, message = patch_file(dialog_paths[name], INSERTIONS[name])
        results.append((status, message))

    # 7. Tidy up a pre-rename install, only when every dialog patched: an
    #    unpatched dialog may still import the old module, which reads the old prefs
    failed = any(status == 'error' for status, _ in results)
    legacy_path = os.path.join(os.path.dirname(module_dest), LEGACY_MODULE_NAME)
    if not failed and os.path.isfile(legacy_path):
        os.remove(legacy_path)
        results.append(('removed', f'legacy {legacy_path}'))
    if not failed and os.path.isfile(LEGACY_PREFS_FILE) and not os.path.exists(PREFS_FILE):
        os.rename(LEGACY_PREFS_FILE, PREFS_FILE)
        results.append(('migrated', f'{LEGACY_PREFS_FILE} -> {PREFS_FILE}'))

    # 8. Summary
    print('')
    print('Summary')
    print('=======')
    print(f'  copied: {module_dest}')
    print(f'  LOGIK_BACKDOOR_DIR -> {backdoor_dir}')
    for status, message in results:
        print(f'  {status + ":":<8} {message}')

    # Non-zero exit if any file errored out
    if failed:
        return 1

    # Tell the user Sammie must restart to load the patched dialogs
    print('')
    print('Update complete. Restart Sammie Roto to see the Flame Export options.')
    print('')
    print('NOTE: Sammie Roto Flame Export requires Autodesk Flame or Flare 2025.2 or later.')

    return 0

def uninstall(sammie_dir) -> int:
    """
    Uninstall
    =========

    Restore each dialog file from its .orig backup and remove the copied module
    (and any pre-rename flame_import.py), then print a summary.

    Args
    ----
        sammie_dir (str | None): Path to the Sammie Roto install, or None to prompt for it.

    Returns
    -------
        exit_code (int): 0 on success, 1 if Sammie could not be found.
    """

    print('Sammie Roto Flame Export -- uninstaller')

    # Prompt (Return accepts the default) when the path wasn't given on the command line
    if sammie_dir is None:
        sammie_dir = prompt_for_sammie_dir()
        if sammie_dir is None:
            print('Quit: no Sammie Roto folder given.')

            return 1
    print(f'Sammie dir: {sammie_dir}')

    # Sammie package folder that holds everything the install touched
    sammie_pkg = os.path.join(sammie_dir, 'sammie')
    if not os.path.isdir(sammie_pkg):
        print(f'ERROR: no such folder: {sammie_pkg}')

        return 1

    results = []

    # Restore each dialog file from its backup if one exists
    for name in TARGET_DIALOGS:
        path = os.path.join(sammie_pkg, name)
        orig_path = path + '.orig'
        if os.path.exists(orig_path):
            shutil.copy2(orig_path, path)
            os.remove(orig_path)
            results.append(f'restored: {name} from {os.path.basename(orig_path)}')
        else:
            results.append(f'skipped:  {name} (no backup found)')

    # Remove the copied module, and the pre-rename one if an old install left it
    for module_name in (MODULE_NAME, LEGACY_MODULE_NAME):
        module_path = os.path.join(sammie_pkg, module_name)
        if os.path.isfile(module_path):
            os.remove(module_path)
            results.append(f'removed:  {module_name}')
        else:
            results.append(f'skipped:  {module_name} (not present)')

    # Summary
    print('')
    print('Summary')
    print('=======')
    for line in results:
        print(f'  {line}')

    return 0

# ==============================================================================
# [Entry Points]
# ==============================================================================

def main() -> int:
    """
    Main
    ====

    Parse arguments and dispatch to the install or uninstall flow.

    Returns
    -------
        exit_code (int): Process exit code.
    """

    args = parse_args()

    # Folder holding this installer and the sibling module
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Both flows prompt for the Sammie folder when --sammie-dir is unset
    if args.uninstall:
        return uninstall(args.sammie_dir)

    return install(args.sammie_dir, script_dir)

if __name__ == '__main__':
    sys.exit(main())
