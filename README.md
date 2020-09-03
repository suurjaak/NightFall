NightFall
=========

A small tray program for making screen colours darker and softer during
late hours. Confirmed to work under Windows, *might* work under Linux/OSX.

Windows binaries at https://suurjaak.github.io/NightFall.


Using The Program
-----------------

Run "python nightfall.py", or launch the precompiled Windows executable.
It will stay in the system tray as a grey or orange moon icon, depending on
being active, and will dim the screen on command or according to hours
scheduled in settings.


Dependencies
------------

If running as a Python script, NightFall requires Python 2.7 and wx.Python
4.0+ (http://wxpython.org)


Attribution
-----------

NightFall includes bits of code in gamma.py from PsychoPy 1.75
(http://www.psychopy.org/epydoc/psychopy.gamma-pysrc.html), released under the
compatible GNU General Public License v3; and from Windows Routines 2.2.1 by
Jason R. Coombs,
(http://pydoc.net/jaraco.windows/2.2.1/jaraco.windows.error), released under
the MIT License.

Windows binaries built with PyInstaller (http://www.pyinstaller.org).


License
-------

Copyright (c) 2012 by Erki Suurjaak.
Released as free open source software under the MIT License,
see [LICENSE.md](LICENSE.md) for full license text.
