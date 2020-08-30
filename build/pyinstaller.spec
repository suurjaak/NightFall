# -*- mode: python -*-
# Spec file for pyinstaller.
# To get this spec, run python Setup.py <specfile> in pyinstaller\ directory.
# Copy to pyinstaller\gui and in pyinstaller\ run python Build.py
import os
import platform
import sys
sys.path.append("")

import conf

a = Analysis([("nightfall.py")],)
# Add all image resources used by the script
for i in ["icon.png", "icons.ico", "listicon.png", "tray_off.png",
          "tray_on.png", "tray_off_scheduled.png", "tray_on_scheduled.png"]:
	a.datas.append((os.path.join("res", i), os.path.join("res", i), "DATA"))

pyz = PYZ(a.pure)

exename = "nightfall_%s.exe" % conf.Version
if "64" in platform.architecture()[0]:
    exename = "nightfall_%s_x64.exe" % conf.Version
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=os.path.join("dist", exename),
    debug=False,  # Verbose or non-verbose 
    strip=False,  # EXE and all shared libraries run through cygwin's strip, tends to render Win32 DLLs unusable
    upx=True,     # Using Ultimate Packer for eXecutables
    icon=os.path.join("res", "icons.ico"),
    console=False # Use the Windows subsystem executable instead of the console one
)
