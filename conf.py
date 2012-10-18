# -*- coding: utf-8 -*-
"""
Application settings, and functionality to save/load some of them from
an external file. Configuration file has simple INI file format,
and all values are kept in JSON.

@author      Erki Suurjaak
@created     15.10.2012
@modified    18.10.2012
"""
from ConfigParser import RawConfigParser
import datetime
import json
import os
import sys

"""Program title."""
Title = "NightFall"

Version = "0.1.1a"

VersionDate = "18.10.2012"

if getattr(sys, 'frozen', False):
    # Running as a pyinstaller executable
    ApplicationDirectory = os.path.dirname(sys.executable) # likely relative
    ApplicationPath = os.path.abspath(sys.executable)
    ShortcutIconPath = ApplicationPath
    ResourceDirectory = os.path.join(os.environ.get("_MEIPASS2", sys._MEIPASS), "res")
else:
    ApplicationDirectory = os.path.dirname(__file__)       # likely relative
    FullDirectory = os.path.dirname(os.path.abspath(__file__))
    ApplicationPath = os.path.join(FullDirectory, "%s.py" % Title.lower())
    ResourceDirectory = os.path.join(FullDirectory, "res")
    ShortcutIconPath = os.path.join(ResourceDirectory, "icons.ico")

"""List of attribute names that can be saved to and loaded from ConfigFile."""
FileDirectives = [
    "DimmingEnabled", "ScheduleEnabled", "DimmingFactor", "Schedule"
]

"""Name of file where FileDirectives are kept."""
ConfigFile = "%s.ini" % os.path.join(ApplicationDirectory, Title.lower())

"""Settings window size in pixels, (w, h)."""
SettingsFrameSize = (-1, 250)

"""Tooltip shown for the tray icon."""
TrayTooltip = "NightFall (click to toggle options, right-click for menu)"

"""Window icon."""
SettingsFrameIcon = os.path.join(ResourceDirectory, "icon.png")

"""Number of milliseconds before settings window is hidden on losing focus."""
SettingsFrameTimeout = 10000

"""Tray icon when dimming is enabled."""
TrayIconOn = os.path.join(ResourceDirectory, "tray_on.png")

"""Tray icon when dimming is disabled."""
TrayIconOff = os.path.join(ResourceDirectory, "tray_off.png")

"""Tray icon when dimming is disabled."""
TrayIconOnSchedule = \
    os.path.join(ResourceDirectory, "tray_schedule.png")

"""
Valid range for gamma coefficients, as (min, max). Lower coefficients cause the
system calls to fail for some reason.
"""
ValidGammaRange = (0.23, 1.)

"""Whether dimming is currently enabled."""
DimmingEnabled = False

"""Whether time-scheduled automatic dimming is enabled."""
ScheduleEnabled = True

"""Whether NightFall runs at computer startup."""
StartupEnabled = False

"""Gamma coefficients for RGB channels, ranging 0..1."""
DimmingFactor = [0.94, 0.52, 0.45]

"""Default gamma coefficients for dimmed display."""
DefaultDimmingFactor = [0.94, 0.52, 0.45]

"""Gamma coefficients for normal display."""
NormalDimmingFactor = [1, 1, 1]

"""The dimming schedule, [1,0,..] per each hour."""
Schedule = []

"""The default dimming schedule, [1,0,..] per each hour."""
DefaultSchedule = [1] * 6 + [0] * 15 + [1] * 3 # 21->05 on, 06->20 off


"""Copyright symbol and year string."""
Copyright = "\xA9 2012"

"""Information text shown on settings page."""
InfoText = ("%(name)s can dim screen color gamma for a more natural feeling" + 
    " during nocturnal hours. %(copy)s, Erki Suurjaak. Version " + 
    "%(ver)s, %(date)s.") % {
    "copy": Copyright.decode("latin1"), "name": Title, "ver": Version,
    "date": VersionDate
}


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
