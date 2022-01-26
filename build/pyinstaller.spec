# -*- mode: python -*-
"""
Pyinstaller spec file for NightFall, produces a 32-bit or 64-bit executable,
depending on current environment.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@created   18.10.2012
@modified  26.01.2022
------------------------------------------------------------------------------
"""
import os
import struct
import sys

NAME        = "nightfall"
DO_DEBUGVER = False
DO_64BIT    = (struct.calcsize("P") * 8 == 64)

BUILDPATH = os.path.dirname(os.path.abspath(SPEC))
ROOTPATH  = os.path.dirname(BUILDPATH)
APPPATH   = os.path.join(ROOTPATH, "src")
os.chdir(ROOTPATH)
sys.path.insert(0, APPPATH)

from nightfall import conf

app_file = "%s_%s%s%s" % (NAME, conf.Version, "_x64" if DO_64BIT else "",
                          ".exe" if "nt" == os.name else "")
entrypoint = os.path.join(ROOTPATH, "launch.py")

with open(entrypoint, "w") as f:
    f.write("from %s import main; main.run()" % NAME)


a = Analysis(
    [entrypoint],
    excludes=["FixTk", "numpy", "tcl", "tk", "_tkinter", "tkinter", "Tkinter"],
)
# Add all image resources used by the script
for i in os.listdir("res"):
    a.datas.append((os.path.join("res", i), os.path.join("res", i), "DATA"))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts + ([("v", "", "OPTION")] if DO_DEBUGVER else []),
    a.binaries,
    a.zipfiles,
    a.datas,
    name=os.path.join("dist", app_file),
    debug=DO_DEBUGVER, # Verbose or non-verbose debug statements printed
    strip=False,  # EXE and all shared libraries run through cygwin's strip, tends to render Win32 DLLs unusable
    upx=True,     # Using Ultimate Packer for eXecutables
    icon=os.path.join(ROOTPATH, "res", "Icon.ico"),
    console=False # Use the Windows subsystem executable instead of the console one
)

try: os.remove(entrypoint)
except Exception: pass
