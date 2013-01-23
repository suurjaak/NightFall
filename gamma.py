#-*- coding: utf-8 -*-
"""
Functionality for handling screen device gamma ramps.

Accessing device ramp functionality mostly from PsychoPy, (c) Jonathan Peirce,
formatting Windows errors from Windows Routines by Jason R. Coombs, both
released under compatible open source licences.

@from SetDeviceGammaRamp function Windows documentation:
    The gamma ramp is specified in three arrays of 256 WORD elements each,
    which contain the mapping between RGB values in the frame buffer and
    digital-analog-converter values. The sequence of the arrays is red,
    green, blue. The RGB values must be stored in the most significant bits
    of each WORD to increase DAC independence.
    Any entry in the ramp must be within 32768 of the identity value.

@from http://tech.groups.yahoo.com/group/psychtoolbox/message/6984,
"Re: Gamma Table constraints (Windows)" by Brian J. Stankiewicz:
    There are two "regions" that have illegal LUT values. The LUT Entries
    below 128 can be characterized by:
      IllegalRegion > 0.505+LUTEntry*0.39
    and those above can be characterized by:
      IllegalRegion < -0.5093+LUTEntry*0.39

@author      Erki Suurjaak
@created     15.10.2012
@modified    22.01.2013
"""

import __builtin__
import ctypes
import ctypes.util
import ctypes.wintypes
from ctypes import c_uint32, c_void_p, c_int, c_char_p, Structure, POINTER
import numpy
import platform
import sys
import wx

device = None # Platform-specific screen device context


# import platform specific C++ libs for controlling gamma 
if "win32" == sys.platform: 
    from ctypes import windll 
if "darwin" == sys.platform: 
    carbon = ctypes.CDLL("/System/Library/Carbon.framework/Carbon") 
if sys.platform.startswith("linux"): 
    #we need XF86VidMode 
    xf86vm=ctypes.CDLL(ctypes.util.find_library("Xxf86vm")) 
    xlib = ctypes.CDLL(ctypes.util.find_library("X11")) 


def set_screen_factor(factor):
    """
    Changes the brightness and color gamma of the screen.

    @param   factor       a 4-byte list, with first being brightness and last 3
                          being RGB values (0..255). Brightness is regular at
                          128 and brighter than normal if above 128.
    @return               True on success, False on failure
    """
    global device, newRamp
    init_device()

    ramp = [[], [], []] # will be [3][256]

    for i in range(256):
        val = min(i * (factor[0] + 128), 65535)
        [ramp[j].append(int(val * factor[j + 1] / 255.)) for j in range(3)]

    ramp = numpy.array(ramp).astype(numpy.uint16)
    try:
        set_gamma_ramp(ramp)
        result = True
    except Exception, e:
        result = False

    return result


def init_device():
    """Initializes the platform-specific screen device instance."""
    global device
    if device is None:
        if "win32" ==  sys.platform: 
            device = wx.ScreenDC()
        if "darwin" == sys.platform: 
            count = c_uint32()
            carbon.CGGetActiveDisplayList(0, None, byref(count))
            displays = (c_void_p * count.value)()
            carbon.CGGetActiveDisplayList(count.value, displays, byref(count))
            device = displays[0]
        if sys.platform.startswith("linux"): 
            class Display(Structure):
                __slots__ = []
            Display._fields_ = [("_opaque_struct", c_int)]
            XOpenDisplay = xlib.XOpenDisplay
            XOpenDisplay.restype = POINTER(Display)
            XOpenDisplay.argtypes = [c_char_p]
            device = XOpenDisplay("")


def set_gamma_ramp(ramp): 
    """
    Sets the hardware look-up table, using platform-specific ctypes functions. 
    Ramp should be provided as 3x256 or 3x1024 array in range 0:1.0 
    """ 
    global device
    init_device()

    if "win32" == sys.platform:
        success = windll.gdi32.SetDeviceGammaRamp(device.GetHDC(), ramp.ctypes) 
        if not success:
            errorcode = windll.kernel32.GetLastError()
            errormsg = format_system_message(errorcode).strip()
            raise Exception, "SetDeviceGammaRamp failed: %s [error %s]" \
                             % (errormsg, errorcode)

    if "darwin" == sys.platform:
        ramp = (ramp).astype(numpy.float32)
        LUTlength = ramp.shape[1]
        error = carbon.CGSetDisplayTransferByTable(device, LUTlength,
                   ramp[0,:].ctypes, ramp[1,:].ctypes, ramp[2,:].ctypes)
        if error:
            raise AssertionError, "CGSetDisplayTransferByTable failed"

    if sys.platform.startswith("linux"):
        success = xf86vm.XF86VidModeSetGammaRamp(device, 0, 256,
                    ramp[0,:].ctypes, ramp[1,:].ctypes, ramp[2,:].ctypes)
        if not success:
            raise AssertionError, "XF86VidModeSetGammaRamp failed" 


def get_gamma_ramp():      
    """Ramp will be returned as 3x256 array in range 0:1""" 
    global device
    init_device()

    if "win32" == sys.platform:
        origramps = numpy.empty((3, 256), dtype=numpy.uint16) # init RGB ramps
        success = windll.gdi32.GetDeviceGammaRamp(device.GetHDC(),
                                                  origramps.ctypes) 
        if not success:
            raise AssertionError, "SetDeviceGammaRamp failed" 
        origramps.byteswap(True) 
        origramps = origramps / 255.0 #rescale to 0:1 
         
    if "darwin" == sys.platform:
        origramps = numpy.empty((3, 256), dtype=numpy.float32) # init RGB ramps
        n = numpy.empty([1], dtype=numpy.int) 
        error = carbon.CGGetDisplayTransferByTable(device, 256, 
                     origramps[0,:].ctypes, origramps[1,:].ctypes,
                     origramps[2,:].ctypes, n.ctypes)
        if error:
            raise AssertionError, "CGSetDisplayTransferByTable failed" 
 
    if sys.platform.startswith("linux"): 
        origramps = numpy.empty((3, 256), dtype=numpy.uint16)  
        success = xf86vm.XF86VidModeGetGammaRamp(device, 0, 256, 
                      origramps[0,:].ctypes, origramps[1,:].ctypes,
                      origramps[2,:].ctypes) 
        if not success:
            raise AssertionError, "XF86VidModeGetGammaRamp failed" 
         
    return origramps 


def format_system_message(errno):
    """
    Call FormatMessage with a system error number to retrieve
    the descriptive error message.
    """
    # first some flags used by FormatMessageW
    ALLOCATE_BUFFER = 0x100
    ARGUMENT_ARRAY = 0x2000
    FROM_HMODULE = 0x800
    FROM_STRING = 0x400
    FROM_SYSTEM = 0x1000
    IGNORE_INSERTS = 0x200
  
    # Let FormatMessageW allocate the buffer (we'll free it below)
    # Also, let it know we want a system error message.
    flags = ALLOCATE_BUFFER | FROM_SYSTEM
    source = None
    message_id = errno
    language_id = 0
    result_buffer = ctypes.wintypes.LPWSTR()
    buffer_size = 0
    arguments = None
    bytes = ctypes.windll.kernel32.FormatMessageW(
        flags,
        source,
        message_id,
        language_id,
        ctypes.byref(result_buffer),
        buffer_size,
        arguments,
        )
    # note the following will cause an infinite loop if GetLastError
    #  repeatedly returns an error that cannot be formatted, although
    #  this should not happen.
    if bytes == 0:
        raise WindowsError()
    message = result_buffer.value
    ctypes.windll.kernel32.LocalFree(result_buffer)
    return message
