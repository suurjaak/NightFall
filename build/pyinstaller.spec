# -*- mode: python -*-
"""
Pyinstaller spec file for Skyperious, produces a 32-bit or 64-bit executable,
depending on current environment.

@created   18.10.2012
@modified  12.09.2020
"""
import os
import struct
import sys

os.chdir("..")
ROOTPATH  = APPPATH = os.getcwd()
sys.path.append(APPPATH)

import conf


DO_DEBUG_VERSION = False
DO_WINDOWS = ("nt" == os.name)

def do_64bit(): return (struct.calcsize("P") * 8 == 64)


app_file = "nightfall_%s%s" % (conf.Version, "_x64" if do_64bit() else "")
entrypoint = os.path.join(ROOTPATH, "nightfall.py")
if DO_WINDOWS:
    app_file += ".exe"


a = Analysis(
    ["nightfall.py"],
    excludes=["FixTk", "numpy", "tcl", "tk", "_tkinter", "tkinter", "Tkinter"],
)
# Add all image resources used by the script
for i in os.listdir("res"):
    a.datas.append((os.path.join("res", i), os.path.join("res", i), "DATA"))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts + ([("v", "", "OPTION")] if DO_DEBUG_VERSION else []),
    a.binaries,
    a.zipfiles,
    a.datas,
    name=os.path.join("dist", app_file),
    debug=DO_DEBUG_VERSION, # Verbose or non-verbose debug statements printed
    strip=False,  # EXE and all shared libraries run through cygwin's strip, tends to render Win32 DLLs unusable
    upx=True,     # Using Ultimate Packer for eXecutables
    icon=os.path.join(ROOTPATH, "build", "nightfall.ico"),
    console=False # Use the Windows subsystem executable instead of the console one
)
