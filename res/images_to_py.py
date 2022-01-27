"""
Simple small script for generating a nicely formatted Python module with
embedded binary resources and docstrings.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author    Erki Suurjaak
@created   26.01.2022
@modified  27.01.2022
------------------------------------------------------------------------------
"""
import base64
import datetime
import os
import shutil
import wx.tools.img2py

"""Target Python script to write."""
TARGET = os.path.join("..", "src", "nightfall", "images.py")

Q3 = '"""'

"""Application icons of different size and colour depth."""
APPICONS = [("Icon{0}x{0}_{1}bit.png".format(s, b),
             "NightFall application {0}x{0} icon, {1}-bit colour.".format(s, b))
            for s in (16, 32, 48, 64, 256) for b in (32, )]
IMAGES = {
    "Brightness_High.png":
        "Small image for brightness slider end in theme editor.",
    "Brightness_Low.png":
        "Small image for brightness slider start in theme editor.",
    "IconTray_Off.png":
        "Tray icon when theme is not applied.",
    "IconTray_Off_Paused.png":
        "Tray icon when theme is temporarily suspended.",
    "IconTray_Off_Scheduled.png":
        "Tray icon when theme is not applied and schedule is enabled.",
    "IconTray_On.png":
        "Tray icon when theme is applied.",
    "IconTray_On_Scheduled.png":
        "Tray icon when theme is applied and schedule is enabled.",
}
HEADER = """%s
Contains embedded image and icon resources for SQLitely. Auto-generated.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     26.01.2022
@modified    %s
------------------------------------------------------------------------------
%s
try:
    import wx
    from wx.lib.embeddedimage import PyEmbeddedImage
except ImportError:
    class PyEmbeddedImage(object):
        \"\"\"Data stand-in for wx.lib.embeddedimage.PyEmbeddedImage.\"\"\"
        def __init__(self, data):
            self.data = data
""" % (Q3, datetime.date.today().strftime("%d.%m.%Y"), Q3)


def create_py(target):
    global HEADER, APPICONS, IMAGES
    f = open(target, "w")
    f.write(HEADER)
    icons = [os.path.splitext(x)[0] for x, _ in APPICONS]
    icon_parts = [", ".join(icons[4*i:4*i+4]) for i in range(max(1, len(icons) // 4))]
    iconstr = ",\n        ".join(icon_parts)
    f.write("\n\n%s%s%s\ndef get_appicons():\n    icons = wx.IconBundle()\n"
            "    [icons.AddIcon(i.Icon) "
            "for i in [\n        %s\n    ]]\n    return icons\n" % (Q3,
        "Returns the application icon bundle, "
        "for several sizes and colour depths.",
        Q3, iconstr.replace("'", "").replace("[", "").replace("]", "")
    ))
    for filename, desc in APPICONS:
        name, extension = os.path.splitext(filename)
        f.write("\n\n%s%s%s\n%s = PyEmbeddedImage(\n" % (Q3, desc, Q3, name))
        data = base64.b64encode(open(filename, "rb").read())
        while data:
            f.write("    \"%s\"\n" % data[:72])
            data = data[72:]
        f.write(")\n")
    for filename, desc in sorted(IMAGES.items()):
        name, extension = os.path.splitext(filename)
        f.write("\n\n%s%s%s\n%s = PyEmbeddedImage(\n" % (Q3, desc, Q3, name))
        data = base64.b64encode(open(filename, "rb").read())
        while data:
            f.write("    \"%s\"\n" % data[:72])
            data = data[72:]
        f.write(")\n")
    f.close()


if "__main__" == __name__:
    create_py(TARGET)
