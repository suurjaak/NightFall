#-*- coding: utf-8 -*-
"""
Stand-alone GUI components for wx:

- BitmapComboBox(wx.adv.OwnerDrawnComboBox):
  Dropdown combobox for showing bitmaps identified by name.

- BitmapListCtrl(wx.lib.agw.thumbnailctrl.ThumbnailCtrl):
  A ThumbnailCtrl that shows bitmaps, without requiring images on disk.

- ClockSelector(wx.Panel):
  A 24h clock for selecting any number of periods from 24 hours,
  with a quarter hour step by default.

- ColourManager(object):
  Updates managed component colours on Windows system colour change.


------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     25.01.2022
@modified    27.01.2022
------------------------------------------------------------------------------
"""
import collections
import datetime
import math
import sys

import wx
import wx.lib.agw.thumbnailctrl
import wx.lib.agw.ultimatelistctrl
import wx.lib.newevent
try: import wx.lib.agw.scrolledthumbnail as thumbnailevents     # Py3
except ImportError: thumbnailevents = wx.lib.agw.thumbnailctrl  # Py2


"""Event class and event binder for change-events in ClockSelector."""
ClockSelectorEvent, EVT_CLOCK_SELECTOR = wx.lib.newevent.NewEvent()

"""Event class and event binder for double-clicking center of ClockSelector."""
ClockCenterEvent, EVT_CLOCK_CENTER = wx.lib.newevent.NewEvent()


class KEYS(object):
    """Keycode groupings, includes numpad keys."""
    UP         = (wx.WXK_UP,       wx.WXK_NUMPAD_UP)
    DOWN       = (wx.WXK_DOWN,     wx.WXK_NUMPAD_DOWN)
    LEFT       = (wx.WXK_LEFT,     wx.WXK_NUMPAD_LEFT)
    RIGHT      = (wx.WXK_RIGHT,    wx.WXK_NUMPAD_RIGHT)
    PAGEUP     = (wx.WXK_PAGEUP,   wx.WXK_NUMPAD_PAGEUP)
    PAGEDOWN   = (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN)
    ENTER      = (wx.WXK_RETURN,   wx.WXK_NUMPAD_ENTER)
    INSERT     = (wx.WXK_INSERT,   wx.WXK_NUMPAD_INSERT)
    DELETE     = (wx.WXK_DELETE,   wx.WXK_NUMPAD_DELETE)
    HOME       = (wx.WXK_HOME,     wx.WXK_NUMPAD_HOME)
    END        = (wx.WXK_END,      wx.WXK_NUMPAD_END)
    SPACE      = (wx.WXK_SPACE,    wx.WXK_NUMPAD_SPACE)
    BACKSPACE  = (wx.WXK_BACK, )
    TAB        = (wx.WXK_TAB,      wx.WXK_NUMPAD_TAB)
    ESCAPE     = (wx.WXK_ESCAPE, )

    ARROW      = UP + DOWN + LEFT + RIGHT
    PAGING     = PAGEUP + PAGEDOWN
    NAVIGATION = ARROW + PAGING + HOME + END + TAB
    COMMAND    = ENTER + INSERT + DELETE + SPACE + BACKSPACE + ESCAPE



class ColourManager(object):
    """Updates managed component colours on Windows system colour change."""
    ctrls = collections.defaultdict(dict) # {ctrl: {prop name: colour}}


    @classmethod
    def Init(cls, window):
        """Hooks WM_SYSCOLORCHANGE event to window on Windows."""
        window.Bind(wx.EVT_SYS_COLOUR_CHANGED, cls.OnSysColourChange)


    @classmethod
    def Manage(cls, ctrl, prop, colour):
        """
        Starts managing a control colour property.

        @param   ctrl    wx component
        @param   prop    property name like "BackgroundColour",
                         tries using ("Set" + prop)() if no such property
        @param   colour  colour name or [r, g, b]
                         or system colour ID like wx.SYS_COLOUR_WINDOW
        """
        if not ctrl: return
        cls.ctrls[ctrl][prop] = colour
        cls.UpdateControlColour(ctrl, prop, colour)


    @classmethod
    def OnSysColourChange(cls, event):
        """Handler for system colour change, updates managed controls."""
        event.Skip()
        cls.UpdateControls()


    @classmethod
    def ColourHex(cls, colour):
        """Returns colour hex string for string or [r, g, b] or wx.SYS_COLOUR_XYZ."""
        return cls.GetColour(colour).GetAsString(wx.C2S_HTML_SYNTAX)


    @classmethod
    def GetColour(cls, colour):
        """Returns wx.Colour, from string or [r, g, b] or wx.SYS_COLOUR_XYZ."""
        if isinstance(colour, wx.Colour): return colour
        return wx.Colour(colour)  if isinstance(colour, text_types)    else \
               wx.Colour(*colour) if isinstance(colour, (list, tuple)) else \
               wx.SystemSettings.GetColour(colour)


    @classmethod
    def UpdateControls(cls):
        """Updates all managed controls."""
        for ctrl, props in cls.ctrls.items():
            if not ctrl: # Component destroyed
                cls.ctrls.pop(ctrl)
                continue # for ctrl, props

            for prop, colour in props.items():
                cls.UpdateControlColour(ctrl, prop, colour)


    @classmethod
    def UpdateControlColour(cls, ctrl, prop, colour):
        """Sets control property or invokes "Set" + prop."""
        mycolour = cls.GetColour(colour)
        if hasattr(ctrl, prop): setattr(ctrl, prop, mycolour)
        elif hasattr(ctrl, "Set" + prop): getattr(ctrl, "Set" + prop)(mycolour)



class BitmapComboBox(wx.adv.OwnerDrawnComboBox):
    """Dropdown combobox for showing bitmaps identified by name."""

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, bitmapsize=wx.DefaultSize,
                 choices=(), selected=None,
                 imagehandler=wx.lib.agw.thumbnailctrl.PILImageHandler,
                 style=0, name=""):
        """
        @param   choices   [name, ]
        @param   selected  index of selected choice, if any
        """
        super(BitmapComboBox, self).__init__(parent, id=id, pos=pos,
              size=size, choices=choices, style=style | wx.CB_READONLY, name=name)

        self._imagehandler = imagehandler()
        self._items = list(choices)
        self._bitmapsize = wx.Size(*bitmapsize)
        thumbsz, bordersz = self.GetButtonSize(), self.GetWindowBorderSize()
        self.MinSize = [sum(x) for x in zip(bitmapsize, bordersz, (thumbsz[0] + 3, 0))]
        if choices: self.SetSelection(0 if selected is None else selected)


    def OnDrawItem(self, dc, rect, item, flags):
        """OwnerDrawnComboBox override, draws item bitmapfrom handler."""
        if not (0 <= item < len(self._items)):
            return # Painting the control, but no valid item selected yet

        value = self._items[item]
        img, _, _ = self._imagehandler.LoadThumbnail(value, self._bitmapsize)
        if img: dc.DrawBitmap(img.ConvertToBitmap(), rect.x + 1, rect.y + 1)


    def GetItemCount(self):
        """Returns the number of items."""
        return len(self._items)


    def GetItemValue(self, index):
        """Returns item value at index."""
        return self._items[index]


    def FindItem(self, value):
        """Returns item index for the specified value, or wx.NOT_FOUND."""
        return next((i for i, x in enumerate(self._items) if x == value), wx.NOT_FOUND)


    def Insert(self, item, pos):
        """Inserts an item at position."""
        pos = min(pos, len(self._items)) % (len(self._items) or 1)
        self._items.insert(pos, item)
        super(BitmapComboBox, self).Insert(str(item), pos)


    def Delete(self, n):
        """Deletes the item with specified index."""
        if not (0 <= n < len(self._items)): return
        super(BitmapComboBox, self).Delete(n)
        del self._items[n]
        self.SetSelection(min(n, len(self._items) - 1))


    def ReplaceItem(self, n, value):
        """Replaces item value at specified index."""
        if not (0 <= n < len(self._items)): return
        self._items[n] = value
        self.Refresh()


    def SetItems(self, items):
        """Replaces all items in control."""
        self._items = list(items)
        return super(BitmapComboBox, self).SetItems(items)


    def OnDrawBackground(self, dc, rect, item, flags):
        """OwnerDrawnComboBox override."""
        bgCol = self.BackgroundColour
        if flags & wx.adv.ODCB_PAINTING_SELECTED \
        and not (flags & wx.adv.ODCB_PAINTING_CONTROL):
            bgCol = wx.Colour(0, 127, 255)
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(bgCol))
        w, h = self._bitmapsize
        dc.DrawRectangle(rect.x, rect.y, w + 2, h + 2)


    def OnMeasureItem(self, item):
        """OwnerDrawnComboBox override, returns item height."""
        return self._bitmapsize[1] + 2 # 1px padding on both sides


    def OnMeasureItemWidth(self, item):
        """OwnerDrawnComboBox override, returns item width."""
        return self._bitmapsize[0] + 2 # 1px padding on both sides



class BitmapListCtrl(wx.lib.agw.thumbnailctrl.ThumbnailCtrl):
    """A ThumbnailCtrl that shows bitmaps, without requiring images on disk."""

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition, size=wx.DefaultSize,
                 imagehandler=wx.lib.agw.thumbnailctrl.PILImageHandler):
        super(BitmapListCtrl, self).__init__(parent, id, pos, size,
            wx.lib.agw.thumbnailctrl.THUMB_OUTLINE_FULL,
            wx.lib.agw.thumbnailctrl.THUMB_FILTER_IMAGES, imagehandler
        )

        self._get_info = None
        self._imagehandler = imagehandler
        # Hack to get around ThumbnailCtrl's internal monkey-patching
        setattr(self._scrolled, "GetThumbInfo", self._GetThumbInfo)

        self.EnableDragging(False)
        self.EnableToolTips(True)
        self.SetDropShadow(False)
        self.ShowFileNames(True)

        self._scrolled.Bind(wx.EVT_CHAR_HOOK, self._OnChar)
        self._scrolled.Bind(wx.EVT_MOUSEWHEEL, None) # Disable zoom
        self._scrolled.Bind(thumbnailevents.EVT_THUMBNAILS_SEL_CHANGED, self._OnSelectionChanged)
        self._scrolled.Bind(thumbnailevents.EVT_THUMBNAILS_DCLICK,      self._OnDoubleClick)
        ColourManager.Manage(self._scrolled, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def GetItemValue(self, index):
        """Returns item value at specified index."""
        if not (0 <= index < self.GetItemCount()): return None
        thumb = self.GetItem(index)
        return thumb.GetFileName() if thumb else None


    def GetValue(self):
        """Returns value of the currently selected item, if any."""
        return self.GetItemValue(self.GetSelection())                
    def SetValue(self, value):
        """Sets selection to the specified value if present."""
        idx = self.FindItem(value)
        if idx >= 0: self.SetSelection(idx)
    Value = property(GetValue, SetValue)


    def FindItem(self, value):
        """Returns item index for the specified value, or wx.NOT_FOUND."""
        return next((i for i in range(self.GetItemCount())
                     if self.GetItem(i).GetFileName() == value), wx.NOT_FOUND)


    def SetItems(self, items):
        """Populates the control with string items."""
        def make_args(item):
            """Returns keyword arguments for wx.lib.agw.thumbnailctrl.Thumb()."""
            kwargs = dict(folder="", filename=item, caption=item)
            if sys.version_info >= (3, ):
                kwargs.update(imagehandler=self._imagehandler)
            else:
                kwargs.update(parent=self)
            return kwargs
        args = ([wx.lib.agw.thumbnailctrl.Thumb(**make_args(x)) for x in items], )
        if sys.version_info < (3, ): args += ("", )  # caption=""
        self.ShowThumbs(*args)


    def SetToolTipFunction(self, get_info):
        """Registers callback(name) for image tooltips."""
        self._get_info = get_info


    def _GetThumbInfo(self, index):
        """Returns the thumbnail information for the specified index."""
        thumb = self.GetItem(index)
        return self._get_info(thumb.GetFileName()) if thumb and self._get_info else None


    def _OnChar(self, event):
        """Handler for keypress, allows navigation, activation and deletion."""
        if not self.GetItemCount():
            event.Skip()
            return

        selection = self.GetSelection()
        if event.KeyCode in KEYS.ENTER:
            if selection >= 0: self._OnDoubleClick()
        elif event.KeyCode in KEYS.DELETE:
            evt = wx.CommandEvent(wx.wxEVT_LIST_DELETE_ITEM, self.Id)
            evt.SetEventObject(self)
            wx.PostEvent(self, evt)
        elif event.KeyCode in KEYS.ARROW + KEYS.PAGING + KEYS.HOME + KEYS.END \
        and not event.AltDown() and not event.ShiftDown():
            bmpw, bmph, margin = self.GetThumbSize()
            _, texth = self.GetTextExtent("X")
            per_line = self.Size[0] / (bmpw + margin + 2)
            per_page = per_line * (self.Size[1] / (bmph + texth + margin + 2))
            line_last, line_pos = self.GetItemCount() / per_line, selection % per_line
            sel_max = self.GetItemCount() - 1

            selection, sel2 = max(0, selection), None
            if event.KeyCode in KEYS.LEFT:
                if event.ControlDown(): sel2 = selection - line_pos
                else: sel2 = selection - 1
            elif event.KeyCode in KEYS.RIGHT:
                if event.ControlDown(): sel2 = selection + (per_line - line_pos - 1)
                else: sel2 = selection + 1
            elif event.KeyCode in KEYS.UP:
                if event.ControlDown(): sel2 = line_pos
                else: sel2 = selection - per_line
            elif event.KeyCode in KEYS.DOWN:
                if event.ControlDown():
                    sel2 = min(line_last * per_line + line_pos, sel_max)
                    if sel2 % per_line != line_pos:
                        sel2 = (line_last - 1) * per_line + line_pos
                        if sel2 == selection: sel2 = sel_max
                else: sel2 = selection + per_line
            elif event.KeyCode in KEYS.PAGEUP:
                if event.ControlDown(): event.Skip() # Propagate to parent
                else: sel2 = max(line_pos, selection - per_page)
            elif event.KeyCode in KEYS.PAGEDOWN:
                if event.ControlDown(): event.Skip() # Propagate to parent
                else: sel2 = min(selection + per_page, sel_max)
            elif event.KeyCode in KEYS.HOME:
                if event.ControlDown(): sel2 = 0
                else: sel2 = selection - line_pos
            elif event.KeyCode in KEYS.END:
                if event.ControlDown(): sel2 = sel_max
                else: sel2 = selection + (per_line - line_pos - 1)
            else: event.Skip()
            if sel2 is not None:
                self.SetSelection(max(0, (min(sel2, sel_max))))
        else: event.Skip()


    def _OnSelectionChanged(self, event):
        """Handler for selecting item, ensures single select."""
        event.Skip()
        # Disable ThumbnailCtrl's multiple selection
        self._scrolled._selectedarray[:] = [self.GetSelection()]
        evt = thumbnailevents.ThumbnailEvent(thumbnailevents.wxEVT_THUMBNAILS_SEL_CHANGED, self.Id)
        evt.SetEventObject(self)
        evt.Selection = self.GetSelection()
        wx.PostEvent(self, evt)


    def _OnDoubleClick(self, event=None):
        """Handler for double-clicking item, fires EVT_THUMBNAILS_DCLICK."""
        if event: event.Skip()
        evt = thumbnailevents.ThumbnailEvent(thumbnailevents.wxEVT_THUMBNAILS_DCLICK, self.Id)
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)



class ClockSelector(wx.Panel):
    """
    A 24h clock face for selecting any number of time periods,
    with a quarter hour step by default.

    Clicking and dragging with left or right button selects or deselects,
    double-clicking toggles an hour.
    """

    COLOUR_ON        = wx.Colour(241, 184, 45, 140)
    COLOUR_OFF       = wx.Colour(235, 236, 255)
    COLOUR_TEXT      = wx.BLACK
    COLOUR_LINES     = wx.BLACK
    COLOUR_TIME      = wx.RED
    FONT_SIZE        = 8
    INTERVAL         = 30
    INTERVAL_TOOLTIP = 1
    RADIUS_CENTER    = 20
    ANGLE_START      = math.pi / 2 # 0-hour position, in radians from horizontal


    def __init__(self, parent, id=-1, pos=wx.DefaultPosition,
                 size=(400, 400), style=0, name=wx.PanelNameStr,
                 selections=(0, )*24*4, centericon=None):
        """
        @param   selections  the selections to use, as [0,1,] for each time
                             unit in 24 hours. Length of selections determines
                             the minimum selectable step. Defaults to a quarter
                             hour step.
        @param   centericon  wx.Bitmap for clock center icon
        """
        super(ClockSelector, self).__init__(parent, id, pos, size,
            style | wx.FULL_REPAINT_ON_RESIZE, name
        )

        self.BackgroundColour = self.COLOUR_OFF
        self.ForegroundColour = self.COLOUR_TEXT

        self.USE_GC        = True # Use GraphicsContext instead of DC
        self.buffer        = None # Bitmap buffer
        self.selections    = list(selections)
        self.centericon    = centericon
        self.sticky_value  = None # True|False|None if selecting|de-|nothing
        self.last_unit     = None # Last changed time unit
        self.penult_unit   = None # Last but one unit, to detect moving backwards
        self.dragback_unit = None # Unit on a section edge dragged backwards
        self.sectors       = None # [[(x, y), ], ] center-edge2-edge1-center
        self.hourlines     = None # [(x1, y1, x2, y2), ]
        self.hourtexts     = None # ["00", ]
        self.hourtext_pts  = None # [(x, y), ]
        self.notch_pts     = None # [(x1, y1, x2, y2), ]
        self.tooltip_timer = None # wx.CallLater for refreshing tooltip
        self.SetInitialSize(self.GetMinSize())
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        font = self.Font; font.SetPointSize(self.FONT_SIZE); self.Font = font

        self.Bind(wx.EVT_SIZE,  self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouse)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)
        self.TopLevelParent.Bind(wx.EVT_MOUSEWHEEL, self.OnTopParentMouseWheel)
        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        # Ensure timer tick is immediately after start of minute
        delta = self.INTERVAL - datetime.datetime.now().second % self.INTERVAL + 1
        wx.CallLater(1000 * delta, self.timer.Start, 1000 * self.INTERVAL)
        self.timer.Start(milliseconds=1000 * self.INTERVAL)


    def OnTimer(self, event):
        """Handler for timer, refreshes clock face."""
        if not self: return
        if self.USE_GC: self.InitBuffer()
        self.Refresh()


    def OnSysColourChange(self, event):
        """Handler for system colour change, repaints control."""
        event.Skip()
        if self.USE_GC: self.InitBuffer()
        self.Refresh()


    def OnToolTip(self):
        """Populates control tooltip with current selections."""
        if not self: return
        self.tooltip_timer = None
        sections, start, i = [], None, 0 # sections=[(start, len), ]
        for i, on in enumerate(self.selections):
            if on and start is None: start = i # section start
            elif not on and start is not None: # section end
                sections.append((start, i - start))
                start = None
        if start is not None: # section reached the end
            sections.append((start, i - start + 1))

        f = lambda x: "%02d:%02d" % (x / 4, 15 * (x % 4))
        tip = ", ".join("%s - %s" % (f(i), f(i + n)) for i, n in sections)
        if not self.ToolTip or tip != self.ToolTip.Tip: self.ToolTip = tip


    def OnSize(self, event):
        """Size event handler, forces control back to rectangular size."""
        event.Skip()
        min_size = self.MinSize
        self.Size = max(min_size[0], min(self.Size)), max(min_size[1], min(self.Size))

        self.sectors      = []
        self.hourlines    = []
        self.hourtexts    = []
        self.hourtext_pts = []
        self.notch_pts    = []

        def polar_to_canvas(angle, radius, x=None, y=None):
            """
            Convert polar coordinates to canvas coordinates (in polar, zero
            point starts from the center - ordinary Cartesian system.
            On canvas, zero starts from top left and grows down and right.)

            @param   angle   polar angle where the x or y coordinates are at
            @param   radius  polar radius of the (x, y)
            @return          (x, y) or (x) or (y), depending on input arguments
            """
            xval, yval = None, None
            angle = (angle + 2 * math.pi) % (2 * math.pi)
            xval = None if x is None else x + radius
            yval = None if y is None else radius - y
            return yval if xval is None else (xval, yval) if yval else xval


        """
        All polar angles need reversed sign to map to graphics context.
        All (x,y) from polar coordinates need (-radius, +radius).
        -------------------
        |                 |
        |               --|
        |            --   |
        |        o -------|
        |                 |
        |                 |
        |                 |
        -------------------
        """

        LENGTH            = len(self.selections)
        RADIUS            = self.Size[0] / 2
        RADIUS_LINESTART  = RADIUS / 2
        PT_CENTER         = RADIUS, RADIUS
        HOUR_RADIUS_RATIO = 6 / 8.

        textwidth, textheight = self.GetTextExtent("02")
        for i, text in enumerate(["%02d" % h for h in range(24)]):  # Assemble hour text positions
            angle = self.ANGLE_START - i * 2 * math.pi / 24. - (2 * math.pi / 48.)
            x_polar, y_polar = (HOUR_RADIUS_RATIO * RADIUS * f(angle) for f in (math.cos, math.sin))
            x, y = polar_to_canvas(angle, RADIUS, x=x_polar, y=y_polar)
            x, y = x - textwidth / 2, y - textheight / 2
            self.hourtext_pts.append((x, y))
            self.hourtexts.append(text)

        last_line = None
        for i in range(LENGTH):  # Assemble hour/quarter line positions and sector polygons
            angle = math.pi + (2 * math.pi) / LENGTH * (i) + self.ANGLE_START
            # alpha: angle within one quadrant of a 24h clock
            alpha = angle % (math.pi / 2)  # Force into 90deg
            alpha = alpha if alpha < math.pi / 4 else math.pi / 2 - alpha  # Force into 45deg
            radius_ray = (RADIUS - 1) / math.cos(alpha) if alpha else RADIUS  # Lengthen radius to reach edge
            radius_start = RADIUS_LINESTART
            if alpha == math.pi / 4: radius_ray -= 8  # End corner lines earlier for rounded corners
            if not i % 12: radius_start *= 0.8        # Start quadrant first sector lines closer to center

            # Assemble hour/quarter line positions
            x1, y1 = radius_start * (math.cos(angle)) + RADIUS, radius_start * (math.sin(angle)) + RADIUS
            x2, y2 = radius_ray   * (math.cos(angle)) + RADIUS, radius_ray   * (math.sin(angle)) + RADIUS
            if not i % 4:  # Is full hour
                self.hourlines.append((x1, y1, x2, y2))
            else:
                # Make half-hour notches longer than quarter-hour
                ptx1 = (radius_ray - (3 if i % 2 else 10)) * (math.cos(angle)) + RADIUS
                pty1 = (radius_ray - (3 if i % 2 else 10)) * (math.sin(angle)) + RADIUS
                self.notch_pts.append((ptx1, pty1, x2, y2))

            # Assemble sector polygon
            x1, y1 = PT_CENTER
            if alpha == math.pi / 4:  # Corner sector, restore previously subtracted
                radius_ray += 8
                x2, y2 = radius_ray * (math.cos(angle)) + RADIUS, radius_ray * (math.sin(angle)) + RADIUS
            if last_line:
                self.sectors.append([(x1, y1), (x2, y2), last_line[1], last_line[0], ])
            last_line = ((x1, y1), (x2, y2))
        self.sectors.append([last_line[0], last_line[1],  # Connect overflow
                             self.sectors[0][2], self.sectors[0][3]])

        if self.USE_GC: self.InitBuffer()


    def SetSelections(self, selections):
        """Sets the currently selected time periods, as a list of 0/1."""
        refresh = (self.selections != selections)
        self.selections = selections[:]
        if refresh: self.InitBuffer(); self.Refresh()


    def GetSelections(self):
        """Returns the currently selected schedule as a list of 0/1."""
        return self.selections[:]


    def GetMinSize(self):
        """Returns the minimum needed size for the control."""
        return (100, 100)


    def OnPaint(self, event):
        """Handler for paint event, uses double buffering to reduce flicker."""
        if self.USE_GC: wx.BufferedPaintDC(self, self.buffer)
        else: self.DrawDC(wx.BufferedPaintDC(self))


    def OnEraseBackground(self, event):
        """Handles the wx.EVT_ERASE_BACKGROUND event."""
        pass # Intentionally empty to reduce flicker.


    def InitBuffer(self):
        """Initializes and paints cached content buffer."""
        sz = self.GetClientSize()
        sz.width = max(1, sz.width)
        sz.height = max(1, sz.height)
        self.buffer = wx.Bitmap(sz.width, sz.height, 32)

        dc = wx.MemoryDC(self.buffer)
        dc.SetBackground(wx.Brush(self.Parent.BackgroundColour))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        self.Draw(gc)


    def Draw(self, gc):
        """Draws the custom selector control using a GraphicsContext."""
        width, height = self.Size
        if not width or not height:
            return

        radius = width / 2

        # Draw clock background
        gc.SetPen(wx.Pen(self.COLOUR_LINES, style=wx.TRANSPARENT))
        gc.SetBrush(wx.Brush(self.BackgroundColour, wx.SOLID))
        gc.DrawRoundedRectangle(0, 0, width - 1, height - 1, 18)

        # Draw and fill all selected sectors
        gc.SetPen(wx.Pen(self.COLOUR_ON, style=wx.TRANSPARENT))
        gc.SetBrush(wx.Brush(self.COLOUR_ON, wx.SOLID))
        for sect in (x for i, x in enumerate(self.sectors) if self.selections[i]):
            gc.DrawLines(sect)

        # Draw hour lines and smaller notches
        gc.SetPen(wx.Pen(self.COLOUR_LINES, width=1))
        for x1, y1, x2, y2 in self.hourlines:
            gc.StrokeLines([(x1, y1), (x2, y2)])
        for x1, y1, x2, y2 in self.notch_pts:
            gc.StrokeLines([(x1, y1), (x2, y2)])

        # Draw hour texts
        gc.SetFont(gc.CreateFont(self.Font))
        textwidth, _ = self.GetTextExtent("02")
        for i, text in enumerate(self.hourtexts):
            if width / 6 < 2.8 * textwidth and i % 2: continue # for i, text
            gc.DrawText(text, *self.hourtext_pts[i])

        # Draw current time ray
        tm = datetime.datetime.now().time()
        hours = tm.hour + tm.minute / 60.
        angle = (2 * math.pi / 24) * (hours) - self.ANGLE_START
        alpha = angle % (math.pi / 2) # Force into 90deg
        alpha = alpha if alpha < math.pi / 4 else math.pi / 2 - alpha
        if alpha:
            radius_ray = (radius - 1) / math.cos(alpha)
        else:
            radius_ray = radius
        if alpha == math.pi / 4:
            radius_ray -= 8
        x1, y1 = radius, radius
        x2, y2 = radius_ray * (math.cos(angle)) + radius, radius_ray * (math.sin(angle)) + radius
        gc.SetPen(wx.Pen(self.COLOUR_TIME, style=wx.SOLID))
        gc.SetBrush(wx.Brush(self.COLOUR_TIME, wx.SOLID))
        gc.StrokeLines([(x1, y1), (x2, y2)])

        # Draw center icon
        if self.centericon:
            stepx, stepy = (x / 2 for x in self.centericon.Size)
            gc.DrawBitmap(self.centericon, radius - stepx, radius - stepy, *self.centericon.Size)

        # Refill rounded corners with background colour
        gc.SetPen(wx.Pen(self.Parent.BackgroundColour, style=wx.SOLID))
        gc.SetBrush(wx.Brush(self.Parent.BackgroundColour, wx.SOLID))
        CORNER_LINES = 18 - 7
        for i in range(4):
            x, y = 0 if i in [2, 3] else width - 1, 0 if i in [0, 3] else width - 1
            for j in range(CORNER_LINES, -1, -1):
                x1, y1 = x + (j if i in [2, 3] else -j), y
                x2, y2 = x1, y1 + (CORNER_LINES - j) * (1 if i in [0, 3] else -1)
                gc.StrokeLines([(x1, y1), (x2, y2)])

        # Draw rounded outer rectangle
        gc.SetPen(wx.Pen(self.COLOUR_LINES))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRoundedRectangle(0, 0, width - 1, height - 1, 18)


    def DrawDC(self, dc):
        """Draws the custom selector control using a DC."""
        width, height = self.Size
        if not width or not height: return

        dc.Background = wx.Brush(self.BackgroundColour)
        dc.Clear()

        # Draw highlighted sectors
        dc.Pen = wx.TRANSPARENT_PEN
        dc.Brush = wx.Brush(self.COLOUR_ON, wx.SOLID)
        for sect in (x for i, x in enumerate(self.sectors) if self.selections[i]):
            dc.DrawPolygon(sect)

        # Draw outer border
        dc.Pen = wx.Pen(self.COLOUR_LINES)
        dc.Brush = wx.TRANSPARENT_BRUSH
        dc.DrawRectangle(0, 0, width, height)

        # Draw hour lines and hour texts
        dc.Pen = wx.Pen(self.COLOUR_LINES, width=1)
        dc.DrawLineList(self.hourlines)
        dc.TextForeground = self.COLOUR_TEXT
        dc.Font = self.Font
        dc.DrawTextList(self.hourtexts, self.hourtext_pts)

        # Draw center icon
        if self.centericon:
            stepx, stepy = (x / 2 for x in self.centericon.Size)
            radius = width / 2
            dc.DrawBitmap(self.centericon, radius - stepx, radius - stepy)


    def OnTopParentMouseWheel(self, event):
        """
        Handler for mouse wheel in control top-level parent,
        forwards event to this control if cursor inside control.
        Workaround for win32 not sending wheel events to control unless
        it's focused.
        """
        abspos = self.TopLevelParent.ClientToScreen(event.Position)
        relpos = self.ScreenToClient(abspos)
        if self.HitTest(relpos) == wx.HT_WINDOW_INSIDE:
            event.Position = relpos
            self.ProcessEvent(event)


    def OnMouse(self, event):
        """Handler for any and all mouse actions in the control."""
        if not self.Enabled or not self.sectors: return


        def point_in_polygon(point, polypoints):
            """Returns whether point is inside a polygon."""
            result = False 
            if len(polypoints) < 3 or len(point) < 2: return result

            polygon = [list(map(float, p)) for p in polypoints]
            (x, y), (x2, y2) = list(map(float, point)), polygon[-1]
            for x1, y1 in polygon:
                if (y1 <= y and y < y2 or y2 <= y and y < y1) \
                and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    result = not result
                x2, y2 = x1, y1
            return result

        center = [self.Size.width / 2] * 2
        unit, x, y = None, event.Position.x, event.Position.y
        dist_center = ((center[0] - x) ** 2 + (center[1] - y) ** 2) ** 0.5
        if dist_center < self.RADIUS_CENTER:
            self.penult_unit = self.last_unit = None
        else:
            for i, sector in enumerate(self.sectors):
                if point_in_polygon((x, y), sector):
                    unit = i
                    break # for i, sector

        refresh, do_tooltip = False, False
        if event.LeftDown() or event.RightDown():
            self.CaptureMouse()
            if unit is not None and 0 <= unit < len(self.selections):
                self.penult_unit = None
                self.last_unit, self.sticky_value = unit, int(event.LeftDown())
                self.dragback_unit = None
                if bool(self.selections[unit]) != event.LeftDown():
                    self.selections[unit] = self.sticky_value
                    refresh = True
        elif event.LeftDClick() or event.RightDClick():
            if unit is not None:
                # Toggle an entire hour on double-click
                steps = len(self.selections) // 24
                low, hi = unit - unit % steps, unit - unit % steps + steps
                units = self.selections[low:hi]
                 # Toggle hour off on left-dclick only if all set
                value = 0 if event.RightDClick() else int(not all(units))
                self.selections[low:hi] = [value] * len(units)
                refresh = (units != self.selections[low:hi])
            elif event.LeftDClick():
                wx.PostEvent(self.TopLevelParent, ClockCenterEvent())
        elif event.LeftUp() or event.RightUp():
            if self.HasCapture(): self.ReleaseMouse()
            self.last_unit,   self.sticky_value  = None, None
            self.penult_unit, self.dragback_unit = None, None
        elif event.Dragging():
            if self.sticky_value is not None and unit != self.last_unit \
            and unit is not None and 0 <= unit < len(self.selections):
                LENGTH = len(self.selections)
                STARTS = range(2)
                ENDS = range(LENGTH - 2, LENGTH)
                def is_overflow(a, b):
                    return (a in STARTS and b in ENDS) or (a in ENDS and b in STARTS)
                def get_direction(a, b):
                    result = 1 if None in (a, b) or b > a else -1
                    result *= -1 if is_overflow(a, b) else 1
                    return result

                direction = get_direction(self.last_unit, unit)
                if is_overflow(self.last_unit, unit):
                    last = unit + 1 if self.last_unit is None else self.last_unit
                    low = min(unit, last)
                    hi  = max(unit, last)
                    units = self.selections[:low+1] + self.selections[hi:]
                    self.selections[:low+1] = [self.sticky_value] * (low + 1)
                    self.selections[hi:] = [self.sticky_value] * (LENGTH - hi)
                    refresh = (units != (self.selections[:low] + self.selections[hi:]))
                else:
                    last = unit if self.last_unit is None else self.last_unit
                    low = min(unit, last)
                    hi  = max(unit, last) + 1
                    units = self.selections[low:hi]
                    self.selections[low:hi] = [self.sticky_value] * len(units)
                    refresh = (units != self.selections[low:hi])

                # Check if we should drag the enabled edge backwards
                if (event.LeftIsDown() and self.penult_unit is not None):
                    last_direction = get_direction(self.penult_unit, self.last_unit)
                    # Did cursor just reverse direction
                    is_turnabout = (direction != last_direction)
                    # Value to the other side of current moving direction
                    prev_val = self.selections[(unit - direction) % LENGTH]
                    # The unit right on the other side of the last unit
                    edge_unit = (self.last_unit - direction) % LENGTH
                    # Next unit in the current moving direction
                    next_unit = (unit + direction) % LENGTH
                    # Value of the edge unit
                    edge_val = self.selections[edge_unit]
                    # Value of the next unit, or None if beyond start/end
                    next_val = self.selections[next_unit]
                    # Drag back if we are already doing so, or if we just
                    # turned around and the edge unit is off; but only if
                    # we didn't just turn around during dragging into a
                    # selected area, or if we are moving away from an edge
                    # into unselected area.
                    do_dragback = ((self.dragback_unit is not None or
                                    is_turnabout and edge_val != self.selections[unit])
                                   and not (self.dragback_unit is not None
                                            and is_turnabout and prev_val)
                                   and next_val)

                    if do_dragback:
                        # Deselect from last to almost current 
                        low = min((unit - direction) % LENGTH, self.last_unit)
                        hi  = max((unit - direction) % LENGTH, self.last_unit) + 1
                        self.dragback_unit = self.last_unit
                        self.selections[low:hi] = [0] * abs(hi - low)
                        refresh = True
                    else:
                        self.dragback_unit = None

                self.penult_unit = self.last_unit
                self.last_unit = unit
        elif event.Leaving():
            if not self.HasCapture():
                self.last_unit, self.sticky_value = None, None
                self.penult_unit, self.dragback_unit = None, None
        elif event.Moving() or event.Entering():
            do_tooltip = True
        elif event.WheelRotation:
            if unit is not None and 0 <= unit < len(self.selections):
                grow = (event.WheelRotation > 0) ^ event.IsWheelInverted()
                nextunit, ptr, i = unit, unit, 0
                while self.selections[ptr]:
                    nextunit, ptr = ptr, (ptr + 1) % len(self.selections)
                    i += 1
                    if i > len(self.selections): break # while
                if grow and self.selections[nextunit]:
                    nextunit = (nextunit + 1) % len(self.selections)
                if self.selections[nextunit] ^ grow:
                    refresh, self.selections[nextunit] = True, grow

        if refresh:
            do_tooltip = True
            self.InitBuffer()
            self.Refresh()
            wx.PostEvent(self.TopLevelParent, ClockSelectorEvent())
        if do_tooltip:
            if self.tooltip_timer: self.tooltip_timer.Stop()
            self.tooltip_timer = wx.CallLater(self.INTERVAL_TOOLTIP * 1000,
                                              self.OnToolTip)



try: text_types = (str, unicode)       # Py2
except Exception: text_types = (str, ) # Py3
