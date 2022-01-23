#-*- coding: utf-8 -*-
"""
Functionality for handling screen device gamma ramps.

Accessing gamma ramp functionality on the basis of PsychoPy 1.75 by Jonathan Peirce.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     15.10.2012
@modified    04.09.2020
------------------------------------------------------------------------------
"""
import ctypes
import ctypes.util
import sys

# import platform specific C++ libs for controlling gamma
if "win32" == sys.platform: # Using the following DLLs: gdi32, kernel32, user32
    import ctypes.wintypes
elif "darwin" == sys.platform:
    carbon = ctypes.CDLL("/System/Library/Carbon.framework/Carbon")
elif sys.platform.startswith("linux"):
    xf86vm = ctypes.CDLL(ctypes.util.find_library("Xxf86vm"))
    xlib = ctypes.CDLL(ctypes.util.find_library("X11"))


def set_screen_gamma(factor):
    """
    Changes the brightness and color gamma of the screen.

    @param   factor       a 4-byte list, with first 3 being RGB values (0..255)
                          and last being brightness. Brightness is regular at
                          128 and brighter than normal if above 128.
    @return               True on success, False on failure
    """
    ramp = [[], [], []]
    """
    @from SetDeviceGammaRamp function Windows documentation:
        The gamma ramp is specified in three arrays of 256 WORD elements each,
        which contain the mapping between RGB values in the frame buffer and
        digital-analog-converter values. The sequence of the arrays is red,
        green, blue. The RGB values must be stored in the most significant bits
        of each WORD to increase DAC independence.
        Any entry in the ramp must be within 32768 of the identity value.

    @from http://tech.groups.yahoo.com/group/psychtoolbox/message/6984,
    "Re: Gamma Table constraints (Windows)" by Brian J. Stankiewicz:
        There are two "regions" that have illegal LUT (lookup table) values.
        The LUT Entries below 128 can be characterized by:
          IllegalRegion > 0.505+LUTEntry*0.39
        and those above can be characterized by:
          IllegalRegion < -0.5093+LUTEntry*0.39
    """
    for i in range(256):
        val = min(i * (factor[-1] + 128), 65535)
        [ramp[j].append(int(val * factor[j] / 255.)) for j in range(3)]

    result = True
    try: set_gamma_ramp(ramp)
    except Exception: result = False
    return result


def get_screen_device():
    """Returns the platform-specific screen device identifier."""
    if not hasattr(get_screen_device, "device"):
        if "win32" == sys.platform:
            get_screen_device.device = ctypes.windll.user32.GetDC(0)
        elif "darwin" == sys.platform:
            count = ctypes.c_uint32()
            carbon.CGGetActiveDisplayList(0, None, byref(count))
            displays = (ctypes.c_void_p * count.value)()
            carbon.CGGetActiveDisplayList(count.value, displays, byref(count))
            get_screen_device.device = displays[0]
        elif sys.platform.startswith("linux"):
            class Display(ctypes.Structure):
                __slots__ = []
            Display._fields_ = [("_opaque_struct", ctypes.c_int)]
            XOpenDisplay = xlib.XOpenDisplay
            XOpenDisplay.restype = ctypes.POINTER(Display)
            XOpenDisplay.argtypes = [ctypes.c_char_p]
            get_screen_device.device = XOpenDisplay("")
    device = get_screen_device.device
    return device


def set_gamma_ramp(ramp):
    """
    Sets the hardware look-up table, using platform-specific ctypes functions.

    @param   ramp  a 3x256 or 3x1024 list of values within 0..65535
    """
    device = get_screen_device()

    # Initialize platform-specific ramp structure for system call
    type_c = ctypes.c_float if "darwin" == sys.platform else ctypes.c_uint16
    ramp_c = ((type_c * len(ramp[0])) * len(ramp))()
    for i, column in enumerate(ramp):
        for j, value in enumerate(column):
            ramp_c[i][j] = value

    if "win32" == sys.platform:
        success = ctypes.windll.gdi32.SetDeviceGammaRamp(device, ramp_c)
        if not success:
            code = ctypes.windll.kernel32.GetLastError()
            msg = "SetDeviceGammaRamp failed [error %s]" % code
            raise Exception(msg)
    elif "darwin" == sys.platform:
        error = carbon.CGSetDisplayTransferByTable(device, len(ramp_c[0]),
                   ramp_c[0], ramp_c[1], ramp_c[2])
        if error:
            msg = "CGSetDisplayTransferByTable failed [error %s]" % error
            raise Exception(msg)
    elif sys.platform.startswith("linux"):
        success = xf86vm.XF86VidModeSetGammaRamp(device, 0, len(ramp_c[0]),
                    ramp_c[0], ramp_c[1], ramp_c[2])
        if not success:
            raise Exception("XF86VidModeSetGammaRamp failed")
