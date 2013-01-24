#-*- coding: utf-8 -*-
"""
A tray application that can make screen colors darker and softer during
nocturnal hours, can activate on schedule.

@author      Erki Suurjaak
@created     15.10.2012
@modified    24.01.2013
"""
import datetime
import math
import os
import sys
import wx
import wx.combo
import wx.lib.agw.aquabutton
import wx.lib.agw.flatnotebook
import wx.lib.agw.gradientbutton
import wx.lib.agw.thumbnailctrl
import wx.lib.agw.ultimatelistctrl
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
        self.current_factor = conf.NormalDimmingFactor # Current screen factor
        self.fade_timer = None # wx.Timer instance for applying fading
        self.fade_steps = None # Number of steps to take during a fade
        self.fade_delta = None # Delta to add to factor elements on fade step
        self.fade_target_factor = None # Final factor values during fade
        self.fade_current_factor = None # Factor float values during fade
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
        for i, g in enumerate(conf.DimmingFactor[1:]):
            if not isinstance(g, (int, float)) \
            or not (conf.ValidColourRange[0] <= g <= conf.ValidColourRange[-1]):
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
            self.apply_factor(conf.DimmingFactor, fade=True)
            msg = "SCHEDULE IN EFFECT" if self.should_schedule() \
                  else "DIMMING ON"
            self.post_event(msg, conf.DimmingFactor)
        else:
            self.apply_factor(conf.NormalDimmingFactor)


    def stop(self):
        """Stops any current dimming."""
        self.apply_factor(conf.NormalDimmingFactor)
        conf.save()


    def post_event(self, topic, data=None, info=None):
        """Sends a message event to the event handler."""
        event = DimmerEvent(Topic=topic, Data=data, Info=info)
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
                self.apply_factor(factor, fade=True)
                self.post_event(msg)


    def set_factor(self, factor, info=None):
        """
        Sets the current screen dimming factor, and applies it if enabled.

        @param   factor       a 4-byte list, for 3 RGB channels and brightness,
                              0..255
        @param   info         info given to callback event, if any
        """
        changed = (factor != self.current_factor)
        if changed:
            conf.DimmingFactor = factor[:]
            self.post_event("FACTOR CHANGED", conf.DimmingFactor, info)
            conf.save()
            if self.should_dim():
                self.apply_factor(factor, info)


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


    def apply_factor(self, factor, info=None, fade=False):
        """
        Applies the specified dimming factor.

        @param   info         info given to callback event, if any
        @param   fade         if True, changes factor from current to new in a
                              number of steps smoothly
        """
        if self.fade_timer:
            self.fade_timer.Stop()
            self.fade_delta = self.fade_steps = self.fade_timer = None
            self.fade_target_factor = None
        if fade or (info and "APPLY DETAILED" != info):
            self.fade_steps = conf.FadeSteps
            self.fade_target_factor = factor[:]
            self.fade_current_factor = map(float, self.current_factor)
            self.fade_delta = []
            for i, (new, now) in enumerate(zip(factor, self.current_factor)):
                self.fade_delta.append(float(new - now) / conf.FadeSteps)
            self.fade_timer = wx.CallLater(conf.FadeDelay, self.fade_step)
        elif gamma.set_screen_factor(factor):
            self.current_factor = factor[:]
            self.post_event("FACTOR SUCCEEDED", conf.DimmingFactor, info)
        else:
            self.post_event("FACTOR FAILED", conf.DimmingFactor, info)



    def fade_step(self):
        """
        Handler for a fade step, applies the fade delta to screen factor and
        schedules another event, if more steps left.
        """
        self.fade_timer = None
        if self.fade_steps:
            self.fade_current_factor = [(current + delta) for current, delta
                in zip(self.fade_current_factor, self.fade_delta)]
            if 1 == self.fade_steps:
                # Final step: use exact given target, to avoid rounding errors
                self.set_factor(self.fade_target_factor)
            self.set_factor(map(int, map(round, self.fade_current_factor)))
            self.fade_steps -= 1
            if self.fade_steps:
                self.fade_timer = wx.CallLater(conf.FadeDelay, self.fade_step)
            else:
                self.fade_delta = self.fade_steps = None
                self.fade_target_factor = None



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
        self.frame_shower = None # wx.CallLater object for timed showing on slideout
        self.frame_pos_orig = None # Position of frame before slidein
        frame.Bind(wx.EVT_CHECKBOX, self.on_toggle_schedule, frame.cb_schedule)
        frame.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_SEL_CHANGED, self.on_change_stored_factor, frame.list_factors._scrolled)
        frame.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_DCLICK, self.on_stored_factor, frame.list_factors._scrolled)

        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_dimming, frame.cb_enabled)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_startup, frame.cb_startup)
        frame.Bind(wx.EVT_BUTTON,     self.on_toggle_settings, frame.button_ok)
        frame.Bind(wx.EVT_BUTTON,     self.on_exit, frame.button_exit)
        frame.Bind(wx.EVT_BUTTON,     self.on_stored_factor, frame.button_saved_apply)
        frame.Bind(wx.EVT_BUTTON,     self.on_delete_factor, frame.button_saved_delete)
        frame.Bind(wx.EVT_BUTTON,     self.on_save_factor, frame.button_save)
        frame.Bind(EVT_TIME_SELECTOR, self.on_change_schedule)
        frame.Bind(wx.EVT_CLOSE,      self.on_toggle_settings)
        frame.Bind(wx.EVT_ACTIVATE,   self.on_deactivate_settings)
        for s in frame.sliders_factor:
            frame.Bind(wx.EVT_SCROLL, self.on_change_factor_detail, s)
            frame.Bind(wx.EVT_SLIDER, self.on_change_factor_detail, s)
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
        if conf.StartMinimizedParameter not in sys.argv:
            frame.Show()
        return True


    def on_dimmer_event(self, event):
        """Handler for all events sent from Dimmer."""
        topic, data, info = event.Topic, event.Data, event.Info
        if "FACTOR CHANGED" == topic:
            for i, g in enumerate(data):
                self.frame.sliders_factor[i].SetValue(g)
            if "APPLY DETAILED" == info and not self.dimmer.should_dim():
                # If dimming is off, success/failure events will not follow
                self.frame.bmp_detail.SetBitmap(get_factor_bitmap(data))
                self.frame.bmp_detail.SetToolTipString(get_factor_str(data))
        elif "FACTOR SUCCEEDED" == topic:
            pass
            bmp, tooltip = get_factor_bitmap(data), get_factor_str(data)
            self.frame.bmp_config.SetBitmap(bmp)
            self.frame.bmp_detail.SetBitmap(bmp)
            self.frame.bmp_config.SetToolTipString(tooltip)
            self.frame.bmp_detail.SetToolTipString(tooltip)
        elif "FACTOR FAILED" == topic:
            bmp = get_factor_bitmap(data, False)
            tooltip = get_factor_str(data, False)
            self.frame.bmp_config.SetBitmap(bmp)
            self.frame.bmp_detail.SetBitmap(bmp)
            self.frame.bmp_config.SetToolTipString(tooltip)
            self.frame.bmp_detail.SetToolTipString(tooltip)
            if "APPLY SAVED" == info:
                for i, factor in enumerate(conf.StoredFactors):
                    if factor == data:
                        thumb = self.frame.list_factors.GetItem(i)
                        thumb.SetBitmap(bmp)
                wx.MessageBox(
                    "This factor is not supported by graphics hardware.",
                    conf.Title, wx.OK | wx.ICON_WARNING)
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


    def on_change_stored_factor(self, event):
        selected = self.frame.list_factors.GetSelection()
        enabled = (selected >= 0)
        if enabled and not self.frame.button_saved_apply.Enabled:
            self.frame.button_saved_apply.Enabled = True
            self.frame.button_saved_delete.Enabled = True
        elif not enabled and self.frame.button_saved_apply.Enabled:
            self.frame.button_saved_apply.Enabled = False
            self.frame.button_saved_delete.Enabled = False
        event.Skip()


    def on_stored_factor(self, event):
        """Applies the selected stored dimming factor."""
        selected = self.frame.list_factors.GetSelection()
        if selected >= 0:
            factor = self.frame.list_factors.GetThumbFactor(selected)
            if not self.dimmer.should_dim():
                conf.DimmingEnabled = True
                self.frame.cb_enabled.Value = True
                self.set_tray_icon(self.TRAYICONS[True][conf.ScheduleEnabled])
            self.dimmer.set_factor(factor, "APPLY SAVED")


    def on_menu_stored_factor(self, event):
        """Handler to apply a stored factor from clicking in tray menu."""
        factor = self.trayiconmenu._item_factors[event.GetId()]
        if not self.dimmer.should_dim():
            conf.DimmingEnabled = True
            self.frame.cb_enabled.Value = True
            self.set_tray_icon(self.TRAYICONS[True][conf.ScheduleEnabled])
        self.dimmer.set_factor(factor, "APPLY SAVED")


    def on_save_factor(self, event):
        """Stores the currently set rgb-brightness values."""
        factor = conf.DimmingFactor
        if factor not in conf.StoredFactors:
            filename = str(bytearray(factor)).decode("latin1")
            thumb = wx.lib.agw.thumbnailctrl.Thumb(self, folder="",
                filename=filename, caption=filename)
            bmp = get_factor_bitmap(factor)
            lst = self.frame.list_factors
            lst.RegisterBitmap(filename, bmp, factor)
            thumbs = [lst.GetItem(i) for i in range(lst.GetItemCount())]
            thumbs.append(thumb)
            lst.ShowThumbs(thumbs, caption="")
            conf.StoredFactors.append(factor)
            conf.save()
            wx.MessageBox("Factor added to saved factors.",
                conf.Title, wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("Factor already in saved factors.",
                conf.Title, wx.OK | wx.ICON_WARNING)


    def on_delete_factor(self, event):
        """Deletes the stored factor, if confirmed."""
        selected = self.frame.list_factors.GetSelection()
        if selected >= 0:
            if wx.OK == wx.MessageBox(
                "Remove this factor from list?",
                conf.Title, wx.OK | wx.CANCEL | wx.ICON_QUESTION
            ):
                factor = self.frame.list_factors.GetThumbFactor(selected)
                if factor in conf.StoredFactors:
                    conf.StoredFactors.remove(factor)
                    conf.save()
                thumb_ctrl = self.frame.list_factors.GetItem(selected)
                self.frame.list_factors.UnregisterBitmap(thumb_ctrl.GetFileName())
                self.frame.list_factors.RemoveItemAt(selected)
                self.frame.list_factors.Refresh()


    def on_open_tray_menu(self, event):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()
        menu._item_factors = {} # {MenuItem.Id: factor, }
        is_dimming = self.dimmer.should_dim()
        text = "Turn " + ("current dimming off" if self.dimmer.should_dim()
                          else "dimming on")
        item = menu.AppendCheckItem(id=-1, text=text)
        item.Check(is_dimming)
        menu.Bind(wx.EVT_MENU, self.on_toggle_dimming_tray, id=item.GetId())
        item = menu.AppendCheckItem(id=-1, text="Dim during scheduled hours")
        item.Check(conf.ScheduleEnabled)
        menu.Bind(wx.EVT_MENU, self.on_toggle_schedule, id=item.GetId())
        menu.AppendSeparator()
        menu_factor = wx.Menu()
        for i in range(self.frame.list_factors.GetItemCount()):
            factor = self.frame.list_factors.GetThumbFactor(i)
            item = menu_factor.AppendCheckItem(id=-1,
                text=get_factor_str(factor, short=True))
            item.Check(is_dimming and factor == conf.DimmingFactor)
            menu.Bind(wx.EVT_MENU, self.on_menu_stored_factor, id=item.GetId())
            menu._item_factors[item.GetId()] = factor # For event handling
        menu.AppendMenu(id=-1, text="Apply saved factor", submenu=menu_factor)
        item = wx.MenuItem(menu, -1, "Options")
        menu.Bind(wx.EVT_MENU, self.on_toggle_settings, id=item.GetId())
        menu.AppendItem(item)
        item = wx.MenuItem(menu, -1, "Exit NightFall")
        menu.Bind(wx.EVT_MENU, self.on_exit, id=item.GetId())
        menu.AppendItem(item)
        self.trayiconmenu = menu
        self.trayicon.PopupMenu(menu)


    def on_change_schedule(self, event):
        """Handler for changing the time schedule in settings window."""
        self.dimmer.set_schedule(self.frame.selector_time.GetSelections())


    def on_toggle_startup(self, event):
        """Handler for toggling the auto-load in settings window on/off."""
        self.dimmer.toggle_startup(self.frame.cb_startup.IsChecked())


    def on_deactivate_settings(self, event):
        """Handler for deactivating settings window, hides it if focus lost."""
        if self.frame.Shown \
        and not (event.Active or self.frame_hider or self.frame_shower):
            millis = conf.SettingsFrameTimeout
            if millis: # Hide if timeout positive
                #self.frame_hider = wx.CallLater(millis, self.frame.Hide)
                self.frame_hider = wx.CallLater(millis, self.settings_slidein)
        elif event.Active: # kill the hiding timeout, if any
            if self.frame_hider:
                self.frame_hider.Stop()
                self.frame_hider = None
                if self.frame_pos_orig:
                    self.frame.Position = self.frame_pos_orig
                    self.frame_pos_orig = None


    def settings_slidein(self):
        """
        Slides the settings out of view into the screen edge, incrementally,
        using callbacks.
        """
        y = self.frame.Position.y
        display_h = wx.GetDisplaySize().height
        if y < display_h:
            if not self.frame_pos_orig:
                self.frame_pos_orig = self.frame.Position
            self.frame.Position = (self.frame.Position.x, y + conf.SettingsFrameSlideInStep)
            self.frame_hider = wx.CallLater(conf.SettingsFrameSlideDelay, self.settings_slidein)
        else:
            self.frame_hider = None
            self.frame.Hide()
            x1, y1, x2, y2 = wx.GetClientDisplayRect()
            self.frame.Position = self.frame_pos_orig if self.frame_pos_orig \
                else (x2 - self.frame.Size.x, y2 - self.frame.Size.y)
            self.frame_pos_orig = None


    def settings_slideout(self):
        """
        Slides the settings into view out from the screen, incrementally,
        using callbacks.
        """
        h = self.frame.Size.height
        display_h = wx.GetClientDisplayRect().height
        #print "settings_slideout, pos=%s, h=%s, display_h=%s" % (self.frame.Position, h, display_h)
        if not self.frame_pos_orig:
            self.frame_pos_orig = self.frame.Position.x, display_h - h
            self.frame.Position = self.frame_pos_orig[0], display_h
            #print "setting frame_pos_orig to %s and frame pos to %s" % (self.frame_pos_orig, self.frame.Position)
        y = self.frame.Position.y
        if not self.frame.Shown:
            self.frame.Show()
        if (y + h > display_h):
            #print "sliding out, as %s + %s > %s" % (y, h, display_h)
            #print "moving frame out to %s" % self.frame.Position
            self.frame.Position = (self.frame.Position.x, y - conf.SettingsFrameSlideOutStep)
            self.frame_shower = wx.CallLater(conf.SettingsFrameSlideDelay, self.settings_slideout)
        else:
            #print "disabling frame_shower, as we're there (%s)" % self.frame.Position
            self.frame_shower = None
            self.frame_pos_orig = None
            self.frame.Raise()


    def on_exit(self, event):
        """Handler for exiting the program, stops the dimmer and cleans up."""
        self.dimmer.stop()
        self.trayicon.RemoveIcon()
        self.trayicon.Destroy()
        self.frame.Destroy()
        self.Exit()


    def on_toggle_settings(self, event):
        """Handler for clicking to toggle settings window visible/hidden."""
        if self.frame_hider: # Window is sliding closed
            self.frame_hider.Stop()
            if self.frame_pos_orig:
                # Sliding was already happening: move back to original place
                self.frame.Position = self.frame_pos_orig
            else:
                # Window was shown: toggle window off
                self.frame.Hide()
            self.frame_hider = None
            self.frame_pos_orig = None
        elif self.frame_shower: # Window is sliding open
            self.frame_shower.Stop()
            self.frame_shower = None
            millis = conf.SettingsFrameTimeout
            if millis: # Hide if timeout positive
                if conf.SettingsFrameSlideInEnabled:
                    self.frame_hider = wx.CallLater(millis,
                                                    self.settings_slidein)
                else:
                    self.frame_hider = wx.CallLater(millis, self.frame.Hide)
            else:
                self.frame.Hide()
                self.frame.Position = self.frame_pos_orig
        else:
            if not self.frame.Shown:
                if conf.SettingsFrameSlideOutEnabled:
                    self.frame_shower = wx.CallLater(
                        conf.SettingsFrameSlideDelay, self.settings_slideout)
                else:
                    self.frame.Shown = True
            else:
                self.frame.Shown = not self.frame.Shown
        if self.frame.Shown:
            self.frame.Raise()



    def on_change_factor_detail(self, event):
        """Handler for a change in screen factor properties."""
        factor = []
        for i, s in enumerate(self.frame.sliders_factor):
            new = isinstance(event, wx.ScrollEvent) and s is event.EventObject
            value = event.GetPosition() if new else s.GetValue()
            factor.append(value)
        self.dimmer.set_factor(factor, "APPLY DETAILED")


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

        notebook = frame.notebook = wx.lib.agw.flatnotebook.FlatNotebook(panel)
        notebook.SetAGWWindowStyleFlag(
              wx.lib.agw.flatnotebook.FNB_FANCY_TABS
            | wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON
            | wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS
            | wx.lib.agw.flatnotebook.FNB_NODRAG
            | wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS)
        notebook.SetGradientColourFrom(wx.Colour(255, 255, 255))
        notebook.SetGradientColourTo(notebook.Parent.BackgroundColour)
        notebook.SetNonActiveTabTextColour(wx.Colour(128, 128, 128))
        sizer.Add(notebook, border=5, flag=wx.GROW | wx.LEFT | wx.RIGHT)

        panel_config = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_config.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_config.BackgroundColour = wx.WHITE
        notebook.AddPage(panel_config, "Configuration ")
        panel_savedfactors = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_savedfactors.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_savedfactors.BackgroundColour = wx.WHITE
        notebook.AddPage(panel_savedfactors, "Saved factors ")
        panel_detailedfactor = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_detailedfactor.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_detailedfactor.BackgroundColour = wx.WHITE
        notebook.AddPage(panel_detailedfactor, "Expert settings ")


        # Create config page, with time selector and scheduling checkboxes
        text = wx.StaticText(panel_config, label=conf.InfoText,
                             style=wx.ALIGN_CENTER)
        text.ForegroundColour = wx.Colour(92, 92, 92)
        panel_config.Sizer.Add(text, border=5, flag=wx.ALL | wx.ALIGN_CENTER)
        panel_config.Sizer.AddStretchSpacer()
        panel_factor = wx.Panel(panel_config)
        panel_factor.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_factor.Sizer.AddStretchSpacer()
        panel_factor.Sizer.Add(wx.StaticText(panel_factor,
            label="Currently selected screen factor:"), border=5,
            flag=wx.ALL | wx.ALIGN_RIGHT)
        frame.bmp_config = wx.StaticBitmap(panel_factor,
            bitmap=get_factor_bitmap(conf.DimmingFactor))
        frame.bmp_config.SetToolTipString(get_factor_str(conf.DimmingFactor))
        panel_factor.Sizer.Add(frame.bmp_config, flag=wx.ALIGN_RIGHT)
        panel_config.Sizer.Add(panel_factor, border=5, flag=wx.GROW | wx.ALL)

        panel_time = frame.panel_time = wx.Panel(panel_config)
        panel_time.Sizer = wx.BoxSizer(wx.VERTICAL)
        cb_schedule = frame.cb_schedule = wx.CheckBox(panel_time,
            label="Apply automatically during the highlighted hours:"
        )
        panel_time.Sizer.Add(cb_schedule, border=3, flag=wx.ALL)
        selector_time = frame.selector_time = \
            TimeSelector(panel_time, selections=conf.Schedule)
        panel_time.Sizer.Add(selector_time, border=10, flag=wx.GROW)
        panel_config.Sizer.Add(panel_time, border=5, flag=wx.GROW | wx.ALL)
        panel_config.Sizer.AddStretchSpacer()

        panel_version = wx.Panel(panel_config)
        panel_version.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        cb_startup = frame.cb_startup = wx.CheckBox(
            panel_version, label="Run %s at computer startup" % conf.Title
        )
        cb_startup.ToolTipString = "Adds NightFall to startup programs"
        panel_version.Sizer.Add(cb_startup, border=5, flag=wx.LEFT)
        panel_version.Sizer.AddStretchSpacer()
        text = wx.StaticText(panel_version,
            label="v%s, %s   " % (conf.Version, conf.VersionDate))
        text.ForegroundColour = wx.Colour(92, 92, 92)
        panel_version.Sizer.Add(text, flag=wx.ALIGN_RIGHT)
        frame.link_www = wx.HyperlinkCtrl(panel_version, id=-1,
            label="github", url=conf.HomeUrl)
        frame.link_www.ToolTipString = "Go to source code repository " \
                                      "at %s" % conf.HomeUrl
        panel_version.Sizer.Add(frame.link_www, border=5,
                                flag=wx.ALIGN_RIGHT | wx.RIGHT)
        panel_config.Sizer.Add(panel_version, border=2, flag=wx.GROW | wx.ALL)


        # Create saved factors page
        list_factors = frame.list_factors = BitmapListCtrl(panel_savedfactors)
        list_factors.MinSize = (-1, 180)
        thumbs = []
        for i, factor in enumerate(conf.StoredFactors):
            bmp = get_factor_bitmap(factor)
            filename = str(bytearray(factor)).decode("latin1")
            list_factors.RegisterBitmap(filename, bmp, factor)
            thumbs.append(wx.lib.agw.thumbnailctrl.Thumb(list_factors, folder="",
                filename=filename, caption=filename))
        list_factors.ShowThumbs(thumbs, caption="")
        panel_savedfactors.Sizer.Add(frame.list_factors, proportion=1,
                                     border=1, flag=wx.GROW | wx.LEFT)
        panel_saved_buttons = wx.Panel(panel_savedfactors)
        panel_saved_buttons.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_savedfactors.Sizer.Add(panel_saved_buttons, border=5,
                                     flag=wx.GROW | wx.ALL)
        button_apply = frame.button_saved_apply = \
            wx.Button(panel_saved_buttons, label="Apply factor")
        button_delete = frame.button_saved_delete = \
            wx.Button(panel_saved_buttons, label="Remove factor")
        button_apply.Enabled = button_delete.Enabled = False
        panel_saved_buttons.Sizer.Add(button_apply)
        panel_saved_buttons.Sizer.AddStretchSpacer()
        panel_saved_buttons.Sizer.Add(button_delete, flag=wx.ALIGN_RIGHT)

        # Create expert settings page, with RGB sliders and color sample panel
        text_detail = wx.StaticText(panel_detailedfactor,
            style=wx.ALIGN_CENTER, label=conf.InfoDetailedText)
        text_detail.ForegroundColour = wx.Colour(92, 92, 92)
        panel_detailedfactor.Sizer.Add(text_detail, border=5,
            flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)
        panel_detailedfactor.Sizer.AddStretchSpacer()
        panel_colorpicker = frame.panel_colorpicker = \
            wx.Panel(panel_detailedfactor)
        panel_colorpicker.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_detailedfactor.Sizer.Add(panel_colorpicker, border=5,
                                       flag=wx.GROW | wx.ALL)

        panel_sliders = frame.panel_sliders = wx.Panel(panel_colorpicker)
        panel_sliders.Sizer = wx.FlexGridSizer(rows=5, cols=2, vgap=0, hgap=5)
        panel_sliders.Sizer.AddGrowableCol(1, proportion=1)
        sliders = frame.sliders_factor = []
        for i, text in enumerate(["brightness", "red", "green", "blue"]):
            panel_sliders.Sizer.Add(wx.StaticText(panel_sliders,
                label=text.capitalize() + ":"))
            slider = wx.Slider(panel_sliders,
                minValue=conf.ValidColourRange[0] if i else 0,    # Brightness
                maxValue=conf.ValidColourRange[-1] if i else 255, # goes 0..255
                value=conf.DimmingFactor[i],
                size=(-1, 20)
            )
            tooltip = "Change %s colour channel" % text if i \
                      else "Change brightness (center is default, higher " \
                           "goes brighter than normal)"
            slider.ToolTipString = tooltip
            sliders.append(slider)
            panel_sliders.Sizer.Add(slider, proportion=1, flag=wx.GROW)
        panel_sliders.Sizer.AddSpacer(0)
        button_save = frame.button_save = wx.Button(panel_sliders,
                                                    label="Save factor")
        panel_sliders.Sizer.Add(button_save, border=5,
                                flag=wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM)

        panel_colorpicker.Sizer.Add(panel_sliders, proportion=1, flag=wx.GROW)
        panel_colorshower = wx.Panel(panel_colorpicker)
        panel_colorshower.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_color = frame.panel_color = wx.Panel(panel_colorshower)
        panel_color.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_color.SetMinSize((60, 60))
        frame.bmp_detail = wx.StaticBitmap(panel_color,
            bitmap=get_factor_bitmap(conf.DimmingFactor))
        panel_color.Sizer.Add(frame.bmp_detail,flag=wx.ALIGN_RIGHT)
        panel_colorshower.Sizer.Add(panel_color, wx.GROW)
        panel_colorpicker.Sizer.Add(panel_colorshower)

        sizer.AddStretchSpacer()
        panel_buttons = frame.panel_buttons = wx.Panel(panel)
        panel_buttons.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(panel_buttons, border=5, flag=wx.GROW | wx.ALL)
        frame.button_ok = wx.lib.agw.gradientbutton.GradientButton(
            panel_buttons, label="Minimize", size=(100, -1))
        frame.button_exit = wx.lib.agw.gradientbutton.GradientButton(
            panel_buttons, label="Exit program", size=(100, -1))
        for b in (frame.button_ok, frame.button_exit):
            bold_font = wx.SystemSettings_GetFont(wx.SYS_DEFAULT_GUI_FONT)
            bold_font.SetWeight(wx.BOLD)
            b.SetFont(bold_font)
            b.SetTopStartColour(wx.Colour(96, 96, 96))
            b.SetTopEndColour(wx.Colour(112, 112, 112))
            b.SetBottomStartColour(b.GetTopEndColour())
            b.SetBottomEndColour(wx.Colour(160, 160, 160))
            b.SetPressedTopColour(wx.Colour(160, 160, 160))
            b.SetPressedBottomColour(wx.Colour(160, 160, 160))
        frame.button_ok.SetDefault()
        panel_buttons.Sizer.Add(frame.button_ok)
        panel_buttons.Sizer.AddStretchSpacer()
        panel_buttons.Sizer.Add(frame.button_exit, flag=wx.ALIGN_RIGHT)

        wx.CallLater(0, lambda: notebook.SetSelection(0)) # Fix display

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

        colour_off, colour_on = wx.Colour(0, 0 ,0), wx.Colour(0, 0, 255)
        colour_text = wx.Colour(255, 255, 255)
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
                shortcut.Arguments = "\"%s\" %s" % \
                                     (target, conf.StartMinimizedParameter)
            else:
                shortcut.Targetpath = target
                shortcut.Arguments = conf.StartMinimizedParameter
            shortcut.WorkingDirectory = workdir
            if icon:
                shortcut.IconLocation = icon
            shortcut.save()


def get_factor_bitmap(factor, supported=True):
    """
    Returns a wx.Bitmap for the specified factor, with colour and brightness
    information as both text and visual.
    
    @param   supported  whether the factor is supported by hardware
    """
    bmp = wx.Bitmap(conf.ListIcon)
    dc = wx.MemoryDC(bmp)
    brightness_ratio = (factor[0] - 128) / 255.
    rgb = [min(255, int(i + i * brightness_ratio)) for i in factor[1:]]
    colour = wx.Colour(*rgb)
    colour_text = wx.WHITE if sum(rgb) < 255 * 2.3 else wx.Colour(64, 64, 64)
    dc.SetBrush(wx.Brush(colour, wx.SOLID))
    dc.SetPen(wx.Pen(colour if supported else wx.RED))
    dc.DrawRectangle(*((8, 4, 32, 20) if supported else (7, 3, 34, 22)))
    dc.SetTextForeground(colour_text)
    dc.SetPen(wx.Pen(colour_text))
    font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                   wx.FONTWEIGHT_BOLD, face="Tahoma")
    dc.SetFont(font)
    text = "%d%%" % math.ceil(100 * (factor[0] + 1) / conf.NormalBrightness)
    width = dc.GetTextExtent(text)[0]
    dc.DrawText(text, 8 + (34 - width) / 2, 8)
    colour_text = wx.Colour(125, 125, 125) if supported else wx.RED
    dc.SetTextForeground(colour_text)
    dc.SetPen(wx.Pen(colour_text))
    font = wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                   wx.FONTWEIGHT_BOLD, face="Arial")
    dc.SetFont(font)
    rgb = "#%2X%2X%2X" % (factor[1], factor[2], factor[3])
    dc.DrawText(rgb, 2, 36)
    
    del dc
    return bmp


def get_factor_str(factor, supported=True, short=False):
    """Returns a readable string representation of the factor."""
    if short:
        result = "%d%% brightness, #%2X%2X%2X" % (factor[0] / 128. * 100,
                 factor[1], factor[2], factor[3])
    else:
        result = "%d%% brightness.\n%s" % (factor[0] / 128. * 100,
                 ", ".join("%s at %d%%" % (s, factor[i + 1] / 255. * 100)
                          for i, s in enumerate(("Red", "green", "blue"))))
        if not supported:
            result += "\n\nNot supported by hardware."
    return result



class BitmapListHandler(object):
    """
    Image loader for wx.lib.agw.thumbnailctrl.ThumbnailCtrl using
    pre-loaded bitmaps.
    """
    _bitmaps = {} # {filename: wx.Bitmap, }
    _factors = {} # {filename: [factor], }


    @classmethod
    def RegisterBitmap(cls, filename, bitmap, factor):
        cls._bitmaps[filename] = bitmap
        cls._factors[filename] = factor


    @classmethod
    def UnregisterBitmap(cls, filename):
        if filename in cls._bitmaps:
            del cls._bitmaps[filename]
        if filename in cls._factors:
            del cls._factors[filename]


    @classmethod
    def GetFactor(cls, filename):
        return cls._factors[filename]


    def LoadThumbnail(self, filename, thumbnailsize):
        """
        Load the image.

        @param  filename  
        :param `thumbnailsize`: the desired size of the thumbnail.
        """
        img = wx.ImageFromBitmap(self._bitmaps[os.path.basename(filename)])

        originalsize = (img.GetWidth(), img.GetHeight())
        alpha = img.HasAlpha()
        
        return img, originalsize, alpha



class BitmapListCtrl(wx.lib.agw.thumbnailctrl.ThumbnailCtrl):
    """A ThumbnailCtrl that can simply show bitmaps, with files not on disk."""

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize,
                 thumboutline=wx.lib.agw.thumbnailctrl.THUMB_OUTLINE_FULL,
                 thumbfilter=wx.lib.agw.thumbnailctrl.THUMB_FILTER_IMAGES,
                 imagehandler=BitmapListHandler):
        wx.lib.agw.thumbnailctrl.ThumbnailCtrl.__init__(self, parent, id, pos,
            size, thumboutline, thumbfilter, imagehandler
        )
        self.SetDropShadow(False)
        self.EnableToolTips(True)
        self.ShowFileNames(False)
        self.SetThumbSize(68, 47, 6)
        # Hack to get around ThumbnailCtrl's internal monkey-patching
        setattr(self._scrolled, "GetThumbInfo", getattr(self, "_GetThumbInfo"))
        # To disable ThumbnailCtrl's rotation/deletion/etc
        self._scrolled.Bind(wx.EVT_CHAR, None)
        # To disable ThumbnailCtrl's zooming
        self._scrolled.Bind(wx.EVT_MOUSEWHEEL, None)
        self._scrolled.Bind(
            wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_SEL_CHANGED,
            self.OnSelectionChanged)


    def OnSelectionChanged(self, event):
        # Disable ThumbnailCtrl's multiple selection
        self._scrolled._selectedarray[:] = [self.GetSelection()]
        event.Skip()


    def RegisterBitmap(self, filename, bitmap, factor):
        BitmapListHandler.RegisterBitmap(filename, bitmap, factor)


    def UnregisterBitmap(self, filename):
        BitmapListHandler.UnregisterBitmap(filename)


    def GetThumbFactor(self, index):
        """Returns the factor for the specified index."""
        result = None
        thumb_ctrl = self.GetItem(index)
        if thumb_ctrl:
            result = BitmapListHandler.GetFactor(thumb_ctrl.GetFileName())
        return result


    def _GetThumbInfo(self, index=-1):
        """Returns the thumbnail information for the specified index."""
        thumbinfo = None
        
        if index >= 0:
            thumbinfo = get_factor_str(self.GetThumbFactor(index))

        return thumbinfo



if __name__ == '__main__':
    app = NightFall()
    app.MainLoop()
