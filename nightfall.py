#-*- coding: utf-8 -*-
"""
A tray application that can make screen colors darker and softer during
nocturnal hours, can activate on schedule.

@author      Erki Suurjaak
@created     15.10.2012
@modified    31.10.2012
"""
import datetime
import os
import sys
import wx
import wx.combo
import wx.lib.newevent

import conf
import gamma

"""Event class and event binder for events in Dimmer."""
DimmerEvent, EVT_DIMMER = wx.lib.newevent.NewEvent()

"""Event class and event binder for change-events in TimeSelector."""
TimeSelectorEvent, EVT_TIME_SELECTOR = wx.lib.newevent.NewEvent()


class Dimmer(object):
    """Handles current screen dimming state and configuration."""
    def __init__(self, event_handler):
        conf.load()
        self.handler = event_handler
        self.current_factor = None # Currently applied dimming factor
        self.service = StartupService()
        self.check_conf()
        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(milliseconds=1000 * 30) # Fire timer every 30 seconds


    def check_conf(self):
        """Sanity-checks configuration loaded from file."""
        if not isinstance(conf.DimmingFactor, list) \
        or len(conf.DimmingFactor) != len(conf.DefaultDimmingFactor):
            conf.DimmingFactor = conf.DefaultDimmingFactor[:]
        for i, g in enumerate(conf.DimmingFactor):
            if not isinstance(g, (int, float)) \
            or not (conf.ValidGammaRange[0] <= g <= conf.ValidGammaRange[-1]):
                conf.DimmingFactor[i] = conf.DefaultDimmingFactor[i]
        if not isinstance(conf.Schedule, list) \
        or len(conf.Schedule) != len(conf.DefaultSchedule):
            conf.Schedule = conf.DefaultSchedule[:]
        for i, g in enumerate(conf.Schedule):
            if g not in [0, 1]:
                conf.Schedule[i] = conf.DefaultSchedule[i]
        conf.StartupEnabled = self.service.is_started()


    def start(self):
        """Starts handler: updates GUI settings, and dims if so configured."""
        self.post_event("FACTOR CHANGED",   conf.DimmingFactor)
        self.post_event("DIMMING TOGGLED",  conf.DimmingEnabled)
        self.post_event("SCHEDULE TOGGLED", conf.ScheduleEnabled)
        self.post_event("SCHEDULE CHANGED", conf.Schedule)
        self.post_event("STARTUP TOGGLED",  conf.StartupEnabled)
        self.post_event("STARTUP POSSIBLE", self.service.can_start())
        if self.should_dim():
            self.apply_factor(conf.DimmingFactor)
            msg = "SCHEDULE IN EFFECT" if self.should_schedule() \
                  else "DIMMING ON"
            self.post_event(msg, conf.DimmingFactor)
        else:
            self.apply_factor(conf.NormalDimmingFactor)

    def stop(self):
        """Stops any current dimming."""
        self.apply_factor(conf.NormalDimmingFactor)
        conf.save()


    def post_event(self, topic, data=None):
        """Sends a message event to the event handler."""
        event = DimmerEvent(Topic=topic, Data=data)
        wx.PostEvent(self.handler, event)


    def on_timer(self, event):
        """
        Handler for a timer event, checks whether to start/stop dimming on
        time-scheduled configuration.
        """
        if conf.ScheduleEnabled and not conf.DimmingEnabled:
            factor, msg = conf.NormalDimmingFactor, "DIMMING OFF"
            if self.should_schedule():
                factor, msg = conf.DimmingFactor, "SCHEDULE IN EFFECT"
            if factor != self.current_factor:
                self.apply_factor(factor)
                self.post_event(msg)


    def set_factor(self, factor):
        """
        Sets the current screen dimming factor, and applies it if enabled.

        @param   factor  a triple of gamma correction values for respective RGB
                 channels, 0..1
        """
        changed = (factor != conf.DimmingFactor)
        if changed:
            conf.DimmingFactor = factor[:]
            if self.should_dim():
                self.apply_factor(factor)
            conf.save()
        self.post_event("FACTOR CHANGED", conf.DimmingFactor)


    def toggle_schedule(self, enabled):
        """Toggles the scheduled dimming on/off."""
        changed = (enabled != conf.ScheduleEnabled)
        if changed:
            conf.ScheduleEnabled = enabled
            self.post_event("SCHEDULE TOGGLED", conf.ScheduleEnabled)
            conf.save()
            if self.should_dim():
                self.apply_factor(conf.DimmingFactor)
                msg = "SCHEDULE IN EFFECT" if self.should_schedule() \
                      else "DIMMING ON"
                self.post_event(msg, conf.DimmingFactor)
            else:
                self.apply_factor(conf.NormalDimmingFactor)
                self.post_event("DIMMING OFF", conf.NormalDimmingFactor)


    def toggle_startup(self, enabled):
        """Toggles running NightFall on system startup."""
        if self.service.can_start():
            conf.StartupEnabled = enabled
            self.service.start() if enabled else self.service.stop()
            conf.save()
            self.post_event("STARTUP TOGGLED", conf.StartupEnabled)


    def set_schedule(self, schedule):
        """
        Sets the current screen dimming schedule, and applies it if suitable.

        @param   selections  selected times, [1,0,..] per each hour
        """
        changed = (schedule != conf.Schedule)
        if changed:
            conf.Schedule = schedule[:]
            self.post_event("SCHEDULE CHANGED", conf.Schedule)
            conf.save()
            if self.should_dim():
                self.apply_factor(conf.DimmingFactor)
                msg = "SCHEDULE IN EFFECT" if self.should_schedule() \
                      else "DIMMING ON"
                self.post_event(msg, conf.DimmingFactor)
            else:
                self.apply_factor(conf.NormalDimmingFactor)
                self.post_event("DIMMING OFF", conf.NormalDimmingFactor)


    def should_dim(self):
        """
        Returns whether dimming should currently be applied, based on global
        enabled flag and enabled time selection.
        """
        return conf.DimmingEnabled or self.should_schedule()


    def should_schedule(self):
        """Whether dimming should currently be on, according to schedule."""
        result = False
        if conf.ScheduleEnabled:
            t = datetime.datetime.now().time()
            H_MUL = len(conf.Schedule) / 24
            M_DIV = 60 / H_MUL
            result = bool(conf.Schedule[t.hour * H_MUL + t.minute / M_DIV])
        return result


    def apply_factor(self, factor):
        """Applies the specified dimming factor."""
        try:
            gamma.setGamma(factor)
            self.current_factor = factor[:]
        except Exception, e:
            print e, factor


    def toggle_dimming(self, enabled):
        """Toggles the global dimmer flag enabled/disabled."""
        changed = (conf.DimmingEnabled != enabled)
        conf.DimmingEnabled = enabled
        msg = "DIMMING TOGGLED"
        if self.should_dim():
            factor = conf.DimmingFactor
            if self.should_schedule():
                msg = "SCHEDULE IN EFFECT"
        else:
            factor = conf.NormalDimmingFactor
        self.apply_factor(factor)
        if changed:
            conf.save()
        self.post_event(msg, conf.DimmingEnabled)



class NightFall(wx.App):
    """
    The NightFall application, manages the GUI elements and communication
    with the dimmer.
    """
    def OnInit(self):
        self.dimmer = Dimmer(self)

        frame = self.frame = self.create_frame()
        self.frame_hider = None # wx.CallLater object for timed hiding on blur
        frame.Bind(wx.EVT_CHECKBOX, self.on_toggle_schedule, frame.cb_schedule)
        frame.Bind(wx.EVT_COMBOBOX, self.on_stored_factor, frame.combo_factor)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_dimming, frame.cb_enabled)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_startup, frame.cb_startup)
        frame.Bind(wx.EVT_BUTTON,     self.on_toggle_settings, frame.button_ok)
        frame.Bind(wx.EVT_BUTTON,     self.on_exit, frame.button_exit)
        frame.Bind(EVT_TIME_SELECTOR, self.on_change_schedule)
        frame.Bind(wx.EVT_CLOSE,      self.on_toggle_settings)
        frame.Bind(wx.EVT_ACTIVATE,   self.on_deactivate_settings)
        for s in frame.sliders_gamma:
            frame.Bind(wx.EVT_SCROLL, self.on_change_dimming, s)
            frame.Bind(wx.EVT_SLIDER, self.on_change_dimming, s)
        self.Bind(EVT_DIMMER,         self.on_dimmer_event)

        self.TRAYICONS = {False: {}, True: {}}
        # Cache tray icons in dicts [dimming now][schedule enabled]
        for i, f in enumerate(conf.TrayIcons):
            dim, sch = False if i < 2 else True, True if i % 2 else False
            self.TRAYICONS[dim][sch] = wx.IconFromBitmap(wx.Bitmap(f))
        trayicon = self.trayicon = wx.TaskBarIcon()
        self.set_tray_icon(self.TRAYICONS[False][False])
        trayicon.Bind(wx.EVT_TASKBAR_LEFT_DOWN, self.on_toggle_settings)
        trayicon.Bind(wx.EVT_TASKBAR_RIGHT_DOWN, self.on_open_tray_menu)

        self.dimmer.start()
        frame.Show()
        return True


    def on_dimmer_event(self, event):
        """Handler for all events sent from Dimmer."""
        topic, data = event.Topic, event.Data
        if "FACTOR CHANGED" == topic:
            for i, g in enumerate(data):
                self.frame.sliders_gamma[i].SetValue(100 * g)
            rgb = [(255 * g) for g in data]
            tooltip = "#" + "".join(["%02X" % (255 * g) for g in data])
            self.frame.panel_color.SetBackgroundColour(wx.Colour(*rgb))
            self.frame.panel_color.SetToolTipString(tooltip)
            self.frame.panel_color.Refresh()
        elif "DIMMING TOGGLED" == topic:
            self.frame.cb_enabled.Value = data
            self.set_tray_icon(self.TRAYICONS[data][conf.ScheduleEnabled])
        elif "SCHEDULE TOGGLED" == topic:
            self.frame.cb_schedule.Value = data
            self.set_tray_icon(self.TRAYICONS[self.dimmer.should_dim()][data])
        elif "SCHEDULE CHANGED" == topic:
            self.frame.selector_time.SetSelections(data)
        elif "SCHEDULE IN EFFECT" == topic:
            self.set_tray_icon(self.TRAYICONS[True][True])
        elif "STARTUP TOGGLED" == topic:
            self.frame.cb_startup.Value = data
        elif "STARTUP POSSIBLE" == topic:
            self.frame.cb_startup.Show(data)
        elif "DIMMING ON" == topic:
            self.set_tray_icon(self.TRAYICONS[True][conf.ScheduleEnabled])
        elif "DIMMING OFF" == topic:
            self.set_tray_icon(self.TRAYICONS[False][conf.ScheduleEnabled])
        else:
            print "Unknown topic: ", topic


    def set_tray_icon(self, icon):
        """Sets the icon into tray and sets a configured tooltip."""
        self.trayicon.SetIcon(icon, conf.TrayTooltip)


    def on_stored_factor(self, event):
        """Applies the selected stored dimming factor."""
        factor = event.GetClientData()
        self.dimmer.set_factor(factor)


    def on_open_tray_menu(self, event):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()
        text = "Turn " + ("current dimming off" if self.dimmer.should_dim()
                          else "dimming on")
        item = menu.AppendCheckItem(id=-1, text=text)
        item.Check(self.dimmer.should_dim())
        menu.Bind(wx.EVT_MENU, self.on_toggle_dimming_tray, id=item.GetId())
        item = menu.AppendCheckItem(id=-1, text="Dim during scheduled hours")
        item.Check(conf.ScheduleEnabled)
        menu.Bind(wx.EVT_MENU, self.on_toggle_schedule, id=item.GetId())
        menu.AppendSeparator()
        item = wx.MenuItem(menu, -1, "Options")
        menu.Bind(wx.EVT_MENU, self.on_toggle_settings, id=item.GetId())
        menu.AppendItem(item)
        item = wx.MenuItem(menu, -1, "Exit NightFall")
        menu.Bind(wx.EVT_MENU, self.on_exit, id=item.GetId())
        menu.AppendItem(item)
        self.trayicon.PopupMenu(menu)


    def on_change_schedule(self, event):
        """Handler for changing the time schedule in settings window."""
        self.dimmer.set_schedule(self.frame.selector_time.GetSelections())


    def on_toggle_startup(self, event):
        """Handler for toggling the auto-load in settings window on/off."""
        self.dimmer.toggle_startup(self.frame.cb_startup.IsChecked())


    def on_deactivate_settings(self, event):
        """Handler for deactivating settings window, hides it if focus lost."""
        if not event.Active and not self.frame_hider:
            millis = conf.SettingsFrameTimeout
            if millis: # Hide if timeout positive
                self.frame_hider = wx.CallLater(millis, self.frame.Hide)
        elif event.Active: # kill the hiding timeout, if any
            if self.frame_hider:
                self.frame_hider.Stop()
                self.frame_hider = None


    def on_exit(self, event):
        """Handler for exiting the program, stops the dimmer and cleans up."""
        self.dimmer.stop()
        self.trayicon.RemoveIcon()
        self.trayicon.Destroy()
        self.frame.Destroy()
        self.Exit()


    def on_toggle_settings(self, event):
        """Handler for clicking to toggle settings window visible/hidden."""
        self.frame.Shown = not self.frame.Shown
        if self.frame.Shown:
            self.frame.Raise()


    def on_change_dimming(self, event):
        """Handler for a change in dimming factor properties."""
        factor = []
        for i, s in enumerate(self.frame.sliders_gamma):
            new = isinstance(event, wx.ScrollEvent) and s is event.EventObject
            value = event.GetPosition() if new else s.GetValue()
            factor.append(value / 100.0)
        self.dimmer.set_factor(factor)


    def on_toggle_dimming(self, event):
        """Handler for toggling dimming on/off."""
        self.dimmer.toggle_dimming(event.IsChecked())


    def on_toggle_dimming_tray(self, event):
        """
        Handler for toggling dimming on/off from the tray, can affect either
        schedule or global flag.
        """
        if not event.IsChecked() and self.dimmer.should_schedule():
            self.dimmer.toggle_schedule(False)
        self.dimmer.toggle_dimming(event.IsChecked())


    def on_toggle_schedule(self, event):
        """Handler for toggling schedule on/off."""
        self.dimmer.toggle_schedule(event.IsChecked())


    def create_frame(self):
        """Creates and returns the settings window."""
        frame = wx.Frame(parent=None, title=conf.Title,
            size=conf.SettingsFrameSize,
            style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX | wx.STAY_ON_TOP
        )

        panel = frame.panel = wx.Panel(frame)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        cb_enabled = frame.cb_enabled = wx.CheckBox(panel, label="Dim now")
        cb_enabled.SetValue(conf.DimmingEnabled)
        cb_enabled.ToolTipString = "Apply dimming settings now"
        sizer.Add(cb_enabled, border=5, flag=wx.ALL)

        # Create RGB sliders and color sample panel
        panel_colorpicker = frame.panel_colorpicker = wx.Panel(panel)
        panel_colorpicker.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(panel_colorpicker, border=5, flag=wx.GROW | wx.ALL)
        panel_sliders = frame.panel_sliders = wx.Panel(panel_colorpicker)
        panel_sliders.Sizer = wx.BoxSizer(wx.VERTICAL)
        sliders = frame.sliders_gamma = []
        colourtexts = ["red", "green", "blue"]
        for i in range(3):
            slider = wx.Slider(panel_sliders,
                minValue=conf.ValidGammaRange[0] * 100,
                maxValue=conf.ValidGammaRange[-1] * 100,
                value=conf.DimmingFactor[i] * 100,
                size=(-1, 20)
            )
            slider.ToolTipString = "Change %s colour channel" % colourtexts[i]
            sliders.append(slider)
            panel_sliders.Sizer.Add(slider, flag=wx.GROW)
        panel_colorpicker.Sizer.Add(panel_sliders, proportion=1, flag=wx.GROW)
        panel_colorshower = wx.Panel(panel_colorpicker)
        panel_colorshower.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_color = frame.panel_color = wx.Panel(panel_colorshower)
        panel_color.SetMinSize((60, 60))
        panel_color.SetBackgroundColour(
            wx.Colour(*[(255 * g) for g in conf.DimmingFactor])
        )
        combo_factor = frame.combo_factor = \
            wx.combo.BitmapComboBox(panel_colorshower, size=(60, 15))
        for i, factor in enumerate(conf.StoredFactors):
            bmp = wx.EmptyBitmap(170, 13)
            dc = wx.MemoryDC(bmp)
            dc.SetBackground(wx.Brush(wx.Colour(*[(255 * f) for f in factor])))
            dc.Clear()
            combo_factor.Append("", bmp, "name %s" % i)
            combo_factor.SetClientData(i, factor)
            if factor == conf.DimmingFactor:
                combo_factor.SetSelection(i)
        combo_factor.SetToolTipString("Choose a preset colour")
        panel_colorshower.Sizer.Add(panel_color, wx.GROW)
        panel_colorshower.Sizer.Add(combo_factor)
        panel_colorpicker.Sizer.Add(panel_colorshower)

        # Create time selector and scheduling checkboxes
        panel_time = frame.panel_time = wx.Panel(panel)
        panel_time.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(panel_time, border=5, flag=wx.GROW | wx.LEFT | wx.RIGHT)
        cb_schedule = frame.cb_schedule = wx.CheckBox(panel_time,
            label="Apply automatically during the highlighted hours:"
        )
        panel_time.Sizer.Add(cb_schedule, border=3, flag=wx.BOTTOM)
        selector_time = frame.selector_time = \
            TimeSelector(panel_time, selections=conf.Schedule)
        panel_time.Sizer.Add(selector_time, flag=wx.GROW)
        cb_startup = frame.cb_startup = wx.CheckBox(
            panel_time, label="Run %s at computer startup" % conf.Title
        )
        cb_startup.ToolTipString = "Adds NightFall to startup programs"
        panel_time.Sizer.Add(cb_startup, border=5, flag=wx.BOTTOM | wx.TOP)

        # Create buttons and infotext
        panel_buttons = frame.panel_buttons = wx.Panel(panel)
        panel_buttons.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(panel_buttons, border=5, flag=wx.GROW | wx.LEFT | wx.RIGHT)
        button_ok = frame.button_ok = wx.Button(panel_buttons,label="Minimize")
        button_exit = frame.button_exit = \
            wx.Button(panel_buttons, label="Exit program")
        button_ok.SetDefault()
        panel_buttons.Sizer.Add(button_ok)
        panel_buttons.Sizer.AddStretchSpacer()
        panel_buttons.Sizer.Add(button_exit, flag=wx.ALIGN_RIGHT)
        text = wx.StaticText(panel, label=conf.InfoText, style=wx.ALIGN_CENTER)
        text.ForegroundColour = wx.Colour(92, 92, 92)
        sizer.AddStretchSpacer()
        sizer.Add(text, border=3, flag=wx.ALL | wx.ALIGN_BOTTOM | wx.ALIGN_CENTER)

        # Position window in lower right corner
        frame.Layout()
        x1, y1, x2, y2 = wx.GetClientDisplayRect()
        frame.Position = (x2 - frame.Size.x, y2 - frame.Size.y)

        icons = wx.IconBundle()
        icons.AddIcon(wx.IconFromBitmap(wx.Bitmap((conf.SettingsFrameIcon))))
        frame.SetIcons(icons)

        frame.ToggleWindowStyle(wx.STAY_ON_TOP)
        return frame



class TimeSelector(wx.PyPanel):
    """
    A horizontal slider for selecting any number of periods from 24 hours,
    configured for an hour step.
    """
    def __init__(self, parent, id=-1, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=0, name=wx.PanelNameStr,
                 selections=[0]*24*4):
        """
        @param   selections  the selections to use, as [0,1,] for each time
                             unit in 24 hours. Length of selections determines
                             the minimum selectable step. Defaults to a quarter
                             hour step.
        """
        wx.PyPanel.__init__(self, parent, id, pos, size,
            style | wx.FULL_REPAINT_ON_RESIZE, name
        )
        self.selections = selections[:]

        self.sticky_value  = None # True|False|None if selecting|de-|nothing
        self.last_unit     = None # Last changed time unit
        self.penult_unit   = None # Last but one unit, to detect move backwards
        self.dragback_unit = None # Unit on a section edge dragged backwards
        self.SetInitialSize(self.GetMinSize())
        self.SetToolTipString("Click and drag with left or right button to "
            "select or deselect,\ndouble-click to toggle an hour")
        self.SetCursor(wx.StockCursor(wx.CURSOR_HAND))
        self.AcceptsFocus = self.AcceptsFocusFromKeyboard = lambda: False
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseEvent)


    def SetSelections(self, selections):
        """Sets the currently selected time periods, as a list of 0/1."""
        refresh = (self.selections != selections)
        self.selections = selections[:]
        if refresh:
            self.Refresh()


    def GetSelections(self):
        """Returns the currently selected schedule as a list of 0/1."""
        return self.selections[:]


    def GetMinSize(self):
        """Returns the minimum needed size for the control."""
        best = wx.Size(-1, -1)
        extent = self.GetFullTextExtent("24")#(width, height, descent, leading)
        best.height = (extent[1] + extent[2]) * 2 # label height * 2
        best.width  = len(self.selections) * (extent[0] + 4)
        return best


    def OnPaint(self, event):
        """Handler for paint event, uses double buffering to reduce flicker."""
        self.Draw(wx.BufferedPaintDC(self))


    def OnEraseBackground(self, event):
        """Handles the wx.EVT_ERASE_BACKGROUND event."""
        pass # Intentionally empty to reduce flicker.


    def Draw(self, dc):
        """Draws the custom selector control."""
        width, height = self.Size
        if not width or not height:
            return

        colour_off, colour_on = wx.Colour(0,0,0), wx.Colour(0,0,255)
        colour_text = wx.Colour(255,255,255)
        dc.SetBackground(wx.Brush(colour_off, wx.SOLID))
        dc.Clear()

        # Find enabled sections to simplify drawing
        sections, start = [], None # sections=[(start, len), ]
        for i, on in enumerate(self.selections):
            if on and start is None:           # section start
                start = i
            elif not on and start is not None: # section end
                sections.append((start, i - start))
                start = None
        if start is not None: # section reached the end
            sections.append((start, i - start + 1))
        units_per_pixel = len(self.selections) / float(width)
        dc.SetBrush(wx.Brush(colour_on, wx.SOLID))
        dc.SetPen(wx.Pen(colour_on))
        for start, length in sections:
            x, xwidth = start / units_per_pixel, length / units_per_pixel
            if start + length == len(self.selections):
                xwidth += 1 # Overstep to ensure selection fills the end
            dc.DrawRectangle(x, 0, xwidth, height)

        # Write hours and draw hour lines
        hour_y = [2, height - 16] # alternating Y coordinates of hour texts
        notch_y = [(0, 2), (height - 2, height)] # alternating notch Y1,Y2
        lead = (width / 24 - self.GetFullTextExtent("24")[0]) / 2 # center text
        texts, text_xys, notch_xys = [], [], []
        for i, t in enumerate(["%02d" % d for d in range(0, 24)]):
            texts.append(t)
            x = i * width / 24
            text_xys.append((x + lead, hour_y[i % 2]))
            if i: # skip first line for hour 0
                notch_xys.append((x, notch_y[i % 2][0], x, notch_y[i % 2][1]))
        dc.SetTextForeground(colour_text)
        dc.SetPen(wx.Pen(colour_text))
        dc.SetFont(self.Font)
        dc.DrawTextList(texts, text_xys)
        dc.DrawLineList(notch_xys)


    def OnMouseEvent(self, event):
        """Handler for any and all mouse actions in the control."""
        if not self.Enabled:
            return

        width, height = self.Size
        units_per_pixel = len(self.selections) / float(width)
        # Last unit can be wider if full width does not divide exactly
        unit = min(len(self.selections) - 1,
                   int(event.Position.x * units_per_pixel))
        refresh = False
        if event.LeftDown() or event.RightDown():
            self.CaptureMouse()
            if 0 <= unit < len(self.selections):
                self.penult_unit = None
                self.last_unit, self.sticky_value = unit, int(event.LeftDown())
                self.dragback_unit = None
                if bool(self.selections[unit]) != event.LeftDown():
                    self.selections[unit] = self.sticky_value
                    refresh = True
        elif event.LeftDClick():
            # Toggle an entire hour on double-click
            steps = len(self.selections) / 24
            low, hi = unit - unit % steps, unit - unit % steps + steps
            units = self.selections[low:hi]
            value = int(sum(units) != len(units)) # Toggle off only if all set
            self.selections[low:hi] = [value] * len(units)
            refresh = (units != self.selections[low:hi])
        elif event.LeftUp() or event.RightUp():
            if self.HasCapture():
                self.ReleaseMouse()
            self.last_unit, self.sticky_value = None, None
            self.penult_unit, self.dragback_unit = None, None
        elif event.Dragging():
            if self.sticky_value is not None and unit != self.last_unit \
            and 0 <= unit < len(self.selections):
                    low = min(unit, self.last_unit)
                    hi  = max(unit, self.last_unit) + 1
                    units = self.selections[low:hi]
                    self.selections[low:hi] = [self.sticky_value] * len(units)
                    refresh = (units != self.selections[low:hi])

                    # Check if we should drag the enabled edge backwards
                    if (event.LeftIsDown() and self.penult_unit is not None):
                        # Did cursor just reverse direction
                        is_turnabout = \
                            ((unit < self.last_unit > self.penult_unit)
                            or (unit > self.last_unit < self.penult_unit))
                        direction = 1 if (unit > self.last_unit) else -1
                        # Value to the other side of current moving direction
                        prev_val = self.selections[unit - direction] \
                            if 0 <= unit - direction < len(self.selections) \
                            else None
                        # The unit right on the other side of the last unit
                        edge_unit = self.last_unit - direction
                        # Next unit in the current moving direction
                        next_unit = unit + direction
                        # Value of the edge unit, or None if beyond start/end
                        edge_val = self.selections[edge_unit] if \
                            (0 <= edge_unit < len(self.selections)) else None
                        # Value of the next unit, or None if beyond start/end
                        next_val = self.selections[next_unit] if \
                            (0 <= next_unit < len(self.selections)) else None
                        # Drag back if we are already doing so, or if we just
                        # turned around and the edge unit is off; but only if
                        # we didn't just turn around during dragging into a
                        # selected area, or if we are moving away from an edge
                        # into unselected area.
                        do_dragback = \
                            ((self.dragback_unit is not None) or (is_turnabout
                             and edge_val != self.selections[unit])) \
                            and not (self.dragback_unit is not None
                                     and is_turnabout and prev_val) \
                            and (edge_val is not None or next_val)
                        if do_dragback:
                            # Deselect from last to almost current 
                            low = min(unit - direction, self.last_unit)
                            hi  = max(unit - direction, self.last_unit) + 1
                            self.dragback_unit = self.last_unit
                            self.selections[low:hi] = [0] * abs(hi - low)
                            refresh = True
                            if not next_val:
                                # Stop dragback if reaching a disabled area
                                self.dragback_unit = None
                        else:
                            self.dragback_unit = None

                    self.penult_unit = self.last_unit
                    self.last_unit = unit
        elif event.Leaving():
            if not self.HasCapture():
                self.last_unit, self.sticky_value = None, None
                self.penult_unit, self.dragback_unit = None, None
        if refresh:
            self.Refresh()
            event = TimeSelectorEvent()
            wx.PostEvent(self.TopLevelParent.EventHandler, event)



class StartupService(object):
    """
    Manages starting NightFall on system startup, if possible. Currently
    supports only Windows systems.
    """

    def can_start(self):
        """Whether startup can be set on this system at all."""
        return ("win32" == sys.platform)

    def is_started(self):
        """Whether NightFall has been started."""
        return os.path.exists(self.get_shortcut_path_windows())

    def start(self):
        """Sets NightFall to run at system startup."""
        shortcut_path = self.get_shortcut_path_windows()
        target_path = conf.ApplicationPath
        workdir, icon = conf.ApplicationDirectory, conf.ShortcutIconPath
        self.create_shortcut_windows(shortcut_path, target_path, workdir, icon)

    def stop(self):
        """Stops NightFall from running at system startup."""
        try:
            os.unlink(self.get_shortcut_path_windows())
        except Exception, e:
            pass

    def get_shortcut_path_windows(self):
        path = "~\\Start Menu\\Programs\\Startup\\%s.lnk" % conf.Title
        return os.path.expanduser(path)

    def create_shortcut_windows(self, path, target="", workdir="", icon=""):
        if "url" == path[-3:].lower():
            with open(path, "w") as shortcut:
                shortcut.write("[InternetShortcut]\nURL=%s" % target)
        else:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(path)
            if target.lower().endswith(("py", "pyw")):
                # pythonw leaves no DOS window open
                python = sys.executable.replace("python.exe", "pythonw.exe")
                shortcut.Targetpath = "\"%s\"" % python
                shortcut.Arguments = "\"%s\"" % target
            else:
                shortcut.Targetpath = target
            shortcut.WorkingDirectory = workdir
            if icon:
                shortcut.IconLocation = icon
            shortcut.save()



if __name__ == '__main__':
    app = NightFall()
    app.MainLoop()
