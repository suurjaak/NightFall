# -*- coding: utf-8 -*-
"""
Application settings, and functionality to save/load some of them from
an external file. Configuration file has simple INI file format,
and all values are kept in JSON.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     15.10.2012
@modified    05.04.2022
------------------------------------------------------------------------------
"""
try: import ConfigParser as configparser # Py2
except ImportError: import configparser  # Py3
import datetime
import json
import os
import sys

import appdirs

"""Program name, title, version number, and version date."""
Name = "nightfall"
Title = "NightFall"
Version = "2.2"
VersionDate = "05.04.2022"

if getattr(sys, 'frozen', False):
    # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable) # likely relative
    ApplicationFile = os.path.realpath(sys.executable)
    ApplicationPath = os.path.abspath(sys.executable)
    ShortcutIconPath = ApplicationPath
    ResourceDirectory = os.path.join(getattr(sys, "_MEIPASS", ""), "res")
    EtcDirectory = ApplicationDirectory
else:
    ApplicationDirectory = os.path.abspath(os.path.join(__file__, "..", ".."))
    ApplicationFile = os.path.join(ApplicationDirectory, Title.lower(), "main.py")
    ApplicationPath = "%s" % Title.lower()
    ResourceDirectory = os.path.abspath(os.path.join(ApplicationDirectory, "..", "res"))
    ShortcutIconPath = os.path.join(ResourceDirectory, "Icon.ico")
    EtcDirectory = os.path.join(os.path.abspath(os.path.dirname(__file__)), "etc")

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = [
    "ManualEnabled", "Schedule", "ScheduleEnabled", "ThemeName", "Themes",
]
"""List of user-modifiable attributes, saved if changed from default."""
OptionalFileDirectives = [
    "DefaultSuspendInterval", "FadeSteps", "ModifiedTemplate",
    "SuspendIntervals", "ThemeBitmapSize", "ThemeNamedBitmapSize",
    "TimerInterval", "UnsavedLabel", "UnsavedName", "UnsavedTheme",
    "WindowSlideInEnabled", "WindowSlideOutEnabled",
    "WindowSlideInStep", "WindowSlideOutStep",
    "WindowSlideDelay", "WindowTimeout",
]
Defaults = {}

"""Default path of file where FileDirectives are kept."""
ConfigFile = os.path.join(EtcDirectory, "%s.ini" % Title.lower())

"""Settings window size in pixels, (w, h)."""
WindowSize = (400, 380)

"""Size for theme bitmaps, as (w, h)."""
ThemeBitmapSize = (80, 50)

"""Size for labelled theme bitmaps, as (w, h)."""
ThemeNamedBitmapSize = ThemeBitmapSize[0], ThemeBitmapSize[1] + 15

"""Seconds between checking whether to apply/unapply schedule."""
TimerInterval = 10

"""Number of seconds before settings window is hidden on losing focus."""
WindowTimeout = 60

"""Whether sliding the settings window in/out of view is enabled."""
WindowSlideInEnabled = True
WindowSlideOutEnabled = False
"""Pixel step for settings window movement during slidein/slideout."""
WindowSlideInStep = 6
WindowSlideOutStep = 5

"""Milliseconds between steps during slidein/slideout."""
WindowSlideDelay = 10

"""Milliseconds between steps during theme fadein/fadeout."""
FadeDelay = 30

"""Number of incremental steps to take during theme fadein/fadeout."""
FadeSteps = 20

"""Command-line parameter for running the program with settings minimized."""
StartMinimizedParameter = "--start-minimized"

"""
Valid range for gamma coefficients, as (min, max). Lower coefficients cause the
system calls to fail for unknown reason.
"""
ValidColourRange = (59, 255)

"""Whether theme is manually applied."""
ManualEnabled = False

"""Whether theme is applied automatically on schedule."""
ScheduleEnabled = True

"""Whether NightFall runs at computer startup."""
StartupEnabled = False

"""Name of current selected theme."""
ThemeName = "alpenglow"

"""Gamma coefficients for normal display."""
NormalTheme = [255, 255, 255, 128]

"""Gamma coefficients being edited in theme editor."""
UnsavedTheme = None

"""Screen brightness for normal display, most screens can go 0..200%."""
NormalBrightness = 128

"""Stored colour themes, as {name: [r, g, b, brightness]}."""
Themes = {
    "alpenglow":   [255, 211, 176,  57],
    "dawn":        [255, 189, 189,  82],
    "gloom":       [255, 255, 255,   0],
    "golden hour": [255, 255, 159,  77],
    "green visor": [159, 255, 159,  77],
    "no sleep":    [128, 128, 255, 128],
    "superbright": [255, 255, 255, 255],
    "twilight":    [255, 179, 179,  57],
    "fireside":    [255, 128, 128, 128],
}

"""Auto-apply schedule, [1,0,..] per each quarter hour."""
Schedule = [1] * 7 * 4 + [0] * 15 * 4 + [1] * 2 * 4

"""Datetime from which to apply theme."""
SuspendedUntil = None

"""URL to program homepage."""
HomeUrl = "https://github.com/suurjaak/NightFall"

"""Tooltip shown for the tray icon."""
TrayTooltip = "NightFall (double-click to toggle colour theme)"

"""Name of edited but unsaved theme."""
UnsavedName = "alpenglow"

"""Label for unsaved and unnamed theme in schedule combobox."""
UnsavedLabel = " (unsaved) "

"""String template for modified unsaved theme, with name placeholder."""
ModifiedTemplate = "%s *"

"""String template for suspended info, with time placeholder."""
SuspendedTemplate = "Suspended until %s"

"""String template for suspended info, with time placeholder."""
SuspendedHTMLTemplate = """
<font face="Tahoma" size=2 color="%(graycolour)s">
Suspended until <a href="_"><font color="%(linkcolour)s">%(time)s</font></a>
</font>"""

"""Minutes to postpone schedule by on suspending."""
SuspendIntervals = [10, 20, 30, 45, 60, 90, 120, 180]

"""Initial minutes to postpone schedule by on suspending."""
DefaultSuspendInterval = 20

"""Activation label for suspend-button."""
SuspendOnLabel = "\n".join(x.center(15) for x in 
                           ("Suspend", "for %s minutes" % DefaultSuspendInterval))

"""Deactivation label for suspend-button."""
SuspendOffLabel = "Unsuspend"

"""Activation tooltip for suspend-button."""
SuspendOnToolTip = "Delay applying theme for %s minutes" % DefaultSuspendInterval

"""Deactivation tooltip for suspend-button."""
SuspendOffToolTip = "Apply theme immediately"

"""Information text shown on theme editor page."""
InfoEditorText = (
    "Fine-tune individual display components: brightness "
    "(ranges from dark to superbright) and red-green-blue colour channels.\n"
    "Normal mode is 100% brightness with colours at maximum.\n\n"
    "A lot of the darker ranges will not be accepted by the graphics hardware. "
    "This is system-specific, and is to be expected."
)

"""Information text shown on about page."""
AboutHTMLTemplate = """
<font face="Tahoma" size=2 color="%%(textcolour)s">
  <p>
  Change screen colour gamma and brightness settings, 
  in order to achieve a more natural feeling during late hours.
  </p>

  <p>
  Released as free open source software under the MIT License.<br />
  Copyright &copy; 2012, Erki Suurjaak
  </p>

  <p>
  NightFall has been built using the following open source software:
  <ul>
    <li>Python, <a href="https://www.python.org"><font color="%%(linkcolour)s">python.org</font></a></li>
    <li>wxPython, <a href="https://wxpython.org"><font color="%%(linkcolour)s">wxpython.org</font></a></li>
    <li>appdirs, <a href="https://pypi.org/project/appdirs"><font color="%%(linkcolour)s">pypi.org/project/appdirs</font></a></li>
    %(pyinstaller)s
  </ul>
  </p>

  <p>
  Several icons from Fugue Icons, &copy; 2010 Yusuke Kamiyamane,
  <a href="https://p.yusukekamiyamane.com"><font color="%%(linkcolour)s">p.yusukekamiyamane.com</font></a>
  %(nsis)s
  </p>
</font>
""" % {"pyinstaller": '<li>PyInstaller, <a href="https://www.pyinstaller.org">'
                      '<font color="%(linkcolour)s">pyinstaller.org</font></a></li>'
                      if getattr(sys, 'frozen', False) else "",
       "nsis":        '<br />Installer from Nullsoft Scriptable Install System, <a href="https://nsis.sourceforge.io">'
                      '<font color="%(linkcolour)s">nsis.sourceforge.io</font></a>'
                      if getattr(sys, 'frozen', False) else ""}


def load():
    """Loads known directives from ConfigFile into this module's attributes."""
    global Defaults

    configpaths = [ConfigFile]
    if not Defaults:  # First load
        try: # Instantiate OS- and user-specific path
            p = appdirs.user_config_dir(Title, appauthor=False)
            # Try user-specific path first, then path under application folder
            configpaths.insert(0, os.path.join(p, "%s.ini" % Title.lower()))
        except Exception: pass

    section = "*"
    module = sys.modules[__name__]
    Defaults.update({k: getattr(module, k) for k in FileDirectives + OptionalFileDirectives
                     if hasattr(module, k)}) if not Defaults else None

    parser = configparser.RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    try:
        # Try user-specific path first, then path under application folder
        for path in configpaths[::-1]:
            if os.path.isfile(path) and parser.read(ConfigFile):
                break  # for path

        def parse_value(name):
            try:  # parser.get can throw an error if value not found
                value_raw = parser.get(section, name)
            except Exception:
                return None, False
            try:  # Try to interpret as JSON, fall back on raw string
                value = json.loads(value_raw)
            except ValueError:
                value = value_raw
            return value, True

        for name in FileDirectives + OptionalFileDirectives:
            [setattr(module, name, v) for v, s in [parse_value(name)] if s]
    except Exception:
        pass  # Fail silently


def save():
    """Saves directives into ConfigFile."""
    configpaths = [ConfigFile]
    try:
        p = appdirs.user_config_dir(Title, appauthor=False)
        userpath = os.path.join(p, "%s.ini" % Title.lower())
        # Pick only userpath if exists, else try application folder first
        if os.path.isfile(userpath): configpaths = [userpath]
        else: configpaths.append(userpath)
    except Exception: pass

    section = "*"
    module = sys.modules[__name__]
    parser = configparser.RawConfigParser()
    parser.optionxform = str  # Force case-sensitivity on names
    parser.add_section(section)
    try:
        for path in configpaths:
            try: os.makedirs(os.path.split(path)[0])
            except Exception: pass
            try: f = open(path, "w")
            except Exception: continue  # for path
            else: break  # for path

        f.write("# %s configuration written on %s.\n" % 
                (Title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        for name in FileDirectives:
            try: parser.set(section, name, json.dumps(getattr(module, name)))
            except Exception: pass
        for name in OptionalFileDirectives:
            try:
                value = getattr(module, name, None)
                if Defaults.get(name) != value:
                    parser.set(section, name, json.dumps(value))
            except Exception: pass
        parser.write(f)
        f.close()
    except Exception:
        pass  # Fail silently
