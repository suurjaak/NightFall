#-*- coding: utf-8 -*-
"""
Program entry point.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     23.01.2022
@modified    23.01.2022
------------------------------------------------------------------------------
"""
try: from urllib.parse import quote_plus           # Py3
except ImportError: from urllib import quote_plus  # Py2
import warnings
import sys

import wx

from . import conf
from . nightfall import NightFall


def run():
    warnings.simplefilter("ignore", UnicodeWarning)
    singlename = quote_plus("%s-%s" % (conf.Title, conf.ApplicationFile))
    singlechecker = wx.SingleInstanceChecker(singlename)
    if singlechecker.IsAnotherRunning(): sys.exit()

    app = NightFall(redirect=True) # stdout and stderr redirected to wx popup
    mylocale = wx.Locale(wx.LANGUAGE_ENGLISH) # Avoid dialog buttons in native language
    app.MainLoop()
    del singlechecker
