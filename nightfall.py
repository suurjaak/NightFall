#-*- coding: utf-8 -*-
"""
A tray application that can make screen colors darker and softer during
nocturnal hours, can activate on schedule.

@author      Erki Suurjaak
@created     15.10.2012
@modified    04.09.2020
"""
import collections
import copy
import datetime
import functools
import math
import os
import sys
import warnings
import webbrowser

import wx
import wx.adv
import wx.html
import wx.lib.agw.aquabutton
import wx.lib.agw.flatnotebook
import wx.lib.agw.genericmessagedialog
import wx.lib.agw.gradientbutton
import wx.lib.agw.thumbnailctrl
import wx.lib.agw.ultimatelistctrl
import wx.lib.newevent
import wx.py

import conf
import gamma

"""Event class and event binder for events in Dimmer."""
DimmerEvent, EVT_DIMMER = wx.lib.newevent.NewEvent()

"""Event class and event binder for change-events in TimeSelector."""
TimeSelectorEvent, EVT_TIME_SELECTOR = wx.lib.newevent.NewEvent()


class Dimmer(object):
    """Model handling current screen gamma state and configuration."""

    """Seconds between checking whether to apply/unapply schedule."""
    INTERVAL = 30

    def __init__(self, event_handler):
        self.handler = event_handler

        conf.load()
        self.check_conf()

        self.current_theme = copy.copy(conf.NormalTheme) # Applied colour theme
        self.fade_timer = None # wx.Timer instance for applying fading
        self.fade_steps = None # Number of steps to take during a fade
        self.fade_delta = None # Delta to add to theme components on fade step
        self.fade_target_theme   = None # Final theme values during fade
        self.fade_current_theme  = None # Theme float values during fade
        self.fade_original_theme = None # Original theme before applying fade
        self.fade_info = None # Info given for applying/setting theme

        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(milliseconds=1000 * self.INTERVAL)


    def check_conf(self):
        """Sanity-checks configuration loaded from file."""

        def is_valid(theme):
            if not isinstance(theme, (list, tuple)) \
            or len(theme) != len(conf.NormalTheme): return False
            for g in theme[:-1]:
                if not isinstance(g, (int, float)) \
                or not (conf.ValidColourRange[0] <= g <= conf.ValidColourRange[-1]):
                    return False
            return 0 <= theme[-1] <= 255

        if not is_valid(conf.CurrentTheme):
            conf.CurrentTheme = copy.copy(conf.Defaults["CurrentTheme"])
        if not is_valid(conf.UnsavedTheme):
            conf.UnsavedTheme = None
        if not isinstance(conf.Themes, dict):
            conf.Themes = copy.deepcopy(conf.Defaults["Themes"])

        for name, theme in conf.Themes.items():
            if not is_valid(theme): conf.Themes.pop(name)

        if not isinstance(conf.Schedule, list) \
        or len(conf.Schedule) != len(conf.DefaultSchedule):
            conf.Schedule = conf.DefaultSchedule[:]
        for i, g in enumerate(conf.Schedule):
            if g not in [0, 1]:
                conf.Schedule[i] = conf.DefaultSchedule[i]
        conf.StartupEnabled = StartupService.is_started()


    def start(self):
        """Starts handler: updates GUI settings, and dims if so configured."""
        self.post_event("THEME CHANGED",    conf.CurrentTheme)
        self.post_event("GAMMA TOGGLED",    conf.ThemeEnabled)
        self.post_event("SCHEDULE TOGGLED", conf.ScheduleEnabled)
        self.post_event("SCHEDULE CHANGED", conf.Schedule)
        self.post_event("STARTUP TOGGLED",  conf.StartupEnabled)
        self.post_event("STARTUP POSSIBLE", StartupService.can_start())
        if self.should_dim():
            self.apply_theme(conf.CurrentTheme, fade=True)
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() else \
                  "GAMMA ON"
            self.post_event(msg, conf.CurrentTheme)
        else:
            self.apply_theme(conf.NormalTheme)


    def stop(self):
        """Stops any current dimming."""
        self.apply_theme(conf.NormalTheme)
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
        if conf.ScheduleEnabled and not conf.ThemeEnabled:
            theme, msg = conf.NormalTheme, "GAMMA OFF"
            if self.should_dim_scheduled():
                theme, msg = conf.CurrentTheme, "SCHEDULE IN EFFECT"
            if theme != self.current_theme:
                self.apply_theme(theme, fade=True)
                self.post_event(msg)


    def set_theme(self, theme, info=None):
        """
        Sets the current screen colour theme, and applies it if enabled.

        @param   theme  a 4-byte list, for 3 RGB channels and brightness, 0..255
        @param   info   info given to callback event, if any
        @return         False on failure, True otherwise
        """
        result = True
        changed = (theme != self.current_theme)
        if changed:
            conf.CurrentTheme = theme[:]
            self.post_event("THEME CHANGED", theme, info)
            conf.save()
            if self.should_dim():
                result = self.apply_theme(theme, info)
        return result


    def toggle_schedule(self, enabled):
        """Toggles the scheduled dimming on/off."""
        changed = (enabled != conf.ScheduleEnabled)
        if changed:
            conf.ScheduleEnabled = enabled
            self.post_event("SCHEDULE TOGGLED", conf.ScheduleEnabled)
            conf.save()
            theme, msg = conf.NormalTheme, "GAMMA OFF"
            if self.should_dim():
                theme = conf.CurrentTheme
                msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() \
                      else "GAMMA ON"
            self.apply_theme(theme, fade=True)
            self.post_event(msg, theme)


    def toggle_startup(self, enabled):
        """Toggles running NightFall on system startup."""
        if StartupService.can_start():
            conf.StartupEnabled = enabled
            StartupService.start() if enabled else StartupService.stop()
            conf.save()
            self.post_event("STARTUP TOGGLED", conf.StartupEnabled)


    def set_schedule(self, schedule):
        """
        Sets the current screen dimming schedule, and applies it if suitable.

        @param   selections  selected times, [1,0,..] per each hour
        """
        changed = (schedule != conf.Schedule)
        if not changed: return

        did_dim_scheduled = self.should_dim_scheduled()
        conf.Schedule = schedule[:]
        self.post_event("SCHEDULE CHANGED", conf.Schedule)
        conf.save()
        if did_dim_scheduled and self.should_dim_scheduled(): return

        theme, msg = conf.NormalTheme, "GAMMA OFF"
        if self.should_dim():
            theme = conf.CurrentTheme
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() \
                  else "GAMMA ON"
        self.apply_theme(theme, fade=True)
        self.post_event(msg, theme)


    def should_dim(self):
        """
        Returns whether dimming should currently be applied, based on global
        enabled flag and enabled time selection.
        """
        return conf.ThemeEnabled or self.should_dim_scheduled()


    def should_dim_scheduled(self):
        """Whether dimming should currently be on, according to schedule."""
        result = False
        if conf.ScheduleEnabled:
            t = datetime.datetime.now().time()
            H_MUL = len(conf.Schedule) / 24
            M_DIV = 60 / H_MUL
            result = bool(conf.Schedule[t.hour * H_MUL + t.minute / M_DIV])
        return result


    def apply_theme(self, theme, info=None, fade=False):
        """
        Applies the specified colour theme.

        @param   info   info given to callback event, if any
        @param   fade   if True, changes theme from current to new smoothly,
                        in a number of steps
        @return         False on failure, True otherwise
        """
        result = True
        if self.fade_timer:
            self.fade_timer.Stop()
            self.fade_target_theme = self.fade_info = None
            self.fade_delta = self.fade_steps = self.fade_timer = None
            self.fade_current_theme = self.fade_original_theme = None
        if fade or (info and "THEME MODIFIED" != info):
            self.fade_info = info
            self.fade_steps = conf.FadeSteps
            self.fade_target_theme = theme[:]
            self.fade_current_theme = map(float, self.current_theme)
            self.fade_original_theme = self.current_theme[:]
            self.fade_delta = []
            for new, now in zip(theme, self.current_theme):
                self.fade_delta.append(float(new - now) / conf.FadeSteps)
            self.fade_timer = wx.CallLater(conf.FadeDelay, self.on_fade_step)
        elif gamma.set_screen_gamma(theme):
            self.current_theme = theme[:]
        else:
            self.post_event("THEME FAILED", theme, info)
            result = False
        return result


    def on_fade_step(self):
        """
        Handler for a fade step, applies the fade delta to colour theme and
        schedules another event, if more steps left.
        """
        self.fade_timer = None
        if self.fade_steps:
            self.fade_current_theme = [(current + delta) for current, delta
                in zip(self.fade_current_theme, self.fade_delta)]
            self.fade_steps -= 1
            if not self.fade_steps:
                # Final step: use exact given target, to avoid rounding errors
                current_theme = self.fade_target_theme
            else:
                current_theme = map(int, map(round, self.fade_current_theme))
            success = self.apply_theme(current_theme)
            if success and self.should_dim() \
            and self.fade_original_theme != conf.NormalTheme:
                # Send incremental change if fading from one theme to another.
                self.post_event("THEME CHANGED", current_theme, self.fade_info)
            elif not success:
                if not self.fade_steps:
                    # Unsupported theme: jump back to normal on last step.
                    self.apply_theme(conf.NormalTheme, fade=False)
            if self.fade_steps:
                self.fade_timer = wx.CallLater(conf.FadeDelay, self.on_fade_step)
            else:
                self.fade_target_theme = None
                self.fade_delta = self.fade_steps = self.fade_info = None
                self.fade_current_theme = self.fade_original_theme = None



    def toggle_dimming(self, enabled):
        """Toggles the global dimmer flag enabled/disabled."""
        changed = (conf.ThemeEnabled != enabled)
        conf.ThemeEnabled = enabled
        msg = "GAMMA TOGGLED"
        if self.should_dim():
            theme = conf.CurrentTheme
            if self.should_dim_scheduled(): msg = "SCHEDULE IN EFFECT"
        else:
            theme = conf.NormalTheme
        self.apply_theme(theme, fade=True)
        if changed: conf.save()
        self.post_event(msg, conf.ThemeEnabled)



class NightFall(wx.App):
    """
    The NightFall application, controller managing the GUI elements 
    and communication with the dimmer model.
    """


    def __init__(self, redirect=False, filename=None,
                 useBestVisual=False, clearSigInt=True):
        wx.App.__init__(self, redirect, filename, useBestVisual, clearSigInt)
        self.dimmer = Dimmer(self)

        self.frame_hider    = None # wx.CallLater object for timed hiding on blur
        self.frame_shower   = None # wx.CallLater object for timed showing on slideout
        self.frame_pos_orig = None # Position of frame before slidein
        self.frame_unmoved  = True # Whether user has moved the window
        self.frame_move_ignore = False # Ignore EVT_MOVE on showing window
        self.frame_has_modal   = False # Whether a modal dialog is open
        self.dt_tray_click     = None  # Last click timestamp, for double-click
        self.name_selected     = None # Last named theme selected
        self.frame = frame = self.create_frame()

        frame.Bind(wx.EVT_CHECKBOX, self.on_toggle_schedule, frame.cb_schedule)
        frame.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_SEL_CHANGED,
            self.on_select_list_theme, frame.list_themes._scrolled)
        frame.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_DCLICK,
            self.on_apply_list_theme, frame.list_themes._scrolled)

        ColourManager.Init(frame)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_dimming, frame.cb_enabled)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_startup, frame.cb_startup)
        frame.Bind(wx.EVT_BUTTON,     self.on_toggle_settings, frame.button_ok)
        frame.Bind(wx.EVT_BUTTON,     self.on_exit, frame.button_exit)
        frame.Bind(wx.EVT_BUTTON,     self.on_apply_list_theme, frame.button_apply)
        frame.Bind(wx.EVT_BUTTON,     self.on_delete_theme, frame.button_delete)
        frame.Bind(wx.EVT_BUTTON,     self.on_save_theme,   frame.button_save)
        frame.Bind(wx.EVT_COMBOBOX,   self.on_select_combo_theme, frame.combo_themes)
        frame.link_www.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                            lambda e: webbrowser.open(e.GetLinkInfo().Href))
        frame.label_about.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                            lambda e: webbrowser.open(e.GetLinkInfo().Href))

        frame.Bind(EVT_TIME_SELECTOR, self.on_change_schedule)
        frame.Bind(wx.EVT_CLOSE,      self.on_toggle_settings)
        frame.Bind(wx.EVT_ACTIVATE,   self.on_activate_settings)
        frame.Bind(wx.EVT_MOVE,       self.on_move)
        for s in frame.sliders:
            frame.Bind(wx.EVT_SCROLL, self.on_change_theme_detail, s)
            frame.Bind(wx.EVT_SLIDER, self.on_change_theme_detail, s)
        self.Bind(EVT_DIMMER,         self.on_dimmer_event)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_toggle_console, frame.label_combo)
        self.frame.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)

        self.TRAYICONS = {False: {}, True: {}}
        # Cache tray icons in dicts [dimming now][schedule enabled]
        for i, f in enumerate(conf.TrayIcons):
            dim, sch = False if i < 2 else True, True if i % 2 else False
            self.TRAYICONS[dim][sch] = wx.Icon(wx.Bitmap(f))
        trayicon = self.trayicon = wx.adv.TaskBarIcon()
        self.set_tray_icon(self.TRAYICONS[False][False])
        trayicon.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_toggle_dimming_tray)
        trayicon.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN,   self.on_lclick_tray)
        trayicon.Bind(wx.adv.EVT_TASKBAR_RIGHT_DOWN,  self.on_open_tray_menu)

        self.dimmer.start()
        if conf.StartMinimizedParameter not in sys.argv:
            self.frame_move_ignore = True # Skip first move event on Show()
            frame.Show()


    def on_dimmer_event(self, event):
        """Handler for all events sent from Dimmer, updates UI controls."""
        topic, data, info = event.Topic, event.Data, event.Info
        if "THEME CHANGED" == topic:
            for i, g in enumerate(data):
                self.frame.sliders[i].SetValue(g)
            bmp, tooltip = get_theme_bitmap(data, border=True), get_theme_str(data)
            for b in [self.frame.bmp_detail]: b.Bitmap, b.ToolTip = bmp, tooltip
            self.frame.label_error.Hide()
        elif "THEME FAILED" == topic:
            bmp = get_theme_bitmap(data, supported=False)
            tooltip = get_theme_str(data, supported=False)
            for b in [self.frame.bmp_detail]: b.Bitmap, b.ToolTip = bmp, tooltip
            self.frame.label_error.Label = "Setting unsupported by hardware."
            self.frame.label_error.Show()
            self.frame.label_error.ContainingSizer.Layout()
            self.frame.label_error.Wrap(self.frame.label_error.Size[0])
            if "THEME APPLIED" == info:
                index = self.frame.list_themes.FindIndex(theme=data)
                if index >= 0: self.frame.list_themes.GetItem(i).SetBitmap(bmp)
                self.frame_has_modal = True
                wx.MessageBox("Setting not supported by graphics hardware.",
                              conf.Title, wx.OK | wx.ICON_WARNING)
                self.frame_has_modal = False
        elif "GAMMA TOGGLED" == topic:
            self.frame.cb_enabled.Value = data
            self.set_tray_icon(self.TRAYICONS[data][conf.ScheduleEnabled])
            if self.dimmer.should_dim():
                idx = self.frame.list_themes.FindIndex(theme=conf.CurrentTheme)
                if idx >= 0: self.frame.list_themes.SetSelection(idx)
        elif "SCHEDULE TOGGLED" == topic:
            self.frame.cb_schedule.Value = data
            self.set_tray_icon(self.TRAYICONS[self.dimmer.should_dim()][data])
        elif "SCHEDULE CHANGED" == topic:
            self.frame.selector_time.SetSelections(data)
        elif "SCHEDULE IN EFFECT" == topic:
            self.set_tray_icon(self.TRAYICONS[True][True])
            idx = self.frame.list_themes.FindIndex(theme=conf.CurrentTheme)
            if idx >= 0: self.frame.list_themes.SetSelection(idx)
            self.frame.cb_enabled.Disable()
            if not self.frame.Shown:
                m = wx.adv.NotificationMessage(title=conf.Title,
                                               message="Dimmer schedule in effect.")
                m.UseTaskBarIcon(self.trayicon)
                m.Show()
        elif "STARTUP TOGGLED" == topic:
            self.frame.cb_startup.Value = data
        elif "STARTUP POSSIBLE" == topic:
            self.frame.cb_startup.Show(data)
        elif "GAMMA ON" == topic:
            self.set_tray_icon(self.TRAYICONS[True][conf.ScheduleEnabled])
        elif "GAMMA OFF" == topic:
            self.set_tray_icon(self.TRAYICONS[False][conf.ScheduleEnabled])
            self.frame.cb_enabled.Enable()

        if "THEME APPLIED" in (topic, info):
            idx = self.frame.combo_themes.FindIndex(theme=data)
            if idx >= 0: self.frame.combo_themes.Select(idx)


    def set_tray_icon(self, icon):
        """Sets the icon into tray and sets a configured tooltip."""
        self.trayicon.SetIcon(icon, conf.TrayTooltip)


    def on_select_list_theme(self, event):
        """Handler for selecting a theme in list, toggles buttons enabled."""
        event.Skip()
        selected = self.frame.list_themes.GetSelection()
        self.frame.button_apply.Enabled  = (selected >= 0)
        self.frame.button_delete.Enabled = (selected >= 0)


    def on_apply_list_theme(self, event=None):
        """Applies the colour theme selected in list."""
        selected = self.frame.list_themes.GetSelection()
        if selected < 0: return

        self.name_selected, theme = self.frame.list_themes.GetItemData(selected)
        if not self.dimmer.should_dim():
            conf.ThemeEnabled = True
            self.frame.cb_enabled.Value = True
            self.set_tray_icon(self.TRAYICONS[True][conf.ScheduleEnabled])
        self.dimmer.set_theme(theme, "THEME APPLIED")


    def on_save_theme(self, event=None):
        """Stores the currently set rgb+brightness values."""
        theme = conf.CurrentTheme
        name0 = name = self.name_selected or get_theme_str(theme, short=True)

        self.frame_has_modal = True
        dlg = wx.TextEntryDialog(self.frame, "Name:", conf.Title,
                                 value=name, style=wx.OK | wx.CANCEL)
        dlg.CenterOnParent()
        resp = dlg.ShowModal()
        self.frame_has_modal = False
        if wx.ID_OK != resp: return

        name = dlg.GetValue().strip()
        if not name: return

        lst, cmb = self.frame.list_themes, self.frame.combo_themes
        if theme == conf.Themes.get(name): # No change
            conf.UnsavedTheme = None
            conf.save()
            cmb.Delete(0)
            cmb.Select(cmb.FindIndex(name=name))
            return

        if name in conf.Themes:
            self.frame_has_modal = True
            resp = wx.MessageBox('Theme named "%s" already exists, '
                'are you sure you want to overwrite it?' % name, conf.Title,
                 wx.OK | wx.CANCEL | wx.ICON_INFORMATION
            )
            self.frame_has_modal = False
            if wx.OK != resp: return

        lst.RegisterBitmap(name, get_theme_bitmap(theme), theme)
        if name in conf.Themes:
            cmb.ReplaceItem((name, theme), cmb.FindIndex(name=name))
            lst.Refresh() # @todo vt kas on vaja
        else:
            thumbs = [lst.GetItem(i) for i in range(lst.GetItemCount())]
            thumb = wx.lib.agw.thumbnailctrl.Thumb(self, folder="", filename=name, caption=name)
            thumbs.append(thumb)
            lst.ShowThumbs(thumbs, caption="")
            choices = conf.Themes.items()
            cmb.SetItems(sorted(choices + [(name, theme)]))
        cmb.Select(cmb.FindIndex(name=name))
        lst.SetSelection(lst.FindIndex(name=name))
        conf.Themes[name] = theme
        conf.UnsavedTheme = None
        conf.save()


    def on_delete_theme(self, event=None):
        """Deletes the stored theme on confirm."""
        selected = self.frame.list_themes.GetSelection()
        if selected < 0: return

        name, theme = self.frame.list_themes.GetItemData(selected)
        self.frame_has_modal = True
        resp = wx.MessageBox('Delete theme "%s"?' % name,
                             conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING)
        self.frame_has_modal = False
        if wx.OK != resp: return

        if name in conf.Themes:
            conf.Themes.pop(name)
            conf.save()
        self.frame.list_themes.UnregisterBitmap(name)
        self.frame.list_themes.RemoveItemAt(selected)
        self.frame.list_themes.Refresh()
        if self.dimmer.should_dim() and theme == conf.CurrentTheme:
            self.dimmer.toggle_dimming(False)

        idx, idx2 = self.frame.combo_themes.FindIndex(name=name), -1
        if idx >= 0:
            self.frame.combo_themes.Delete(idx)
            idx2 = self.frame.combo_themes.Selection
        if idx2 >= 0:
            name2, theme2 = self.frame.combo_themes.GetItemData(idx2)
            self.name_selected = name2 if name2 in conf.Themes else None
            conf.CurrentTheme = theme2


    def on_open_tray_menu(self, event=None):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()

        def on_apply_theme(name, theme, event):
            if not self.dimmer.should_dim():
                conf.ThemeEnabled = True
                self.frame.cb_enabled.Value = True
                self.set_tray_icon(self.TRAYICONS[True][conf.ScheduleEnabled])
            self.dimmer.set_theme(theme, "THEME APPLIED")


        is_dimming = self.dimmer.should_dim()
        text = "&Turn " + ("current dimming off" if self.dimmer.should_dim() else
                           "dimming on")
        item = wx.MenuItem(menu, -1, text, kind=wx.ITEM_CHECK)
        item.Font = self.frame.Font.Bold()
        menu.Append(item)
        item.Check(is_dimming)
        menu.Bind(wx.EVT_MENU, self.on_toggle_dimming_tray, id=item.GetId())

        item = menu.Append(-1, "Apply on &schedule", kind=wx.ITEM_CHECK)
        item.Check(conf.ScheduleEnabled)
        menu.Bind(wx.EVT_MENU, self.on_toggle_schedule, id=item.GetId())
        item = menu.Append(-1, "&Run at startup", kind=wx.ITEM_CHECK)
        item.Check(conf.StartupEnabled)
        menu.Bind(wx.EVT_MENU, self.on_toggle_startup, id=item.GetId())
        menu.AppendSeparator()

        menu_themes = wx.Menu()
        for name, theme in sorted(conf.Themes.items()):
            item = menu_themes.Append(-1, name, kind=wx.ITEM_CHECK)
            item.Check(is_dimming and theme == conf.CurrentTheme)
            handler = functools.partial(on_apply_theme, name, theme)
            menu.Bind(wx.EVT_MENU, handler, id=item.GetId())
        menu.Append(-1, "&Apply theme", menu_themes)

        item = wx.MenuItem(menu, -1, "&Options")
        item.Enable(not self.frame.Shown)
        menu.Bind(wx.EVT_MENU, self.on_toggle_settings, id=item.GetId())
        menu.Append(item)
        item = wx.MenuItem(menu, -1, "E&xit NightFall")
        menu.Bind(wx.EVT_MENU, self.on_exit, id=item.GetId())
        menu.Append(item)

        self.trayicon.PopupMenu(menu)


    def on_change_schedule(self, event=None):
        """Handler for changing the time schedule in settings window."""
        self.dimmer.set_schedule(self.frame.selector_time.GetSelections())


    def on_toggle_startup(self, event=None):
        """Handler for toggling the auto-load in settings window on/off."""
        self.dimmer.toggle_startup(not conf.StartupEnabled)


    def on_activate_settings(self, event):
        """Handler for activating/deactivating window, hides it if focus lost."""
        if not self.frame or self.frame_has_modal \
        or not self.trayicon.IsAvailable(): return

        if self.frame.Shown \
        and not (event.Active or self.frame_hider or self.frame_shower):
            millis = conf.WindowTimeout
            if millis: # Hide if timeout positive
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
            self.frame.Position = (self.frame.Position.x, y + conf.WindowSlideInStep)
            self.frame_hider = wx.CallLater(conf.WindowSlideDelay, self.settings_slidein)
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
        if not self.frame_pos_orig:
            self.frame_pos_orig = self.frame.Position.x, display_h - h
            self.frame.Position = self.frame_pos_orig[0], display_h
        y = self.frame.Position.y
        if not self.frame.Shown:
            self.frame.Show()
        if (y + h > display_h):
            self.frame.Position = (self.frame.Position.x, y - conf.WindowSlideOutStep)
            self.frame_shower = wx.CallLater(conf.WindowSlideDelay, self.settings_slideout)
        else:
            self.frame_shower = None
            self.frame_pos_orig = None
            self.frame.Raise()


    def on_exit(self, event=None):
        """Handler for exiting the program, stops the dimmer and cleans up."""
        self.dimmer.stop()
        self.trayicon.RemoveIcon()
        self.trayicon.Destroy()
        self.frame.Destroy()
        wx.CallAfter(sys.exit) # Immediate exit fails if exiting from tray


    def on_toggle_console(self, event):
        """
        Handler for clicking to open the Python console, activated if
        Ctrl-Alt-Shift is down.
        """
        if event.CmdDown() and event.ShiftDown():
            self.frame_console.Show(not self.frame_console.Shown)


    def on_move(self, event=None):
        """Handler for moving the window, clears window auto-positioning."""
        if self.frame_pos_orig is None and self.frame_move_ignore:
            self.frame_unmoved = False
        self.frame_move_ignore = False


    def on_toggle_settings(self, event=None):
        """Handler for clicking to toggle settings window visible/hidden."""
        if self.frame_has_modal: return

        if not self.trayicon.IsAvailable():
            self.frame.Iconize(not self.frame.IsIconized())
            return

        if self.frame_hider: # Window is sliding closed
            self.frame_hider.Stop()
            if self.frame_pos_orig: # Was already sliding: back to original pos
                self.frame.Position = self.frame_pos_orig
            else: # Window was shown: toggle window off
                self.frame.Hide()
            self.frame_hider = None
            self.frame_pos_orig = None
        elif self.frame_shower: # Window is sliding open
            self.frame_shower.Stop()
            self.frame_shower = None
            millis = conf.WindowTimeout
            if millis: # Hide if timeout positive
                if conf.WindowSlideInEnabled:
                    self.frame_hider = wx.CallLater(millis,
                                                    self.settings_slidein)
                else:
                    self.frame_hider = wx.CallLater(millis, self.frame.Hide)
            else:
                self.frame.Hide()
                self.frame.Position = self.frame_pos_orig
        else:
            if not self.frame.Shown:
                if self.frame_unmoved:
                    x1, y1, x2, y2 = wx.GetClientDisplayRect() # Set in lower right corner
                    self.frame.Position = (x2 - self.frame.Size.x, y2 - self.frame.Size.y)
                if conf.WindowSlideOutEnabled:
                    self.frame_shower = wx.CallLater(
                        conf.WindowSlideDelay, self.settings_slideout)
                else:
                    self.frame.Shown = True
                    self.frame_move_ignore = True
            else:
                self.frame.Shown = not self.frame.Shown
        if self.frame.Shown:
            self.frame.Raise()


    def on_change_theme_detail(self, event):
        """Handler for a change in colour theme properties."""
        theme = []
        for s in self.frame.sliders:
            new = isinstance(event, wx.ScrollEvent) and s is event.EventObject
            value = event.GetPosition() if new else s.GetValue()
            theme.append(value)
        self.dimmer.set_theme(theme, "THEME MODIFIED")
        if conf.UnsavedTheme:
            self.frame.combo_themes.ReplaceItem((" (unsaved) ", theme), 0)
        else:
            self.frame.combo_themes.Insert((" (unsaved) ", theme), 0)
        self.frame.combo_themes.Select(0)
        conf.UnsavedTheme = theme


    def on_select_combo_theme(self, event):
        """Handler for selecting an item in combobox."""
        name, theme = self.frame.combo_themes.GetItemData(event.Selection)
        self.name_selected = name if name in conf.Themes else None
        self.dimmer.set_theme(theme, "THEME APPLIED")


    def on_toggle_dimming(self, event):
        """Handler for toggling dimming on/off."""
        self.dimmer.toggle_dimming(event.IsChecked())


    def on_toggle_dimming_tray(self, event=None):
        """
        Handler for toggling dimming on/off from the tray, can affect either
        schedule or global flag.
        """
        self.dt_tray_click = None
        do_dim = event.IsChecked() if isinstance(event, wx.CommandEvent) \
                 else not self.dimmer.should_dim()
        if not do_dim and self.dimmer.should_dim_scheduled():
            self.dimmer.toggle_schedule(False)
        self.dimmer.toggle_dimming(do_dim)


    def on_toggle_schedule(self, event):
        """Handler for toggling schedule on/off."""
        self.dimmer.toggle_schedule(event.IsChecked())


    def on_lclick_tray(self, event):
        """
        Handler for left-clicking the tray icon, waits to see if user
        is double-clicking, otherwise toggles the settings window.        
        """
        if self.dt_tray_click: return

        def after():
            if not self or not self.dt_tray_click: return
            self.dt_tray_click = None
            self.on_toggle_settings()
            
        self.dt_tray_click = datetime.datetime.utcnow()
        wx.CallLater(wx.SystemSettings.GetMetric(wx.SYS_DCLICK_MSEC) + 1, after)


    def on_sys_colour_change(self, event):
        """Handler for system colour change, refreshes About-text."""
        event.Skip()
        args = {"textcolour": ColourManager.ColourHex(wx.SYS_COLOUR_BTNTEXT),
                "linkcolour": ColourManager.ColourHex(wx.SYS_COLOUR_HOTLIGHT)}
        self.frame.label_about.SetPage(conf.AboutText % args)


    def create_frame(self):
        """Creates and returns the settings window."""
        frame = wx.Frame(parent=None, title=conf.Title, size=conf.WindowSize,
            style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX | wx.STAY_ON_TOP
        )

        panel = frame.panel = wx.Panel(frame)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)

        cb_enabled = frame.cb_enabled = wx.CheckBox(panel, label="Dim now")
        cb_enabled.SetValue(conf.ThemeEnabled)
        cb_enabled.ToolTip = "Apply dimming settings now"
        sizer.Add(cb_enabled, border=5, flag=wx.ALL)

        notebook = frame.notebook = wx.lib.agw.flatnotebook.FlatNotebook(panel)
        notebook.SetAGWWindowStyleFlag(
              wx.lib.agw.flatnotebook.FNB_FANCY_TABS
            | wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON
            | wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS
            | wx.lib.agw.flatnotebook.FNB_NODRAG
            | wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS)
        ColourManager.Manage(notebook, "ActiveTabTextColour",    wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(notebook, "NonActiveTabTextColour", wx.SYS_COLOUR_GRAYTEXT)
        ColourManager.Manage(notebook, "TabAreaColour",          wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(notebook, "GradientColourBorder",   wx.SYS_COLOUR_BTNSHADOW)
        ColourManager.Manage(notebook, "GradientColourFrom",     wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(notebook, "GradientColourTo",       wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(notebook, "NonActiveTabTextColour", wx.SYS_COLOUR_GRAYTEXT)
        sizer.Add(notebook, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.RIGHT)

        panel_config = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_config.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel_config, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        notebook.AddPage(panel_config, "Schedule ")
        panel_themes = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_themes.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel_themes, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        notebook.AddPage(panel_themes, "Saved themes ")
        panel_editor = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_editor.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel_editor, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        notebook.AddPage(panel_editor, "Theme editor ")
        panel_about = wx.Panel(notebook, style=wx.BORDER_NONE)
        panel_about.Sizer = wx.BoxSizer(wx.VERTICAL)
        notebook.AddPage(panel_about, "About ")

        # Create config page, with time selector and scheduling checkboxes
        panel_middle = wx.Panel(panel_config)
        ColourManager.Manage(panel_middle, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        sizer_middle = wx.BoxSizer(wx.HORIZONTAL)
        sizer_right = wx.BoxSizer(wx.VERTICAL)
        selector_time = frame.selector_time = ClockSelector(panel_config, selections=conf.Schedule)
        sizer_middle.Add(selector_time, proportion=1, border=5, flag=wx.GROW | wx.ALL)
        frame.label_combo = wx.StaticText(panel_config, label="Colour theme:")
        sizer_right.Add(frame.label_combo)

        choices = sorted(conf.Themes.items())
        if conf.UnsavedTheme:
            choices.insert(0, (" (unsaved) ", conf.UnsavedTheme))
        selected = next((i for i, (a, b) in enumerate(choices)
                         if b == conf.CurrentTheme), None)
        combo_themes = frame.combo_themes = ThemeComboBox(panel_config, 
            choices=choices, selected=selected, 
            bitmapsize=conf.ThemeBitmapSize, style=wx.CB_READONLY)
        combo_themes.SetPopupMaxHeight(200)
        sizer_right.Add(combo_themes)

        label_error = frame.label_error = wx.StaticText(panel_config, style=wx.ALIGN_CENTER)
        ColourManager.Manage(label_error, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)
        sizer_right.Add(label_error, border=10, flag=wx.TOP | wx.BOTTOM)
        sizer_right.AddStretchSpacer()

        cb_schedule = frame.cb_schedule = wx.CheckBox(panel_config, label="Apply on schedule")
        cb_schedule.ToolTip = "Apply automatically during the highlighted hours"
        sizer_right.Add(cb_schedule, border=5, flag=wx.ALL)
        cb_startup = frame.cb_startup = wx.CheckBox(panel_config, label="Run at startup")
        cb_startup.ToolTip = "Adds NightFall to startup programs"
        sizer_right.Add(cb_startup, border=5, flag=wx.LEFT)

        sizer_middle.Add(sizer_right, border=5, flag=wx.BOTTOM | wx.GROW)
        panel_config.Sizer.Add(sizer_middle, proportion=1, border=5, flag=wx.GROW | wx.ALL)


        # Create saved themes page
        list_themes = frame.list_themes = BitmapListCtrl(panel_themes, bitmapsize=conf.ThemeBitmapSize)
        ColourManager.Manage(list_themes, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        thumbs = []
        for name, theme in conf.Themes.items():
            bmp = get_theme_bitmap(theme)
            list_themes.RegisterBitmap(name, bmp, theme)
            thumbs.append(wx.lib.agw.thumbnailctrl.Thumb(list_themes, folder="",
                filename=name, caption=name))
        list_themes.ShowThumbs(thumbs, caption="")
        idx = list_themes.FindIndex(theme=conf.CurrentTheme)
        if idx >= 0:
            list_themes.SetSelection(idx)
            self.name_selected = list_themes.GetItemName(idx)

        panel_themes.Sizer.Add(list_themes, border=5, proportion=1, flag=wx.TOP | wx.GROW)
        panel_saved_buttons = wx.Panel(panel_themes)
        panel_saved_buttons.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_themes.Sizer.Add(panel_saved_buttons, border=5,
                                     flag=wx.GROW | wx.ALL)
        button_apply = frame.button_apply = \
            wx.Button(panel_saved_buttons, label="Apply theme")
        button_delete = frame.button_delete = \
            wx.Button(panel_saved_buttons, label="Remove theme")
        button_apply.Enabled = button_delete.Enabled = (list_themes.GetSelection() >= 0)
        panel_saved_buttons.Sizer.Add(button_apply)
        panel_saved_buttons.Sizer.AddStretchSpacer()
        panel_saved_buttons.Sizer.Add(button_delete)


        # Create theme editor page, with RGB sliders and color sample panel
        text_detail = wx.StaticText(panel_editor,
            style=wx.ALIGN_CENTER, label=conf.InfoEditorText)
        ColourManager.Manage(text_detail, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)
        panel_editor.Sizer.Add(text_detail, border=5,
            flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)
        panel_editor.Sizer.AddStretchSpacer()

        sizer_bar = wx.BoxSizer(wx.HORIZONTAL)
        sizer_right = wx.BoxSizer(wx.VERTICAL)

        sizer_sliders = wx.FlexGridSizer(rows=4, cols=3, vgap=2, hgap=5)
        sizer_sliders.AddGrowableCol(1, proportion=1)
        frame.sliders = []
        kws = dict(red=0, green=0, blue=0)
        for i, text in enumerate(["brightness", "red", "green", "blue"]):
            if i: bmp1, bmp2 = [get_colour_bitmap(wx.Colour(**dict(kws, **{text: x})))
                                for x in conf.ValidColourRange]
            else: bmp1, bmp2 = map(wx.Bitmap,         conf.BrightnessIcons)
            sbmp1 = wx.StaticBitmap(panel_editor, bitmap=bmp1)
            sbmp2 = wx.StaticBitmap(panel_editor, bitmap=bmp2)
            slider = wx.Slider(panel_editor,
                minValue=conf.ValidColourRange[0]  if i else   0, # Brightness
                maxValue=conf.ValidColourRange[-1] if i else 255, # goes 0..255
                value=conf.CurrentTheme[i], size=(-1, 20)
            )
            tooltip = "%s colour channel" % text.capitalize() if i else \
                      "Brightness (center is default, " \
                      "higher goes brighter than normal)"
            sbmp1.ToolTip = sbmp2.ToolTip = tooltip
            sizer_sliders.Add(sbmp1,  flag=wx.ALIGN_CENTER)
            sizer_sliders.Add(slider, flag=wx.ALIGN_CENTER_VERTICAL | wx.GROW)
            sizer_sliders.Add(sbmp2,  flag=wx.ALIGN_CENTER)
            frame.sliders.append(slider)
        frame.sliders.append(frame.sliders.pop(0)) # Make brightness first

        frame.bmp_detail = wx.StaticBitmap(panel_editor,
            bitmap=get_theme_bitmap(conf.CurrentTheme, border=True))
        sizer_right.Add(frame.bmp_detail, border=5, flag=wx.TOP)

        button_save = frame.button_save = wx.Button(panel_editor, label="Save theme")
        sizer_right.Add(button_save, border=5, flag=wx.TOP | wx.GROW)

        sizer_bar.Add(sizer_sliders, border=10, proportion=1, flag=wx.LEFT | wx.GROW)
        sizer_bar.Add(sizer_right, border=5, flag=wx.ALL | wx.GROW)
        panel_editor.Sizer.Add(sizer_bar, proportion=1, flag=wx.GROW)

        # Create About-page
        label_about = frame.label_about = wx.html.HtmlWindow(panel_about)
        args = {"textcolour": ColourManager.ColourHex(wx.SYS_COLOUR_BTNTEXT),
                "linkcolour": ColourManager.ColourHex(wx.SYS_COLOUR_HOTLIGHT)}
        label_about.SetPage(conf.AboutText % args)
        ColourManager.Manage(label_about, "BackgroundColour", wx.SYS_COLOUR_BTNFACE)

        link_www = frame.link_www = wx.adv.HyperlinkCtrl(panel_about, label="github",
                                                         url=conf.HomeUrl)
        link_www.ToolTip = "Go to source code repository at %s" % conf.HomeUrl
        ColourManager.Manage(link_www, "HoverColour",      wx.SYS_COLOUR_HOTLIGHT)
        ColourManager.Manage(link_www, "NormalColour",     wx.SYS_COLOUR_HOTLIGHT)
        ColourManager.Manage(link_www, "VisitedColour",    wx.SYS_COLOUR_HOTLIGHT)
        text = wx.StaticText(panel_about,
            label="v%s, %s   " % (conf.Version, conf.VersionDate))
        ColourManager.Manage(text, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)

        sizer_footer = wx.BoxSizer(wx.HORIZONTAL)
        sizer_footer.Add(text)
        sizer_footer.AddStretchSpacer()
        sizer_footer.Add(link_www, border=5, flag=wx.RIGHT)
        panel_about.Sizer.Add(label_about, border=5, proportion=1, flag=wx.ALL | wx.GROW)
        panel_about.Sizer.Add(sizer_footer, border=5, flag=wx.LEFT | wx.GROW)

        panel_buttons = frame.panel_buttons = wx.Panel(panel)
        panel_buttons.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(panel_buttons, border=5, flag=wx.GROW | wx.ALL)
        frame.button_ok = wx.lib.agw.gradientbutton.GradientButton(
            panel_buttons, label="Minimize", size=(100, -1))
        frame.button_exit = wx.lib.agw.gradientbutton.GradientButton(
            panel_buttons, label="Exit program", size=(100, -1))
        for b in (frame.button_ok, frame.button_exit):
            bold_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
            bold_font.SetWeight(wx.BOLD)
            b.SetFont(bold_font)
            b.SetTopStartColour(wx.Colour(96, 96, 96))
            b.SetTopEndColour(wx.Colour(112, 112, 112))
            b.SetBottomStartColour(b.GetTopEndColour())
            b.SetBottomEndColour(wx.Colour(160, 160, 160))
            b.SetPressedTopColour(wx.Colour(160, 160, 160))
            b.SetPressedBottomColour(wx.Colour(160, 160, 160))
        frame.button_ok.SetDefault()
        frame.button_ok.SetToolTip("Minimize window to tray [Escape]")
        panel_buttons.Sizer.Add(frame.button_ok, border=5, flag=wx.TOP)
        panel_buttons.Sizer.AddStretchSpacer()
        panel_buttons.Sizer.Add(frame.button_exit, border=5, flag=wx.TOP)

        frame.Layout()

        x1, y1, x2, y2 = wx.GetClientDisplayRect() # Set in lower right corner
        frame.Position = (x2 - frame.Size.x, y2 - frame.Size.y)

        self.frame_console = wx.py.shell.ShellFrame(parent=frame,
          title=u"%s Console" % conf.Title, size=(800, 300)
        )
        self.frame_console.Bind(wx.EVT_CLOSE, lambda e: self.frame_console.Hide())

        icons = wx.IconBundle()
        icons.AddIcon(wx.Icon(wx.Bitmap(conf.WindowIcon)))
        frame.SetIcons(icons)
        frame.ToggleWindowStyle(wx.STAY_ON_TOP)
        panel_config.SetFocus()
        return frame



class ClockSelector(wx.Panel):
    """
    A 24h clock for selecting any number of periods from 24 hours,
    with a quarter hour step by default.

    Clicking and dragging with left or right button selects or deselects,
    double-clicking toggles an hour.
    """

    COLOUR_ON     = wx.Colour(241, 184, 45, 140)
    COLOUR_OFF    = wx.Colour(235, 236, 255)
    COLOUR_TEXT   = wx.BLACK
    COLOUR_LINES  = wx.BLACK
    COLOUR_TIME   = wx.RED
    RADIUS_CENTER = 20
    ANGLE_START   = math.pi / 2 # In polar coordinates

    def __init__(self, parent, id=-1, pos=wx.DefaultPosition,
                 size=(400, 400), style=0, name=wx.PanelNameStr,
                 selections=(0, )*24*4):
        """
        @param   selections  the selections to use, as [0,1,] for each time
                             unit in 24 hours. Length of selections determines
                             the minimum selectable step. Defaults to a quarter
                             hour step.
        """
        wx.Panel.__init__(self, parent, id, pos, size,
            style | wx.FULL_REPAINT_ON_RESIZE, name
        )

        self.BackgroundColour = ClockSelector.COLOUR_OFF
        self.ForegroundColour = ClockSelector.COLOUR_TEXT

        self.USE_GC        = True # Use GraphicsContext instead of DC
        self.buffer        = None # Bitmap buffer
        self.selections    = list(selections)
        self.sticky_value  = None # True|False|None if selecting|de-|nothing
        self.last_unit     = None # Last changed time unit
        self.penult_unit   = None # Last but one unit, to detect move backwards
        self.dragback_unit = None # Unit on a section edge dragged backwards
        self.sectors       = None # [(angle, radius, ptlist), ]
        self.hourlines     = None # [(x1, y1, x2, y2), ]
        self.hourtexts     = None # ["00", ]
        self.hourtext_pts  = None # [(x, y), ]
        self.notch_pts     = None # [(x1, y1, x2, y2), ]
        self.SetInitialSize(self.GetMinSize())
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.AcceptsFocus = self.AcceptsFocusFromKeyboard = lambda: False
        self.Bind(wx.EVT_SIZE,  self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseEvent)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.OnSysColourChange)
        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(milliseconds=1000 * 30) # Fire timer every 30 seconds


    def on_timer(self, event):
        if self.USE_GC: self.InitBuffer()
        self.Refresh()


    def OnSysColourChange(self, event):
        """Handler for system colour change, repaints control."""
        event.Skip()
        if self.USE_GC: self.InitBuffer()
        self.Refresh()


    def OnSize(self, event):
        """Size event handler, forces control back to rectangular size."""
        event.Skip()
        min_size = self.MinSize
        self.Size = max(min_size[0], min(self.Size)), max(min_size[1], min(self.Size))
        LENGTH = len(self.selections)
        self.sectors      = []
        self.hourlines    = []
        self.hourtexts    = []
        self.hourtext_pts = []
        self.notch_pts    = []
        last_line = None
        notch_pts = []
        radius = self.Size[0] / 2
        radius_linestart = radius / 2
        pt_center = radius, radius


        def polar_to_canvas(angle, radius, x=None, y=None):
            """
            Convert polar coordinates to canvas coordinates (in polar, zero
            point starts from the center - ordinary Cartesian system.
            On canvas, zero starts from top left and grows down and right.)

            @param   angle   polar angle where the x or y coordinate are at
            @param   radius  polar radius of the (x, y)
            @return          (x, y) or (x) or (y), depending on input arguments
            """
            xval, yval = None, None
            angle = (angle + 2 * math.pi) % (2 * math.pi)
            xval = None if x is None else x + radius
            yval = None if y is None else radius - y
            return yval if xval is None else (xval, yval) if yval else xval


        """
        All polar angles need - to map to graphics context.
        All (x,y) from polar coordinates need (-radius, +radius).
        -----------------------------------
        |                                 |
        |                                 |
        |                                 |
        |                                 |
        |                               --|
        |                          --     |
        |                     --          |
        |                o ---------------|
        |                                 |
        |                                 |
        |                                 |
        |                                 |
        |                                 |
        |                                 |
        |                                 |
        -----------------------------------
        """

        HOUR_RADIUS_RATIO = 6 / 8.
        textwidth, textheight = self.GetTextExtent("02")
        for i, text in enumerate(["%02d" % h for h in range(24)]):
            angle = ClockSelector.ANGLE_START - i * 2 * math.pi / 24. - (2 * math.pi / 48.)
            x_polar, y_polar = HOUR_RADIUS_RATIO * radius * math.cos(angle), HOUR_RADIUS_RATIO * radius * math.sin(angle)
            x, y = polar_to_canvas(angle, radius, x=x_polar, y=y_polar)
            x, y = x - textwidth / 2, y - textheight / 2
            alpha = math.pi / 2 - (angle - math.pi)
            radius_ray = radius / math.sin(alpha)
            self.hourtext_pts.append((x, y))
            self.hourtexts.append(text)

        for i in range(LENGTH):
            angle = math.pi + (2 * math.pi) / LENGTH * (i) + ClockSelector.ANGLE_START
            alpha = angle % (math.pi / 2) # force into 90deg
            alpha = alpha if alpha < math.pi / 4 else math.pi / 2 - alpha
            radius_ray = (radius - 1) / math.cos(alpha) if alpha else radius
            radius_start = radius_linestart
            if alpha == math.pi / 4: radius_ray -= 8
            if not i % 12: radius_start *= 0.8
            x1, y1 = radius_start * (math.cos(angle)) + radius, radius_start * (math.sin(angle)) + radius
            x2, y2 = radius_ray * (math.cos(angle)) + radius, radius_ray * (math.sin(angle)) + radius
            if not i % 4:
                self.hourlines.append((x1, y1, x2, y2))
            else:
                ptx1 = (radius_ray - (3 if i % 2 else 10)) * (math.cos(angle)) + radius
                pty1 = (radius_ray - (3 if i % 2 else 10)) * (math.sin(angle)) + radius
                notch_pts.append((ptx1, pty1, x2, y2))
            x1, y1 = pt_center
            if alpha == math.pi / 4:
                radius_ray += 8
                x2, y2 = radius_ray * (math.cos(angle)) + radius, radius_ray * (math.sin(angle)) + radius
            if last_line:
                self.sectors.append([(x1, y1), (x2, y2), last_line[1], last_line[0], ])
            last_line = ((x1, y1), (x2, y2))
        # Connect overflow
        self.sectors.append([last_line[0], last_line[1], self.sectors[0][2], self.sectors[0][3]  ])
        self.notch_pts = notch_pts
        if self.USE_GC: wx.CallAfter(self.InitBuffer)


    def SetSelections(self, selections):
        """Sets the currently selected time periods, as a list of 0/1."""
        refresh = (self.selections != selections)
        self.selections = selections[:]
        if refresh: self.Refresh()


    def GetSelections(self):
        """Returns the currently selected schedule as a list of 0/1."""
        return self.selections[:]


    def GetMinSize(self):
        """Returns the minimum needed size for the control."""
        return (100, 100)


    def OnPaint(self, event):
        """Handler for paint event, uses double buffering to reduce flicker."""
        if self.USE_GC: dc = wx.BufferedPaintDC(self, self.buffer)
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
        gc.SetPen(wx.Pen(ClockSelector.COLOUR_LINES, style=wx.TRANSPARENT))
        gc.SetBrush(wx.Brush(self.BackgroundColour, wx.SOLID))
        gc.DrawRoundedRectangle(0, 0, width - 1, height - 1, 18)

        # Draw and fill all selected sctors
        gc.SetPen(wx.Pen(ClockSelector.COLOUR_ON, style=wx.TRANSPARENT))
        gc.SetBrush(wx.Brush(ClockSelector.COLOUR_ON, wx.SOLID))
        for sect in (x for i, x in enumerate(self.sectors) if self.selections[i]):
            gc.DrawLines(sect)

        # Draw hour lines and smaller notches
        gc.SetPen(wx.Pen(ClockSelector.COLOUR_LINES, width=1))
        for x1, y1, x2, y2 in self.hourlines:
            gc.StrokeLines([(x1, y1), (x2, y2)])
        for x1, y1, x2, y2 in self.notch_pts:
            gc.StrokeLines([(x1, y1), (x2, y2)])

        # Draw hour texts
        gc.SetFont(gc.CreateFont(self.Font))
        textwidth, textheight = self.GetTextExtent("02")
        for i, text in enumerate(self.hourtexts):
            if width / 6 < 2.8 * textwidth and i % 2: continue # for i, text
            gc.DrawText(text, *self.hourtext_pts[i])

        # Draw current time
        tm = datetime.datetime.now().time()
        hours = tm.hour + tm.minute / 60.
        angle = (2 * math.pi / 24) * (hours) - ClockSelector.ANGLE_START
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
        gc.SetPen(wx.Pen(ClockSelector.COLOUR_TIME, style=wx.SOLID))
        gc.SetBrush(wx.Brush(ClockSelector.COLOUR_TIME, wx.SOLID))
        gc.StrokeLines([(x1, y1), (x2, y2)])

        # Draw center icon
        bmp = wx.Bitmap(conf.ClockIcon)
        stepx, stepy = (x / 2 for x in bmp.Size)
        gc.DrawBitmap(bmp, radius - stepx, radius - stepy, *bmp.Size)

        # Refill corners
        gc.SetPen(wx.Pen(self.Parent.BackgroundColour, style=wx.SOLID))
        gc.SetBrush(wx.Brush(self.Parent.BackgroundColour, wx.SOLID))
        CORNER_LINES = 18 - 7
        for i in range(4):
            x, y = 0 if i in [2, 3] else width - 1, 0 if i in [0, 3] else width - 1
            for j in range(CORNER_LINES, -1, -1):
                x1, y1 = x + (j if i in [2, 3] else -j), y
                x2, y2 = x1, y1 + (CORNER_LINES - j) * (1 if i in [0, 3] else -1)
                gc.StrokeLines([(x1, y1), (x2, y2)])

        gc.SetPen(wx.Pen(ClockSelector.COLOUR_LINES))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRoundedRectangle(0, 0, width - 1, height - 1, 18)



    def DrawDC(self, dc):
        """Draws the custom selector control using a DC."""
        width, height = self.Size
        if not width or not height: return

        dc.BackgroundColour = self.Parent.BackgroundColour
        dc.Clear()

        # Draw outer border
        dc.Pen = wx.Pen(ClockSelector.COLOUR_LINES)
        dc.Brush = wx.Brush(self.BackgroundColour, wx.SOLID)
        dc.DrawRoundedRectangle(0, 0, width, height, 8)

        # Draw highlighted sectors
        dc.Pen = wx.TRANSPARENT_PEN
        dc.Brush = wx.Brush(ClockSelector.COLOUR_ON, wx.SOLID)
        for sect in (x for i, x in enumerate(self.sectors) if self.selections[i]):
            dc.DrawPolygon(sect)

        # Draw hour lines and write hours
        dc.Pen = wx.Pen(ClockSelector.COLOUR_LINES, width=1)
        dc.DrawLineList(self.hourlines)
        dc.TextForeground = ClockSelector.COLOUR_TEXT
        dc.Font = self.Font
        dc.DrawTextList(self.hourtexts, self.hourtext_pts)

        # Draw center icon
        bmp = wx.Bitmap(conf.ClockIcon)
        stepx, stepy = (x / 2 for x in bmp.Size)
        radius = width / 2
        dc.DrawBitmap(bmp, radius - stepx, radius - stepy)


    def OnMouseEvent(self, event):
        """Handler for any and all mouse actions in the control."""
        if not self.Enabled or not self.sectors: return


        def point_in_polygon(point, polypoints):
            """Returns whether point is inside a polygon."""
            result = False 
            if len(polypoints) < 3 or len(point) < 2: return result

            polygon = [map(float, p) for p in polypoints]
            (x, y), (x2, y2) = map(float, point), polygon[-1]
            for x1, y1 in polygon:
                if (y1 <= y and y < y2 or y2 <= y and y < y1) \
                and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    result = not result
                x2, y2 = x1, y1
            return result


        center = [self.Size.width / 2] * 2
        unit, x, y = None, event.Position.x, event.Position.y
        dist_center = ((center[0] - x) ** 2 + (center[1] - y) ** 2) ** 0.5
        if dist_center < ClockSelector.RADIUS_CENTER:
            self.penult_unit = self.last_unit = None
        else:
            for i, sector in enumerate(self.sectors):
                if point_in_polygon((x, y), sector):
                    unit = i
                    break # for i, sector

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
        elif event.LeftDClick() or event.RightDClick():
            # Toggle an entire hour on double-click
            if unit is not None:
                steps = len(self.selections) / 24
                low, hi = unit - unit % steps, unit - unit % steps + steps
                units = self.selections[low:hi]
                 # Toggle hour off on left-dclick only if all set
                value = 0 if event.RightDClick() else int(not all(units))
                self.selections[low:hi] = [value] * len(units)
                refresh = (units != self.selections[low:hi])
        elif event.LeftUp() or event.RightUp():
            if self.HasCapture(): self.ReleaseMouse()
            self.last_unit,   self.sticky_value  = None, None
            self.penult_unit, self.dragback_unit = None, None
        elif event.Dragging():
            if self.sticky_value is not None and unit != self.last_unit \
            and 0 <= unit < len(self.selections):
                LENGTH = len(self.selections)
                STARTS = range(2)
                ENDS = range(LENGTH - 2, LENGTH)
                def is_overflow(a, b):
                    return (a in STARTS and b in ENDS) or (a in ENDS and b in STARTS)
                def get_direction(a, b):
                    result = 1 if b > a else -1
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
        if refresh:
            self.InitBuffer()
            self.Refresh()
            event = TimeSelectorEvent()
            wx.PostEvent(self.TopLevelParent.EventHandler, event)



class StartupService(object):
    """
    Manages starting program on system startup, if possible. Currently
    supports only Windows.
    """

    @classmethod
    def can_start(cls):
        """Whether startup can be set on this system at all."""
        return ("win32" == sys.platform)

    @classmethod
    def is_started(cls):
        """Whether program is in startup."""
        return os.path.exists(cls.get_shortcut_path_windows())

    @classmethod
    def start(cls):
        """Sets program to run at system startup."""
        shortcut_path = cls.get_shortcut_path_windows()
        target_path = conf.ApplicationPath
        workdir, icon = conf.ApplicationDirectory, conf.ShortcutIconPath
        cls.create_shortcut_windows(shortcut_path, target_path, workdir, icon)

    @classmethod
    def stop(cls):
        """Stops program from running at system startup."""
        try: os.unlink(cls.get_shortcut_path_windows())
        except Exception: pass

    @classmethod
    def get_shortcut_path_windows(cls):
        path = "~\\Start Menu\\Programs\\Startup\\%s.lnk" % conf.Title
        return os.path.expanduser(path)

    @classmethod
    def create_shortcut_windows(cls, path, target="", workdir="", icon=""):
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
                shortcut.Targetpath = '"%s"' % python
                shortcut.Arguments = '"%s" %s' % (target, conf.StartMinimizedParameter)
            else:
                shortcut.Targetpath = target
                shortcut.Arguments = conf.StartMinimizedParameter
            shortcut.WorkingDirectory = workdir
            if icon: shortcut.IconLocation = icon
            shortcut.save()



class ThemeComboBox(wx.adv.OwnerDrawnComboBox):
    """Dropdown combobox for showing colour themes."""

    COLOUR_NAME = "#7D7D7D"


    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, choices=(), selected=None,
                 bitmapsize=wx.DefaultSize, style=0, name=""):
        """
        @param   choices  [(name, [theme]), ]
        """
        wx.adv.OwnerDrawnComboBox.__init__(self, parent, id=id, 
            pos=pos, size=size, choices=map(str, range(len(choices))), 
            style=style, name=name)
        self._themes = list(choices)
        w, h = bitmapsize[0], bitmapsize[1] + 15 # Room for name
        self._bitmapsize = wx.Size(w, h)
        thumbsz, bordersz = self.GetButtonSize(), self.GetWindowBorderSize()
        self.MinSize = w + bordersz[0] + thumbsz[0] + 3, h + bordersz[1]
        self.Font = wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                            wx.FONTWEIGHT_BOLD, faceName="Arial")
        if choices: self.Selection = 0 if selected is None else selected


    def OnDrawItem(self, dc, rect, item, flags):
        if item == wx.NOT_FOUND:
            return # Painting the control, but no valid item selected yet

        name, theme = self._themes[item]
        bmp = get_theme_bitmap(theme)

        dc.SetBackground(wx.Brush(ColourManager.GetColour(wx.SYS_COLOUR_WINDOW)))
        dc.Clear()

        dc_bmp = wx.MemoryDC(bmp)
        w, h = bmp.Size
        dc.Blit(rect.x + 1, rect.y + 1, w + 1, h, dc_bmp, 0, 0)

        dc.SetTextForeground(self.COLOUR_NAME)
        dc.SetFont(self.Font)
        text = text0 = name
        (tw, th), cut = dc.GetTextExtent(text), 0
        while tw > w:
            cut += 1
            text = ".." + text0[cut:]
            tw, th = dc.GetTextExtent(text)
        dc.DrawText(text, rect.x + (w - tw) / 2, rect.y + h)


    def GetItemName(self, index):
        """Returns the name of colour theme at index."""
        return self._themes[index][0]


    def GetItemData(self, index):
        """Returns the name and colour theme at index."""
        return copy.deepcopy(self._themes[index])


    def FindIndex(self, name=None, theme=None):
        """Returns item index for the specified name or theme."""
        for i in range(self.GetCount()):
            thumb_name, thumb_theme = self._themes[i]
            if name   is not None and thumb_name  == name \
            or theme  is not None and thumb_theme == theme:
                return i
        return -1


    def Insert(self, item, pos):
        """Inserts an item at position."""
        pos = min(pos, len(self._themes)) % len(self._themes)
        self._themes.insert(pos, item)
        super(ThemeComboBox, self).Insert(str(len(self._themes)), pos)


    def ReplaceItem(self, item, pos):
        """Replaces item content at position."""
        if not self._themes: return
        pos = min(pos, len(self._themes)) % len(self._themes)
        self._themes[pos] = item


    def SetItems(self, items):
        """Replaces all items in control."""
        self._themes = list(items)
        return super(ThemeComboBox, self).SetItems(map(str, range(len(items))))


    def Delete(self, n):
        """Deletes the item with specified index."""
        if not self._themes or n >= len(self._themes): return
        if n < 0: n %= len(self._themes)
        super(ThemeComboBox, self).Delete(n)
        del self._themes[n]
        self.Select(min(n, len(self._themes) - 1))


    def Select(self, n):
        """Selects item with specified index."""
        return self.SetSelection(n)


    def SetSelection(self, n):
        """Selects item with specified index."""
        result = super(ThemeComboBox, self).SetSelection(n)
        if n < len(self._themes):
            self.ToolTip = get_theme_str(self._themes[n][1])
        return result
    Selection = property(wx.adv.OwnerDrawnComboBox.GetSelection, SetSelection)


    def OnDrawBackground(self, dc, rect, item, flags):
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
        return self._bitmapsize.height + 2


    def OnMeasureItemWidth(self, item):
        """OwnerDrawnComboBox override, returns item width."""
        return self._bitmapsize.width + 2



class BitmapListHandler(wx.lib.agw.thumbnailctrl.NativeImageHandler):
    """
    Image loader for wx.lib.agw.thumbnailctrl.ThumbnailCtrl using
    pre-loaded bitmaps.
    """
    _bitmaps = {} # {name: wx.Bitmap, }
    _themes = {}  # {name: [theme], }


    @classmethod
    def RegisterBitmap(cls, name, bitmap, theme):
        cls._bitmaps[name], cls._themes[name] = bitmap, theme


    @classmethod
    def UnregisterBitmap(cls, name):
        cls._bitmaps.pop(name, None)
        cls._themes .pop(name, None)


    @classmethod
    def GetTheme(cls, name):
        return cls._themes[name]


    def LoadThumbnail(self, filename, thumbnailsize):
        """Load the image, return (wx.Image, (w, h), hasAlpha)."""
        img = self._bitmaps[os.path.basename(filename)].ConvertToImage()
        originalsize, alpha = (img.GetWidth(), img.GetHeight()), img.HasAlpha()
        return img, originalsize, alpha



class BitmapListCtrl(wx.lib.agw.thumbnailctrl.ThumbnailCtrl):
    """A ThumbnailCtrl that can simply show bitmaps, with files not on disk."""

    def __init__(self, parent, id=wx.ID_ANY, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, bitmapsize=wx.DefaultSize,
                 thumboutline=wx.lib.agw.thumbnailctrl.THUMB_OUTLINE_FULL,
                 thumbfilter=wx.lib.agw.thumbnailctrl.THUMB_FILTER_IMAGES,
                 imagehandler=BitmapListHandler):
        wx.lib.agw.thumbnailctrl.ThumbnailCtrl.__init__(self, parent, id, pos,
            size, thumboutline, thumbfilter, imagehandler
        )
        self.EnableDragging(False)
        self.EnableToolTips(True)
        self.SetDropShadow(False)
        self.ShowFileNames(True)
        self.SetThumbSize(bitmapsize[0], bitmapsize[1], border=5)

        # Hack to get around ThumbnailCtrl's internal monkey-patching
        setattr(self._scrolled, "GetThumbInfo", getattr(self, "_GetThumbInfo"))

        self._scrolled.Bind(wx.EVT_CHAR, None) # Disable rotation/deletion/etc
        self._scrolled.Bind(wx.EVT_MOUSEWHEEL, None) # Disable zoom
        self._scrolled.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_SEL_CHANGED,
                            self.OnSelectionChanged)
        ColourManager.Manage(self._scrolled, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def OnSelectionChanged(self, event):
        # Disable ThumbnailCtrl's multiple selection
        self._scrolled._selectedarray[:] = [self.GetSelection()]
        event.Skip()


    def RegisterBitmap(self, filename, bitmap, theme):
        BitmapListHandler.RegisterBitmap(filename, bitmap, theme)


    def UnregisterBitmap(self, filename):
        BitmapListHandler.UnregisterBitmap(filename)


    def GetItemName(self, index):
        """Returns the theme name for the specified index."""
        thumb = self.GetItem(index)
        if thumb: return thumb.GetFileName()


    def GetItemData(self, index):
        """Returns (name, theme) for the specified index."""
        thumb = self.GetItem(index)
        if thumb:
            return thumb.GetFileName(), BitmapListHandler.GetTheme(thumb.GetFileName())


    def FindIndex(self, name=None, theme=None):
        """Returns item index for the specified name or theme."""
        for i in range(self.GetItemCount()):
            thumb_name = self.GetItem(i).GetFileName()
            if name is not None and thumb_name == name \
            or theme is not None \
            and BitmapListHandler.GetTheme(thumb_name) == theme:
                return i
        return -1


    def _GetThumbInfo(self, index=-1):
        """Returns the thumbnail information for the specified index."""
        thumb = self.GetItem(index)
        if thumb:
            return get_theme_str(BitmapListHandler.GetTheme(thumb.GetFileName()))



class ColourManager(object):
    """
    Updates managed component colours on Windows system colour change.
    """
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
        return wx.Colour(colour)  if isinstance(colour, basestring)    else \
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



def get_theme_bitmap(theme, supported=True, border=False):
    """
    Returns a wx.Bitmap for the specified theme, with colour and brightness
    information as both text and visual.
    
    @param   supported  whether the theme is supported by hardware
    @param   border     whether to draw border around bitmap
    """
    bmp = wx.Bitmap(*conf.ThemeBitmapSize)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(*theme[:-1])))
    dc.Clear() # Floodfill background with theme colour

    btext = "%d%%" % math.ceil(100 * (theme[-1] + 1) / conf.NormalBrightness)
    dc.SetFont(wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_BOLD, faceName="Tahoma"))
    twidth, theight = dc.GetTextExtent(btext)
    ystart = (bmp.Size.height - theight) / 2 - 4

    # Draw brightness text shadow (dark text shifted +-1px in each direction)
    dc.SetTextForeground(wx.BLACK)
    for dx, dy in [(-1, 0), (-1, 1), (1, 0), (1, 1), (1, -1), (-1, -1)]:
        dc.DrawText(btext, (bmp.Size.width - twidth) / 2 + dx, ystart + dy)
        
    # Draw brightness text
    dc.SetTextForeground(wx.WHITE)
    dc.DrawText(btext, (bmp.Size.width - twidth) / 2, ystart)

    # Draw colour code on white background
    dc.SetFont(wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_BOLD, faceName="Terminal"))
    ctext = "#%2X%2X%2X" % tuple(theme[:-1])
    cwidth, cheight = dc.GetTextExtent(ctext)
    dc.SetBrush(wx.WHITE_BRUSH)
    dc.SetPen(wx.WHITE_PEN)
    dc.DrawRectangle(0, bmp.Size[1] - cheight - 3, *bmp.Size)
    dc.SetPen(wx.LIGHT_GREY_PEN) # Draw separator above colour code
    dc.DrawLine(0, bmp.Size[1] - cheight - 3, bmp.Size[0], bmp.Size[1] - cheight - 3)
    dc.SetTextForeground(wx.BLACK if supported else wx.RED)
    dc.DrawText(ctext, (bmp.Size[0] - cwidth) / 2 - 1, bmp.Size[1] - cheight - 1)

    if border: # Draw outer border
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.LIGHT_GREY_PEN)
        dc.DrawRectangle(0, 0, *bmp.Size)

    if not supported: # Draw unsupported cross-through
        dc.SetPen(wx.RED_PEN)
        dc.DrawLine(0, 0, bmp.Size.width, bmp.Size.height)
        dc.DrawLine(0, bmp.Size.height, bmp.Size.width, 0)

    del dc
    return bmp


def get_theme_str(theme, supported=True, short=False):
    """Returns a readable string representation of the theme."""
    btext = "%d%%" % math.ceil(100 * (theme[-1] + 1) / conf.NormalBrightness)
    if short:
        result = "%s #%2X%2X%2X" % ((btext, ) + tuple(theme[:3]))
    else:
        result = "%s brightness.\n%s" % (btext,
                 ", ".join("%s at %d%%" % (s, theme[i] / 255. * 100)
                           for i, s in enumerate(("Red", "green", "blue"))))
        if not supported:
            result += "\n\nNot supported by hardware."
    return result


def get_colour_bitmap(colour, size=(16, 16)):
    """Returns a wx.Bitmap full of specified colour."""
    bmp = wx.Bitmap(*size)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.BLACK_BRUSH)
    dc.Clear()

    dc.Brush, dc.Pen = wx.Brush(colour), wx.Pen(colour)
    dc.DrawRectangle(1, 1, size[0] - 2, size[1] - 2)

    pts = (1, 1), (1, size[1] - 2), (size[0] - 2, 1), (size[0] - 2, size[1] - 2)
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawPointList(pts)

    del dc
    bmp.SetMaskColour(wx.BLACK)
    return bmp



if __name__ == '__main__':
    warnings.simplefilter("ignore", UnicodeWarning)
    app = NightFall(redirect=0) # stdout and stderr redirected to wx popup
    locale = wx.Locale(wx.LANGUAGE_ENGLISH) # Avoid dialog buttons in native language
    app.MainLoop()
