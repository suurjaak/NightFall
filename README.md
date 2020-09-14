NightFall
=========

A small tray program that can change screen brightness and colour gamma settings
on schedule, in order to achieve a more natural feeling during late hours.

Looking at a lit screen in a dark room can interfere with the sleep cycle,
NightFall can provide a warm-coloured darker screen on desktop and laptop 
computers alike.

Comes with a number of pre-defined brightness and colour themes, you can
also create and save your own themes.

[![Screenshots](https://raw.github.com/suurjaak/NightFall/gh-pages/img/th_collage.png)](https://raw.github.com/suurjaak/NightFall/gh-pages/img/collage.png)

Windows binaries and more screenshots at https://suurjaak.github.io/NightFall.


Using The Program
-----------------

NightFall stays in the system tray as a grey or orange moon icon, depending on
being active, dimming the screen on command or according to the set schedule.
Schedule can be set in quarter-hour steps.

Works under Windows, *might* work under Linux/OSX.

If launching the program manually, `--start-minimized` command-line option
will auto-hide the settings window initially.

Run `python nightfall.py` if using the source distribution.


Dependencies
------------

If running as a Python script, NightFall requires Python 2.7 and wxPython
4.0+ (https://wxpython.org)


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
