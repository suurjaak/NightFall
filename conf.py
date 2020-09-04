# -*- coding: utf-8 -*-
"""
Application settings, and functionality to save/load some of them from
an external file. Configuration file has simple INI file format,
and all values are kept in JSON.

@author      Erki Suurjaak
@created     15.10.2012
@modified    04.09.2020
"""
from ConfigParser import RawConfigParser
import datetime
import json
import os
import sys

"""Program title."""
Title = "NightFall"

Version = "2.0.dev12"

VersionDate = "04.09.2020"

if getattr(sys, 'frozen', False):
    # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable) # likely relative
    ApplicationPath = os.path.abspath(sys.executable)
    ShortcutIconPath = ApplicationPath
    ResourceDirectory = os.path.join(getattr(sys, "_MEIPASS", ""), "res")
else:
    ApplicationDirectory = os.path.dirname(__file__) # likely relative
    FullDirectory = os.path.dirname(os.path.abspath(__file__))
    ApplicationPath = os.path.join(FullDirectory, "%s.py" % Title.lower())
    ResourceDirectory = os.path.join(FullDirectory, "res")
    ShortcutIconPath = os.path.join(ResourceDirectory, "icons.ico")

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = [
    "CurrentTheme", "Schedule", "ScheduleEnabled", "ThemeEnabled", "Themes",
]
"""List of user-modifiable attributes, saved if changed from default."""
OptionalFileDirectives = [
    "FadeSteps", "ThemeBitmapSize", "WindowTimeout", "WindowSize",
    "WindowSlideInEnabled", "WindowSlideOutEnabled",
    "WindowSlideInStep", "WindowSlideOutStep",
    "WindowSlideDelay", "UnsavedTheme",
]
Defaults = {}

"""Name of file where FileDirectives are kept."""
ConfigFile = "%s.ini" % os.path.join(ApplicationDirectory, Title.lower())

"""Settings window size in pixels, (w, h)."""
WindowSize = (400, 380)

"""Tooltip shown for the tray icon."""
TrayTooltip = "NightFall (double-click to toggle dimming)"

"""URL to program homepage."""
HomeUrl = "https://github.com/suurjaak/NightFall"

"""Clock central icon."""
ClockIcon = os.path.join(ResourceDirectory, "icon_48x48.png")

"""Size for theme bitmaps, as (w, h)."""
ThemeBitmapSize = (80, 48)

"""Application icons."""
WindowIcons = [os.path.join(ResourceDirectory, "icon_{0}x{0}.png".format(x))
               for x in (16, 32, 48)]

"""Icons for brigthness slider in theme editor."""
BrightnessIcons = [os.path.join(ResourceDirectory, "brightness_lo.png"),
                   os.path.join(ResourceDirectory, "brightness_hi.png")]

"""Number of milliseconds before settings window is hidden on losing focus."""
WindowTimeout = 30000

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

"""Number of steps to take during theme fadein/fadeout."""
FadeSteps = 20

"""Command-line parameter for running the program with settings minimized."""
StartMinimizedParameter = "--start-minimized"

"""Tray icon when dimming is enabled."""
TrayIconOn = os.path.join(ResourceDirectory, "tray_on.png")

"""Tray icon when dimming is disabled."""
TrayIconOff = os.path.join(ResourceDirectory, "tray_off.png")

"""Tray icon when dimming and schedule is on."""
TrayIconOnScheduled = os.path.join(ResourceDirectory, "tray_on_scheduled.png")

"""Tray icon when dimming is off and schedule is on."""
TrayIconOffScheduled = os.path.join(ResourceDirectory, "tray_off_scheduled.png")

"""List of all tray icons by state, [dimming now|schedule enabled]."""
TrayIcons = [TrayIconOff, TrayIconOffScheduled, TrayIconOn, TrayIconOnScheduled]

"""
Valid range for gamma coefficients, as (min, max). Lower coefficients cause the
system calls to fail for unknown reason.
"""
ValidColourRange = (59, 255)

"""Whether dimming is currently enabled."""
ThemeEnabled = False

"""Whether time-scheduled automatic dimming is enabled."""
ScheduleEnabled = False

"""Whether NightFall runs at computer startup."""
StartupEnabled = False

"""
Screen colour theme, as a list of 4 integers, standing for 3 RGB channels
and brightness, ranging from 0..255 (brightness 128 is 100%, 255 is superbright).
"""
CurrentTheme = [255, 211, 176,  57]

"""Gamma coefficients for normal display."""
NormalTheme = [255, 255, 255, 128]

"""Gamma coefficients being edited in theme editor."""
UnsavedTheme = None

"""Screen brightness for normal display."""
NormalBrightness = 128

"""Stored colour themes, as {name: [r, g, b, brightness]}."""
Themes = {
    "alpenglow":   [255, 211, 176,  57],
    "dawn":        [255, 189, 189,  82],
    "gloom":       [255, 255, 255,   0],
    "golden hour": [255, 255, 159,  77],
    "green visor": [159, 255, 159,  77],
    "no sleep":    [128, 128, 255, 128],
    "twilight":    [255, 179, 179,  57],
    "fireside":    [255, 128, 128, 128],
}

"""The dimming schedule, [1,0,..] per each minute."""
Schedule = []

"""
The default dimming schedule, [1,0,..] per each quarter hour
(21->05 on, 06->20 off).
"""
DefaultSchedule = [1] * 6 * 4 + [0] * 15 * 4 + [1] * 3 * 4

"""Information text shown on theme editor page."""
InfoEditorText = (
    "Fine-tune the components that make up the display: brightness \n"
    "(ranges from dark to superbright) and red-green-blue colour channels.\n\n"
    "A lot of the darker ranges will not be accepted by the graphics hardware."
)

"""Information text shown on about page."""
AboutText = """
<font face="Tahoma" size=2 color="%%(textcolour)s">
  <p>
  NightFall can change screen colour gamma and brightness settings, 
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
    %(pyinstaller)s
  </ul>
  </p>
</font>
""" % {"pyinstaller": '<li>PyInstaller, <a href="https://www.pyinstaller.org">'
                      '<font color="%(linkcolour)s">pyinstaller.org</font></a></li>'
                      if getattr(sys, 'frozen', False) else ""}


def load():
    """Loads FileDirectives from ConfigFile into this module's attributes."""
    global Defaults

    section = "*"
    module = sys.modules[__name__]
    Defaults.update({k: getattr(module, k) for k in FileDirectives + OptionalFileDirectives
                     if hasattr(module, k)}) if not Defaults else None

    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    try:
        parser.read(ConfigFile)

        def parse_value(name):
            try: # parser.get can throw an error if value not found
                value_raw = parser.get(section, name)
            except Exception:
                return None, False
            try: # Try to interpret as JSON, fall back on raw string
                value = json.loads(value_raw)
            except ValueError:
                value = value_raw
            return value, True

        for name in FileDirectives + OptionalFileDirectives:
            [setattr(module, name, v) for v, s in [parse_value(name)] if s]
    except Exception:
        pass # Fail silently


def save():
    """Saves FileDirectives into ConfigFile."""
    section = "*"
    module = sys.modules[__name__]
    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    parser.add_section(section)
    try:
        f = open(ConfigFile, "wb")

        f.write("# %s %s configuration written on %s.\n" % (Title, Version,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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
        pass # Fail silently
