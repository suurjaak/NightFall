NightFall
===========

A small tray program for making screen colours darker and softer during
late hours. Currently works under Windows, *might* work under Linux/OSX.

Windows binaries at http://suurjaak.github.com/NightFall.


Using The Program
-----------------

Run "python nightfall.py", or launch the precompiled Windows executable.
It will stay in the system tray as a grey or orange moon icon, depending on
being active, and will dim the screen on command or according to hours
scheduled in settings.


Dependencies
------------

If running as a Python script, NightFall requires Python 2.6+ and wx.Python
2.8+ (http://wxpython.org/)


Attribution
-----------

NightFall includes bits of code in gamma.py from PsychoPy 1.75
(http://www.psychopy.org/epydoc/psychopy.gamma-pysrc.html), released under the
compatible GNU General Public License v3; and from Windows Routines 2.2.1 by
Jason R. Coombs,
(http://pydoc.net/jaraco.windows/2.2.1/jaraco.windows.error), released under
the MIT License.
Windows binaries built with PyInstaller 2.0 (http://www.pyinstaller.org/).


License
-------

(The MIT License)

Copyright (C) 2012 by Erki Suurjaak

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
