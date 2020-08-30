# -*- coding: utf-8 -*-
"""
Application settings, and functionality to save/load some of them from
an external file. Configuration file has simple INI file format,
and all values are kept in JSON.

@author      Erki Suurjaak
@created     15.10.2012
@modified    03.02.2013
"""
from ConfigParser import RawConfigParser
import datetime
import json
import os
import sys

"""Program title."""
Title = "NightFall"

Version = "1.2"

VersionDate = "03.02.2013"

if getattr(sys, 'frozen', False):
    # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable) # likely relative
    ApplicationPath = os.path.abspath(sys.executable)
    ShortcutIconPath = ApplicationPath
    ResourceDirectory = os.path.join(os.environ.get("_MEIPASS2", sys._MEIPASS),
                                     "res")
else:
    ApplicationDirectory = os.path.dirname(__file__) # likely relative
    FullDirectory = os.path.dirname(os.path.abspath(__file__))
    ApplicationPath = os.path.join(FullDirectory, "%s.py" % Title.lower())
    ResourceDirectory = os.path.join(FullDirectory, "res")
    ShortcutIconPath = os.path.join(ResourceDirectory, "icons.ico")

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = [
    "DimmingEnabled", "ScheduleEnabled", "DimmingFactor", "Schedule",
    "StoredFactors"
]

"""Name of file where FileDirectives are kept."""
ConfigFile = "%s.ini" % os.path.join(ApplicationDirectory, Title.lower())

"""Settings window size in pixels, (w, h)."""
SettingsFrameSize = (400, 450)

"""Tooltip shown for the tray icon."""
TrayTooltip = "NightFall (click to toggle options, right-click for menu)"

"""URL to program homepage."""
HomeUrl = "http://github.com/suurjaak/NightFall"

"""Saved factor list icon."""
ListIcon = os.path.join(ResourceDirectory, "listicon.png")

FactorIconSize = (100, 48)

"""Window icon."""
SettingsFrameIcon = os.path.join(ResourceDirectory, "icon.png")

"""Number of milliseconds before settings window is hidden on losing focus."""
SettingsFrameTimeout = 30000

"""Whether sliding the settings frame in/out of view is enabled."""
SettingsFrameSlideInEnabled = True
SettingsFrameSlideOutEnabled = False
"""Pixel step for settings frame movement during slidein/slideout."""
SettingsFrameSlideInStep = 6
SettingsFrameSlideOutStep = 5

"""Milliseconds between steps during slidein/slideout."""
SettingsFrameSlideDelay = 10

"""Milliseconds between steps during factor fadein/fadeout."""
FadeDelay = 30

"""Number of steps to take during factor fadein/fadeout."""
FadeSteps = 20

"""Command-line parameter for running the program with settings minimized."""
StartMinimizedParameter = "--start-minimized"

"""Tray icon when dimming is enabled."""
TrayIconOn = os.path.join(ResourceDirectory, "tray_on.png")

"""Tray icon when dimming is disabled."""
TrayIconOff = os.path.join(ResourceDirectory, "tray_off.png")

"""Tray icon when dimming and schedule is on."""
TrayIconOnScheduled = \
    os.path.join(ResourceDirectory, "tray_on_scheduled.png")

"""Tray icon when dimming is off and schedule is on."""
TrayIconOffScheduled = \
    os.path.join(ResourceDirectory, "tray_off_scheduled.png")

"""List of all tray icons by state, [dimming now|schedule enabled]."""
TrayIcons = \
    [TrayIconOff, TrayIconOffScheduled, TrayIconOn, TrayIconOnScheduled]

"""
Valid range for gamma coefficients, as (min, max). Lower coefficients cause the
system calls to fail for some reason.
"""
ValidColourRange = (59, 255)

"""Whether dimming is currently enabled."""
DimmingEnabled = False

"""Whether time-scheduled automatic dimming is enabled."""
ScheduleEnabled = False

"""Whether NightFall runs at computer startup."""
StartupEnabled = False

"""
Screen dimming factor, as a list of 4 integers, standing for brightness and 3
RGB channels, ranging from 0..255 (brightness at 128 is 100%, lower is darker).
"""
DimmingFactor = [82, 255, 189, 189]

"""Default gamma coefficients for dimmed display."""
DefaultDimmingFactor = [82, 255, 189, 189]

"""Gamma coefficients for normal display."""
NormalDimmingFactor = [128, 255, 255, 255]

"""Screen brightness for normal display."""
NormalBrightness = 128

"""Pre-stored dimming factors."""
StoredFactors = [
    [57, 255, 179, 179], [57, 255, 211, 176], [128, 255, 128, 128],
    [128, 128, 128, 255], [88, 168, 168, 255], [0, 255, 255, 255],
    [26, 255, 212, 212], [127, 255, 255, 128], [77, 255, 255, 159],
    [77, 159, 255, 159], [83, 159, 236, 159], [82, 255, 189, 189]
]
StoredFactorsNew = {
    "name": [0, 0, 0, 0],
}

"""The dimming schedule, [1,0,..] per each minute."""
Schedule = []

"""
The default dimming schedule, [1,0,..] per each quarter hour
(21->05 on, 06->20 off).
"""
DefaultSchedule = [1] * 6 * 4 + [0] * 15 * 4 + [1] * 3 * 4

"""Information text shown on configuration page."""
InfoText = "%(name)s can dim screen colors for a more natural feeling" \
    " during late hours.\nDimming can be scheduled in detail, or activated " \
    "manually at any time." % {"name": Title}

"""Information text shown on expert settings page."""
InfoDetailedText = "Fine-tune the individual factors that make up the " \
                   "display: brightness \n(ranges from dark to superbright) " \
                   "and red-green-blue colour channels.\n\n" \
                   "A lot of the darker ranges will not be accepted by" \
                   " the graphics hardware."



"""Error text shown if applying a factor failed."""
FactorFailedText = "Selected combo is invalid"

def load():
    """Loads FileDirectives from ConfigFile into this module's attributes."""
    section = "*"
    module = sys.modules[__name__]
    parser = RawConfigParser()
    parser.optionxform = str # Force case-sensitivity on names
    try:
        parser.read(ConfigFile)
        for name in FileDirectives:
            try: # parser.get can throw an error if not found
                value_raw = parser.get(section, name)
                success = False
                # First, try to interpret as JSON
                try:
                    value = json.loads(value_raw)
                    success = True
                except:
                    pass
                if not success:
                    # JSON failed, try to eval it
                    try:
                        value = eval(value_raw)
                        success = True
                    except:
                        # JSON and eval failed, fall back to string
                        value = value_raw
                        success = True
                if success:
                    setattr(module, name, value)
            except:
                pass
    except Exception, e:
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
        f.write("# %s configuration autowritten on %s.\n" % (
            ConfigFile, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        for name in FileDirectives:
            try:
                value = getattr(module, name)
                parser.set(section, name, json.dumps(value))
            except:
                pass
        parser.write(f)
        f.close()
    except Exception, e:
        pass # Fail silently
