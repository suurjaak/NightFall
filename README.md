NightFall
=========

A screen color dimmer for late hours.

NightFall is a tray program to change screen brightness and colour gamma settings
on schedule, in order to achieve a more natural feeling during late hours.

Looking at a lit screen in a dark room can interfere with the sleep cycle,
and is hard on the eyes in general.
NightFall can provide a warm-coloured darker screen on desktop and laptop 
computers alike.

Comes with a number of pre-defined brightness and colour themes;
new themes can be added.

[![Screenshots](https://raw.github.com/suurjaak/NightFall/gh-pages/img/th_collage.png)](https://raw.github.com/suurjaak/NightFall/gh-pages/img/collage.png)

Windows binaries and more screenshots at https://suurjaak.github.io/NightFall.


Using The Program
-----------------

NightFall stays in the system tray as a grey or orange moon icon,
dimming the screen on command or according to set schedule
(grey icon: dimming inactive, orange: dimming applied).

Clicking the tray icon shows or hides the program window.
Double-clicking the tray icon toggles dimming on or off.
Right-clicking the tray icon opens options menu.

Program window has tabs for managing the time schedule and startup,
managing saved themes, and editing theme brightness and colour.
Schedule can be set in quarter-hour steps.
Applied theme can be suspended for a selected number of minutes.

Using the 24h clock face in schedule tab:
- left-click to toggle the quarter hour on
- right-click to toggle the quarter hour off
- left-click and drag to grow or shrink the selection
- right-click and drag to clear selection
- double-click to toggle the entire hour on or off
- right-double-click to toggle the entire hour off
- scroll mouse wheel to grow or shrink the selection
- double-click on center to toggle dimming on or off


Works under Windows, *might* work under Linux/OSX.

If launching the program manually, `--start-minimized` command-line option
will auto-hide the program window.

If using the source distribution, open a terminal to src-directory,
and run `python -m nightfall`.


Dependencies
------------

If running as a Python script, NightFall requires Python 3.5+ or Python 2.7,
and the following 3-rd party Python packages:

- appdirs (https://pypi.org/project/appdirs)
- wxPython 4.0+ (https://wxpython.org)

All dependencies can be installed by running `pip install -r requirements.txt`
in NightFall source distribution folder.


Attribution
-----------

Built with Python (https://python.org) and wxPython (https://wxpython.org).

Includes several icons from Fugue Icons,
(c) 2010 Yusuke Kamiyamane, https://p.yusukekamiyamane.com.

Windows binaries built with PyInstaller (https://www.pyinstaller.org).

Installers created with Nullsoft Scriptable Install System
(https://nsis.sourceforge.io).


License
-------

Copyright (c) 2012 by Erki Suurjaak.
Released as free open source software under the MIT License,
see [LICENSE.md](LICENSE.md) for full license text.
