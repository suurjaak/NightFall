#-*- coding: utf-8 -*-
"""
A tray application that can make screen colors darker and softer during
nocturnal hours, can activate on schedule.

@author      Erki Suurjaak
@created     15.10.2012
@modified    14.09.2020
"""
import collections
import copy
import datetime
import functools
import math
import os
import re
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
    """
    Model handling current screen gamma state and configuration.

    Notification events posted:

    MANUAL TOGGLED      manual dimming state has changed               data=enabled
    MANUAL IN EFFECT    dimming has been applied manually              data=theme
    NORMAL DISPLAY      dimming has been unapplied                     data=normaltheme
    SCHEDULE TOGGLED    schedule applied-state has changed             data=enabled
    SCHEDULE CHANGED    schedule contents have changed                 data=schedule
    SCHEDULE IN EFFECT  dimming has been applied on schedule           data=theme
    SUSPEND TOGGLED     suspended state has changed                    data=enabled
    STARTUP POSSIBLE    can program be added to system startup         data=enabled
    STARTUP TOGGLED     running program at system startup has changed  data=enabled
    THEME CHANGED       dimming theme has changed                      data=theme
    THEME APPLIED       dimming fade step have been completed          data=targettheme
    THEME STEPPED       dimming fade step has been applied             data=steppedtheme
    """


    def __init__(self, event_handler):
        self.handler = event_handler

        conf.load()
        self.validate_conf()

        self.current_theme = copy.copy(conf.NormalTheme) # Applied colour theme
        self.fade_timer = None # wx.Timer instance for applying fading
        self.fade_steps = None # Number of steps to take during a fade
        self.fade_delta = None # Delta to add to theme components on fade step
        self.fade_target_theme   = None # Final theme values during fade
        self.fade_current_theme  = None # Theme float values during fade
        self.fade_original_theme = None # Original theme before applying fade

        self.timer = wx.Timer()
        self.timer.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        # Ensure timer tick is immediately after start of minute
        now = datetime.datetime.now()
        delta = conf.TimerInterval - now.second % conf.TimerInterval + 1
        wx.CallLater(1000 * delta, self.timer.Start, 1000 * conf.TimerInterval)


    def validate_conf(self):
        """Sanity-checks configuration loaded from file."""

        def is_theme_valid(theme):
            if not isinstance(theme, (list, tuple)) \
            or len(theme) != len(conf.NormalTheme): return False
            for g in theme[:-1]:
                if not isinstance(g, (int, float)) \
                or not (conf.ValidColourRange[0] <= g <= conf.ValidColourRange[-1]):
                    return False
            return 0 <= theme[-1] <= 255

        def is_var_valid(name):
            v, v0 = getattr(conf, name), conf.Defaults[name]
            return (len(v) == len(v0)
                    and all(isinstance(a, type(b)) for a, b in zip(v, v0))) \
                   if isinstance(v, (list, tuple)) and isinstance(v0, (list, tuple)) \
                   else (isinstance(v, type(v0))
                         or isinstance(v, basestring) and isinstance(v0, basestring))

        if not is_theme_valid(conf.UnsavedTheme):
            conf.UnsavedTheme = None
        if not isinstance(conf.Themes, dict):
            conf.Themes = copy.deepcopy(conf.Defaults["Themes"])
        for name, theme in conf.Themes.items():
            if not name or not is_theme_valid(theme): conf.Themes.pop(name)
        if conf.ThemeName is not None and conf.ThemeName not in conf.Themes:
            conf.ThemeName = None
        if not conf.UnsavedTheme and not conf.ThemeName and conf.Themes:
            conf.ThemeName = sorted(conf.Themes, key=lambda x: x.lower())[0]
        if not conf.UnsavedTheme and not conf.Themes:
            conf.UnsavedTheme = conf.Defaults["Themes"][conf.Defaults["ThemeName"]]
        if conf.UnsavedTheme:
            name = next((k for k, v in conf.Themes.items()
                         if v == conf.UnsavedTheme), None)
            if name:
                conf.UnsavedTheme = None
                if not conf.ThemeName: conf.ThemeName = name
        conf.ScheduleEnabled = bool(conf.ScheduleEnabled)
        conf.ManualEnabled   = bool(conf.ManualEnabled)
        for n in (x for x in conf.OptionalFileDirectives if x != "UnsavedTheme"):
            if not is_var_valid(n): setattr(conf, n, conf.Defaults[n])

        if not isinstance(conf.Schedule, list) \
        or len(conf.Schedule) != len(conf.DefaultSchedule):
            conf.Schedule = conf.DefaultSchedule[:]
        for i, g in enumerate(conf.Schedule):
            if g not in [True, False]: conf.Schedule[i] = conf.DefaultSchedule[i]
        conf.StartupEnabled = StartupService.is_started()
        conf.save()


    def start(self):
        """Starts handler: updates GUI settings, and dims if so configured."""
        theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
        self.post_event("THEME CHANGED",    theme)
        self.post_event("MANUAL TOGGLED",   conf.ManualEnabled)
        self.post_event("SCHEDULE CHANGED", conf.Schedule)
        self.post_event("SCHEDULE TOGGLED", conf.ScheduleEnabled)
        self.post_event("STARTUP POSSIBLE", StartupService.can_start())
        self.post_event("STARTUP TOGGLED",  conf.StartupEnabled)
        if self.should_dim():
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() else \
                  "MANUAL IN EFFECT"
            self.post_event(msg, theme)
            self.apply_theme(theme, fade=True)
        else:
            self.apply_theme(conf.NormalTheme)


    def stop(self):
        """Stops timers and any current dimming."""
        self.timer.Stop()
        if self.fade_timer: self.fade_timer.Stop()
        self.fade_timer = None
        self.apply_theme(conf.NormalTheme)


    def post_event(self, topic, data=None):
        """Sends a message event to the event handler."""
        if not self.handler: return
        event = DimmerEvent(Topic=topic, Data=data)
        wx.PostEvent(self.handler, event)


    def on_timer(self, event):
        """
        Handler for a timer tick, checks whether to apply/unapply theme
        according to schedule, or whether theme should no longer be suspended.
        """
        if conf.SuspendedUntil and (not self.should_dim() 
        or conf.SuspendedUntil <= datetime.datetime.now()):
            conf.SuspendedUntil = None
            self.post_event("SUSPEND TOGGLED", False)
        theme, msg = conf.NormalTheme, "NORMAL DISPLAY"
        if self.should_dim() and not conf.SuspendedUntil:
            theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() else \
                  "MANUAL IN EFFECT"
        if theme != self.current_theme:
            self.apply_theme(theme, fade=True)
            self.post_event(msg)


    def toggle_manual(self, enabled):
        """Toggles manual dimming on/off."""
        enabled = bool(enabled)
        changed = (conf.ManualEnabled != enabled)

        if not enabled and conf.SuspendedUntil and not self.should_dim_scheduled():
            conf.SuspendedUntil = None
            self.post_event("SUSPEND TOGGLED", False)
        conf.ManualEnabled = enabled
        if changed: conf.save()
        self.post_event("MANUAL TOGGLED", conf.ManualEnabled)
        if conf.SuspendedUntil: return

        theme = conf.NormalTheme
        if self.should_dim():
            theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
        self.apply_theme(theme, fade=True)
        if changed and conf.ManualEnabled:
            self.post_event("MANUAL IN EFFECT", theme)


    def toggle_schedule(self, enabled):
        """Toggles the scheduled dimming on/off."""
        enabled = bool(enabled)
        changed = (enabled != conf.ScheduleEnabled)
        if not changed: return

        if not enabled and conf.SuspendedUntil and not conf.ManualEnabled:
            conf.SuspendedUntil = None
            self.post_event("SUSPEND TOGGLED", False)
        conf.ScheduleEnabled = enabled
        self.post_event("SCHEDULE TOGGLED", conf.ScheduleEnabled)
        conf.save()
        if conf.SuspendedUntil: return

        theme, msg = conf.NormalTheme, "NORMAL DISPLAY"
        if self.should_dim():
            theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() else \
                  "MANUAL IN EFFECT"
        self.apply_theme(theme, fade=True)
        self.post_event(msg, theme)


    def toggle_startup(self, enabled):
        """Toggles running program on system startup."""
        enabled = bool(enabled)
        if StartupService.can_start():
            conf.StartupEnabled = enabled
            conf.save()
            StartupService.start() if enabled else StartupService.stop()
            self.post_event("STARTUP TOGGLED", conf.StartupEnabled)


    def toggle_suspend(self, enabled):
        """Toggles theme postponement on/off."""
        enabled = bool(enabled)
        changed = (enabled != bool(conf.SuspendedUntil))
        if not changed or not self.should_dim(): return

        if enabled:
            delay = datetime.timedelta(minutes=conf.DefaultSuspendInterval)
            start = (datetime.datetime.now() + delay).replace(second=0, microsecond=0)
            msg, theme = "NORMAL DISPLAY", conf.NormalTheme
        else:
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() else \
                  "MANUAL IN EFFECT"
            start, theme = None, conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
        conf.SuspendedUntil = start
        self.post_event("SUSPEND TOGGLED", enabled)
        self.apply_theme(theme, fade=True)
        self.post_event(msg, theme)


    def apply_theme(self, theme, fade=False):
        """
        Applies the specified colour theme.

        @param   fade   if True, changes theme from current to new smoothly,
                        in a number of steps
        @return         False on immediate failure, True otherwise
        """
        result = True
        if self.fade_timer:
            self.fade_timer.Stop()
            self.fade_target_theme = None
            self.fade_delta = self.fade_steps = self.fade_timer = None
            self.fade_current_theme = self.fade_original_theme = None

        if ThemeImaging.IsSupported(theme) == False:
            result = False
        elif conf.FadeSteps > 0 and fade and theme != self.current_theme:
            self.fade_steps = conf.FadeSteps
            self.fade_target_theme = theme[:]
            self.fade_current_theme = map(float, self.current_theme)
            self.fade_original_theme = self.current_theme[:]
            self.fade_delta = []
            for new, now in zip(theme, self.current_theme):
                self.fade_delta.append(float(new - now) / conf.FadeSteps)
            self.fade_timer = wx.CallLater(conf.FadeDelay, self.on_fade_step)
        else:
            result = gamma.set_screen_gamma(theme)
            self.current_theme = theme[:]
            ThemeImaging.MarkSupported(theme, result)

        if not result:
            self.post_event("THEME FAILED", theme)
            # Unsupported theme: jump back to normal if not fading
            if not self.fade_target_theme: self.apply_theme(conf.NormalTheme)
        return result


    def set_schedule(self, schedule):
        """
        Sets the current screen dimming schedule, and applies it if suitable.

        @param   selections  selected times, [1,0,..] per each quarter hour
        """
        changed = (schedule != conf.Schedule)
        if not changed: return

        did_dim_scheduled = self.should_dim_scheduled()
        conf.Schedule = schedule[:]
        if conf.SuspendedUntil and did_dim_scheduled \
        and not conf.ManualEnabled and not self.should_dim_scheduled():
            conf.SuspendedUntil = None
            self.post_event("SUSPEND TOGGLED", False)
        conf.save()
        self.post_event("SCHEDULE CHANGED", conf.Schedule)
        if conf.SuspendedUntil \
        or did_dim_scheduled and self.should_dim_scheduled(): return

        theme, msg = conf.NormalTheme, "NORMAL DISPLAY"
        if self.should_dim():
            theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
            msg = "SCHEDULE IN EFFECT" if self.should_dim_scheduled() else \
                  "MANUAL IN EFFECT"
        self.apply_theme(theme, fade=True)
        self.post_event(msg, theme)


    def set_theme(self, theme, fade=False):
        """
        Sets the screen dimming theme, and applies it if enabled.

        @param   theme  a 4-byte list, for 3 RGB channels and brightness, 0..255
        @param   fade   if True, changes theme from current to new smoothly,
                        in a number of steps
        """
        changed = (theme != self.current_theme)
        if changed:
            self.post_event("THEME CHANGED", theme)
            if self.should_dim() and not conf.SuspendedUntil:
                self.apply_theme(theme, fade=fade)
        conf.save()


    def should_dim(self):
        """
        Returns whether dimming should currently be applied, based on global
        enabled flag and enabled time selection. Disregards suspended state.
        """
        return conf.ManualEnabled or self.should_dim_scheduled()


    def should_dim_scheduled(self, flag=False):
        """
        Whether dimming should currently be on, according to schedule.
        Disregards suspended state. If flag, ignores ScheduleEnabled.
        """
        result = False
        if conf.ScheduleEnabled or flag:
            t = datetime.datetime.now().time()
            H_MUL = len(conf.Schedule) / 24
            M_DIV = 60 / H_MUL
            result = bool(conf.Schedule[t.hour * H_MUL + t.minute / M_DIV])
        return result


    def on_fade_step(self):
        """
        Handler for a fade step, applies the fade delta to colour theme and
        schedules another event, if more steps left.
        """
        self.fade_timer = None
        if not self.fade_steps: return

        self.fade_current_theme = [(current + delta) for current, delta
            in zip(self.fade_current_theme, self.fade_delta)]
        self.fade_steps -= 1
        if not self.fade_steps:
            # Final step: use exact given target, to avoid rounding errors
            current_theme = self.fade_target_theme
        else:
            current_theme = map(int, map(round, self.fade_current_theme))
        success = self.apply_theme(current_theme)
        if success:
            msg = "THEME STEPPED" if self.fade_steps else "THEME APPLIED"
            theme = current_theme if self.fade_steps else self.fade_target_theme
            self.post_event(msg, theme)
        elif not self.fade_steps:
            # Unsupported theme: jump back to normal on last step.
            self.apply_theme(conf.NormalTheme)
            self.current_theme = current_theme[:]
        if self.fade_steps:
            self.fade_timer = wx.CallLater(conf.FadeDelay, self.on_fade_step)
        else:
            self.fade_target_theme = None
            self.fade_delta = self.fade_steps = None
            self.fade_current_theme = self.fade_original_theme = None



class NightFall(wx.App):
    """
    The NightFall application, controller managing the GUI elements 
    and communication with the dimmer model.
    """


    def __init__(self, redirect=False, filename=None,
                 useBestVisual=False, clearSigInt=True):
        super(NightFall, self).__init__(redirect, filename, useBestVisual, clearSigInt)
        self.dimmer = Dimmer(self)

        self.frame_hider    = None # wx.CallLater object for timed hiding on blur
        self.frame_shower   = None # wx.CallLater object for timed showing on slideout
        self.frame_pos_orig = None # Position of frame before slidein
        self.frame_unmoved  = True # Whether user has moved the window
        self.frame_move_ignore = False # Ignore EVT_MOVE on showing window
        self.frame_has_modal   = False # Whether a modal dialog is open
        self.dt_tray_click     = None  # Last click timestamp, for detecting double-click
        self.suspend_interval  = None  # Currently selected suspend interval
        self.skip_notification = False # Skip next tray notification message
        self.frame = frame = self.create_frame()

        frame.Bind(wx.EVT_CHECKBOX, self.on_toggle_schedule, frame.cb_schedule)
        frame.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_SEL_CHANGED,
            self.on_select_list_themes, frame.list_themes)
        frame.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_DCLICK,
            self.on_apply_list_themes, frame.list_themes)
        frame.Bind(wx.EVT_LIST_DELETE_ITEM, self.on_delete_theme, frame.list_themes)

        ColourManager.Init(frame)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_manual,       frame.cb_manual)
        frame.Bind(wx.EVT_CHECKBOX,   self.on_toggle_startup,      frame.cb_startup)
        frame.Bind(wx.EVT_BUTTON,     self.on_toggle_settings,     frame.button_ok)
        frame.Bind(wx.EVT_BUTTON,     self.on_exit,                frame.button_exit)
        frame.Bind(wx.EVT_BUTTON,     self.on_apply_list_themes,   frame.button_apply)
        frame.Bind(wx.EVT_BUTTON,     self.on_restore_themes,      frame.button_restore)
        frame.Bind(wx.EVT_BUTTON,     self.on_delete_theme,        frame.button_delete)
        frame.Bind(wx.EVT_BUTTON,     self.on_save_theme,          frame.button_save)
        frame.Bind(wx.EVT_BUTTON,     self.on_reset_theme,         frame.button_reset)
        frame.Bind(wx.EVT_BUTTON,     self.on_toggle_suspend,      frame.button_suspend)
        frame.Bind(wx.EVT_COMBOBOX,   self.on_select_combo_themes, frame.combo_themes)
        frame.Bind(wx.EVT_COMBOBOX,   self.on_select_combo_editor, frame.combo_editor)
        frame.label_suspend.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.on_change_suspend)
        frame.link_www.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                            lambda e: webbrowser.open(e.GetLinkInfo().Href))
        frame.label_about.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                            lambda e: webbrowser.open(e.GetLinkInfo().Href))

        frame.Bind(EVT_TIME_SELECTOR, self.on_change_schedule)
        frame.Bind(wx.EVT_CLOSE,      self.on_toggle_settings)
        frame.Bind(wx.EVT_ACTIVATE,   self.on_activate_window)
        frame.Bind(wx.EVT_MOVE,       self.on_move)
        frame.Bind(wx.EVT_CHAR_HOOK,  self.on_key)
        frame.Bind(wx.EVT_SYS_COLOUR_CHANGED, self.on_sys_colour_change)
        for s in frame.sliders:
            frame.Bind(wx.EVT_SCROLL, self.on_change_theme_slider, s)
            frame.Bind(wx.EVT_SLIDER, self.on_change_theme_slider, s)
        self.Bind(EVT_DIMMER,         self.on_dimmer_event)
        self.Bind(wx.EVT_LEFT_DCLICK, self.on_toggle_console, frame.label_combo)

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

        self.populate()
        frame.notebook.SetSelection(1); frame.notebook.SetSelection(0) # Layout hack
        ThemeImaging.AddControls(frame.combo_themes, frame.list_themes,
                                 frame.combo_editor)
        self.dimmer.start()
        if conf.StartMinimizedParameter not in sys.argv:
            self.frame_move_ignore = True # Skip first move event on Show()
            frame.Show()


    def on_dimmer_event(self, event):
        """Handler for all events sent from Dimmer, updates UI state."""
        topic, data = event.Topic, event.Data
        if "THEME FAILED" == topic:
            theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
            ThemeImaging.Add(conf.ThemeName or self.unsaved_name(), theme)
            self.frame.combo_themes.ToolTip = ThemeImaging.Repr(theme)
            if not conf.ThemeName or conf.ThemeName == conf.UnsavedName:
                self.frame.combo_editor.ToolTip = self.frame.combo_themes.ToolTip

            self.frame.label_error.Label = "Setting unsupported by hardware."
            self.frame.label_error.Show()
            self.frame.label_error.ContainingSizer.Layout()
            self.frame.label_error.Wrap(self.frame.label_error.Size[0])
        elif "MANUAL TOGGLED" == topic:
            self.frame.cb_manual.Value = data
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
            self.update_suspend()
        elif "SCHEDULE TOGGLED" == topic:
            self.frame.cb_schedule.Value = data
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
        elif "SCHEDULE CHANGED" == topic:
            self.frame.selector_time.SetSelections(data)
        elif "SCHEDULE IN EFFECT" == topic:
            dimming = not conf.SuspendedUntil
            self.set_tray_icon(self.TRAYICONS[dimming][True])
            if not self.skip_notification \
            and (not self.frame.Shown or self.frame.IsIconized()):
                n = conf.ThemeName or ""
                m = "Schedule in effect%s." % ("" if not n else ': theme "%s"' % n)
                m = wx.adv.NotificationMessage(title=conf.Title, message=m)
                if self.trayicon.IsAvailable(): m.UseTaskBarIcon(self.trayicon)
                m.Show()
            self.skip_notification = False
            self.update_suspend()
        elif "SUSPEND TOGGLED" == topic:
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
            self.update_suspend()
        elif "STARTUP TOGGLED" == topic:
            self.frame.cb_startup.Value = data
        elif "STARTUP POSSIBLE" == topic:
            self.frame.panel_startup.Show(data)
            self.frame.panel_startup.ContainingSizer.Layout()
        elif "MANUAL IN EFFECT" == topic:
            dimming = not conf.SuspendedUntil
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
            self.skip_notification = False
            self.update_suspend()
        elif "NORMAL DISPLAY" == topic:
            self.set_tray_icon(self.TRAYICONS[False][conf.ScheduleEnabled])
            self.skip_notification = False
            self.update_suspend()
        elif topic in ("THEME APPLIED", "THEME CHANGED"):
            if not conf.ThemeName and conf.UnsavedTheme and data == conf.UnsavedTheme:
                ThemeImaging.Add(self.unsaved_name(), data)
                tooltip = ThemeImaging.Repr(data)
                self.frame.combo_editor.ToolTip = self.frame.combo_themes.ToolTip = tooltip
            self.frame.label_error.Hide()


    def modal(self, func, *args, **kwargs):
        """Invokes a function while setting window modal-flag, returns result."""
        self.frame_has_modal = True
        try: return func(*args, **kwargs)
        finally: self.frame_has_modal = False


    def unsaved_name(self):
        """Returns current unsaved name for display, as "name *" or " (unsaved) "."""
        if conf.UnsavedName:  return conf.ModifiedTemplate % conf.UnsavedName
        if conf.UnsavedTheme: return conf.UnsavedLabel


    def update_suspend(self):
        """Updates suspend state in UI."""
        self.panel_config.Freeze()
        label, button = self.frame.label_suspend, self.frame.button_suspend
        try:
            if conf.SuspendedUntil:
                args = {"graycolour": ColourManager.ColourHex(wx.SYS_COLOUR_GRAYTEXT),
                        "linkcolour": ColourManager.ColourHex(wx.SYS_COLOUR_HOTLIGHT),
                        "time":       conf.SuspendedUntil.strftime("%H:%M")}
                label.SetPage(conf.SuspendedHTMLTemplate % args)
                label.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_WINDOW)
                button.Label   = conf.SuspendOffLabel
                button.ToolTip = conf.SuspendOffToolTip
                label.Show(); button.Show()
            elif self.dimmer.should_dim():
                button.Label   = conf.SuspendOnLabel
                button.ToolTip = conf.SuspendOnToolTip
                label.Hide(); button.Show()
            else:
                label.Hide(); button.Hide()
            button.ContainingSizer.Layout()
        finally: self.panel_config.Thaw()


    def set_tray_icon(self, icon):
        """Sets the icon into tray and sets a configured tooltip."""
        self.trayicon.SetIcon(icon, conf.TrayTooltip)


    def on_select_list_themes(self, event):
        """Handler for selecting a theme in list, toggles buttons enabled."""
        event.Skip()
        selected = self.frame.list_themes.GetSelection()
        enabled = (0 <= selected < self.frame.list_themes.GetItemCount())
        self.frame.button_apply.Enabled  = enabled
        self.frame.button_delete.Enabled = enabled


    def on_apply_list_themes(self, event=None):
        """Applies the colour theme selected in list."""
        selected = self.frame.list_themes.GetSelection()
        if not (0 <= selected < self.frame.list_themes.GetItemCount()): return

        name = self.frame.list_themes.GetItemValue(selected)
        conf.ThemeName = name
        self.frame.combo_themes.SetSelection(self.frame.combo_themes.FindItem(name))
        if not self.dimmer.should_dim(): self.dimmer.toggle_manual(True)
        self.dimmer.toggle_suspend(False)
        self.dimmer.set_theme(conf.Themes[name], fade=True)


    def on_select_combo_themes(self, event):
        """Handler for selecting an item in schedule combobox."""
        name = self.frame.combo_themes.GetItemValue(event.Selection)
        theme = conf.Themes.get(name, conf.UnsavedTheme)
        conf.ThemeName = name if event.Selection or not conf.UnsavedTheme else None
        self.dimmer.toggle_suspend(False)
        self.dimmer.set_theme(theme, fade=True)


    def on_select_combo_editor(self, event):
        """Handler for selecting an item in editor combobox."""

        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        name = cmb2.GetItemValue(event.Selection)
        if conf.UnsavedTheme and not event.Selection: name = conf.UnsavedName

        if event.Selection and conf.UnsavedTheme \
        and conf.Themes.get(conf.UnsavedName) != conf.UnsavedTheme \
        and wx.OK != self.modal(wx.MessageBox, 'Theme%s has changed, '
            'are you sure you want to discard changes?' %
            (' "%s"' % conf.UnsavedName if conf.UnsavedName else ""),
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ):
            self.frame.combo_editor.SetSelection(0)
            return

        if event.Selection and conf.UnsavedTheme:
            # Selecting saved, unsaved exists: discard unsaved
            conf.UnsavedTheme = None
            for c in cmb, cmb2:
                c.Delete(0), c.SetSelection(event.Selection - 1)
            cmb.ToolTip = ThemeImaging.Repr(conf.Themes[cmb.Value])
            ThemeImaging.Remove(self.unsaved_name())

        theme = conf.Themes.get(name, conf.UnsavedTheme)
        conf.UnsavedName = name
        conf.UnsavedTheme = None if name in conf.Themes else theme
        cmb2.ToolTip = ThemeImaging.Repr(theme)
        for s, v in zip(self.frame.sliders, theme): s.Value, s.ToolTip = v, str(v)
        if self.dimmer.should_dim():
            conf.ThemeName = name
            cmb.SetSelection(cmb.FindItem(name))
            self.dimmer.toggle_suspend(False)
            self.dimmer.set_theme(theme, fade=True)


    def on_change_theme_slider(self, event):
        """Handler for a change in theme component slider."""
        theme = []
        for s in self.frame.sliders:
            new = isinstance(event, wx.ScrollEvent) and s is event.EventObject
            value = event.GetPosition() if new else s.GetValue()
            s.ToolTip = str(value)
            theme.append(value)
        if theme == conf.UnsavedTheme: return

        ThemeImaging.Add(self.unsaved_name(), theme)

        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        if not conf.UnsavedTheme:
            cmb .Insert(self.unsaved_name(), 0)
            cmb2.Insert(self.unsaved_name(), 0)
        conf.UnsavedTheme = theme
        cmb2.SetSelection(0)
        cmb2.ToolTip = ThemeImaging.Repr(theme)
        if self.dimmer.should_dim():
            conf.ThemeName = None
            cmb.SetSelection(0)
            cmb.ToolTip = cmb2.ToolTip
            self.dimmer.toggle_suspend(False)
            self.dimmer.set_theme(theme)


    def on_save_theme(self, event=None):
        """Stores the currently set rgb+brightness values in theme editor."""
        theme = conf.UnsavedTheme or conf.Themes[conf.UnsavedName]
        name0 = name = conf.UnsavedName or ThemeImaging.Repr(theme, short=True)

        dlg = wx.TextEntryDialog(self.frame, "Name:", conf.Title,
                                 value=name, style=wx.OK | wx.CANCEL)
        dlg.CenterOnParent()
        if wx.ID_OK != self.modal(dlg.ShowModal): return

        name = dlg.GetValue().strip()
        if not name: return

        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        if theme == conf.Themes.get(name): # No change from saved
            if conf.UnsavedTheme: # Had changes before
                idx_v = cmb.GetSelection()
                for c in cmb, cmb2: c.Delete(0) # Discard unsaved item
                if not idx_v: # Was unsaved selected
                    cmb.SetSelection(cmb.FindItem(name))
                cmb2.SetSelection(cmb2.FindItem(name))
                ThemeImaging.Remove(self.unsaved_name())
                conf.UnsavedTheme = None
                conf.save()
            ThemeImaging.Add(name, theme)
            return

        theme_existed = name in conf.Themes
        if theme_existed and wx.OK != self.modal(wx.MessageBox,
            'Theme "%s" already exists, are you sure you want to overwrite it?' % name,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        conf.Themes[name] = theme
        conf.UnsavedName, conf.UnsavedTheme = name, None
        if not conf.ThemeName: conf.ThemeName = name
        conf.save()
        ThemeImaging.Add(name, theme)
        items = sorted(conf.Themes, key=lambda x: x.lower())
        lst_v = self.frame.list_themes.Value
        for c in cmb, cmb2, self.frame.list_themes: c.SetItems(items)
        cmb.SetSelection(cmb.FindItem(name))
        cmb2.SetSelection(cmb2.FindItem(name))
        self.frame.list_themes.SetSelection(self.frame.list_themes.FindItem(lst_v))
        self.frame.button_restore.Shown = any(
            conf.Themes.get(k) != v for k, v in conf.Defaults["Themes"].items())
        self.frame.button_restore.ContainingSizer.Layout()
        ThemeImaging.Remove(self.unsaved_name())


    def on_reset_theme(self, event=None):
        """Resets the currently set rgb+brightness values in theme editor."""
        if not conf.UnsavedName or not conf.UnsavedTheme: return

        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        conf.UnsavedTheme = None
        was_unsaved_selected = not cmb.GetSelection()
        cmb.Delete(0)
        cmb2.Delete(0)
        ThemeImaging.Remove(self.unsaved_name())

        name2 = conf.UnsavedName
        if name2 not in conf.Themes and conf.Themes:
            name2 = sorted(conf.Themes, key=lambda x: x.lower())[0]
        if name2 in conf.Themes:
            theme2 = conf.Themes[name2]
            if not conf.ThemeName: conf.ThemeName = name2
        else:
            name2, theme2 = "", conf.Defaults["Themes"][conf.Defaults["ThemeName"]]

        conf.UnsavedName = name2
        conf.save()
        cmb2.SetSelection(cmb2.FindItem(name2))
        cmb2.ToolTip = ThemeImaging.Repr(theme2)
        for s, v in zip(self.frame.sliders, theme2): s.Value, s.ToolTip = v, str(v)
        if was_unsaved_selected:
            cmb.SetSelection(cmb.FindItem(name2))
            cmb.ToolTip = cmb2.ToolTip
            if self.dimmer.should_dim():
                self.dimmer.toggle_suspend(False)
                self.dimmer.apply_theme(theme2, fade=True)


    def on_delete_theme(self, event=None):
        """Deletes the stored theme on confirm."""
        lst = self.frame.list_themes
        selected = lst.GetSelection()
        if not (0 <= selected < lst.GetItemCount()): return

        name = lst.GetItemValue(selected)
        theme = conf.Themes[name]
        resp = self.modal(wx.MessageBox, 'Delete theme "%s"?' % name,
                          conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING)
        lst.SetFocus()
        if wx.OK != resp: return

        conf.Themes.pop(name, None)
        ThemeImaging.Remove(name)
        if name == conf.UnsavedName: ThemeImaging.Remove(self.unsaved_name())
        lst.RemoveItemAt(selected)
        lst.SetSelection(max(0, min(selected, lst.GetItemCount() - 1)))
        lst.Refresh()
        enabled = (0 <= lst.GetSelection() < lst.GetItemCount())
        self.frame.button_apply.Enabled  = enabled
        self.frame.button_delete.Enabled = enabled
        self.frame.button_restore.Shown = any(
            conf.Themes.get(k) != v for k, v in conf.Defaults["Themes"].items())
        self.frame.button_restore.ContainingSizer.Layout()

        if self.dimmer.should_dim() and (conf.ThemeName or conf.UnsavedName) == name:
            self.dimmer.toggle_schedule(False)
            self.dimmer.toggle_manual(False)

        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        was_unsaved = conf.UnsavedTheme and conf.UnsavedName == name

        for c in cmb2, cmb:
            # Drop theme from combos, selecting another if was selected
            idx = c.FindItem(name)
            was_selected = conf.UnsavedTheme and not c.GetSelection() \
                           or (idx >= 0) and c.GetSelection() == idx
            c.Delete(idx)
            if was_unsaved: c.Delete(0) # Both combos have unsaved-item

            if was_selected and c.GetCount():
                idx2 = max(0, min(selected - bool(was_unsaved), c.GetCount() - 1))
                c.SetSelection(idx2)
                name2, theme2 = c.Value, conf.Themes[c.Value]
                if c is cmb:
                    conf.ThemeName = name2
                    self.dimmer.set_theme(theme2, fade=True)
                else:
                    conf.UnsavedName = name2
                    if was_unsaved: conf.UnsavedTheme = None
                    for s, v in zip(self.frame.sliders, theme2):
                        s.Value, s.ToolTip = v, str(v)
                c.ToolTip = ThemeImaging.Repr(theme2)

        if not conf.Themes and not conf.UnsavedTheme:
            # Deleted last theme and nothing being modified: add something at least
            conf.ThemeName, conf.UnsavedName, conf.UnsavedTheme = None, "", theme
            ThemeImaging.Add(self.unsaved_name(), theme)
            for c in cmb, cmb2:
                c.Insert(self.unsaved_name(), 0)
                c.SetSelection(0)
                c.ToolTip = ThemeImaging.Repr(theme)
            self.dimmer.set_theme(theme, fade=True)
        conf.save()


    def on_restore_themes(self, event=None):
        """Restores original themes."""
        conf.Themes.update(conf.Defaults["Themes"])
        conf.save()
        self.populate()


    def on_open_tray_menu(self, event=None):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()

        def on_apply_theme(name, theme, event):
            if not event.IsChecked(): return
            conf.ThemeName = name if name != self.unsaved_name() else None
            conf.save()
            self.frame.combo_themes.SetSelection(self.frame.combo_themes.FindItem(name))
            if not self.dimmer.should_dim(): self.dimmer.toggle_manual(True)
            self.dimmer.toggle_suspend(False)
            self.dimmer.set_theme(theme, fade=True)

        def on_suspend_interval(interval, event):
            if not event.IsChecked(): return self.on_toggle_suspend()

            self.suspend_interval = interval
            conf.SuspendedUntil = dt + datetime.timedelta(minutes=interval)
            self.update_suspend()


        is_dimming = self.dimmer.should_dim()
        item = wx.MenuItem(menu, -1, "Apply &now", kind=wx.ITEM_CHECK)
        item.Font = self.frame.Font.Bold()
        menu.Append(item)
        item.Check(is_dimming and not self.dimmer.should_dim_scheduled())
        menu.Bind(wx.EVT_MENU, self.on_toggle_manual, id=item.GetId())

        item = wx.MenuItem(menu, -1, "Apply on &schedule", kind=wx.ITEM_CHECK)
        if self.dimmer.should_dim_scheduled(): item.Font = self.frame.Font.Bold()
        menu.Append(item)
        item.Check(conf.ScheduleEnabled)
        menu.Bind(wx.EVT_MENU, self.on_toggle_schedule, id=item.GetId())
        if self.dimmer.should_dim():
            if conf.SuspendedUntil:
                menu_intervals = wx.Menu()
                dt = conf.SuspendedUntil - datetime.timedelta(minutes=self.suspend_interval)
                for x in conf.SuspendIntervals:
                    label = "&%s minutes (until %s)" % \
                            (x, (dt + datetime.timedelta(minutes=x)).strftime("%H:%M"))
                    item = menu_intervals.Append(-1, label, kind=wx.ITEM_CHECK)
                    item.Check(x == self.suspend_interval)
                    handler = functools.partial(on_suspend_interval, x)
                    menu.Bind(wx.EVT_MENU, handler, id=item.GetId())
                label = conf.SuspendedTemplate % conf.SuspendedUntil.strftime("%H:%M")
                menu.Append(-1, label.replace("u", "&u", 1), menu_intervals)
            else:
                label = conf.SuspendOnLabel.strip().replace("u", "&u", 1)
                label = re.sub("\s+", " ", label)
                item = menu.Append(-1, label, kind=wx.ITEM_CHECK)
                item.Check(bool(conf.SuspendedUntil))
                menu.Bind(wx.EVT_MENU, self.on_toggle_suspend, id=item.GetId())
        item = menu.Append(-1, "&Run at startup", kind=wx.ITEM_CHECK)
        item.Check(conf.StartupEnabled)
        menu.Bind(wx.EVT_MENU, self.on_toggle_startup, id=item.GetId())
        menu.AppendSeparator()

        menu_themes = wx.Menu()
        items = sorted(conf.Themes.items(), key=lambda x: x[0].lower())
        if conf.UnsavedTheme:
            items.insert(0, (self.unsaved_name(), conf.UnsavedTheme))
        for name, theme in items:
            item = menu_themes.Append(-1, name.strip(), kind=wx.ITEM_CHECK)
            if is_dimming: item.Check(name == conf.ThemeName
                                      or name == self.unsaved_name()
                                         and not conf.ThemeName)
            handler = functools.partial(on_apply_theme, name, theme)
            menu.Bind(wx.EVT_MENU, handler, id=item.GetId())
        menu.Append(-1, "Apply &theme", menu_themes)

        item = wx.MenuItem(menu, -1, "&Options")
        item.Enable(not self.frame.Shown)
        menu.Bind(wx.EVT_MENU, self.on_toggle_settings, id=item.GetId())
        menu.Append(item)
        item = wx.MenuItem(menu, -1, "E&xit %s" % conf.Title)
        menu.Bind(wx.EVT_MENU, self.on_exit, id=item.GetId())
        menu.Append(item)

        self.trayicon.PopupMenu(menu)


    def on_change_schedule(self, event=None):
        """Handler for changing the time schedule in settings window."""
        self.dimmer.set_schedule(self.frame.selector_time.GetSelections())


    def on_toggle_startup(self, event=None):
        """Handler for toggling the auto-load in settings window on/off."""
        self.dimmer.toggle_startup(not conf.StartupEnabled)


    def on_activate_window(self, event):
        """Handler for activating/deactivating window, hides it if focus lost."""
        if not self.frame or self.frame_has_modal \
        or not self.trayicon.IsAvailable(): return

        if self.frame.Shown \
        and not (event.Active or self.frame_hider or self.frame_shower):
            millis = conf.WindowTimeout * 1000
            if millis >= 0: # Hide if timeout positive
                self.frame_hider = wx.CallLater(millis, self.settings_slidein)
        elif event.Active: # Kill the hiding timeout, if any
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
        if self.frame_has_modal: return

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
        self.frame.selector_time.timer.Stop()
        self.trayicon.RemoveIcon()
        self.trayicon.Destroy()
        self.frame.Destroy()
        wx.CallAfter(sys.exit) # Immediate exit fails if exiting from tray
        try: sys.exit()
        except Exception: pass


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


    def on_key(self, event):
        """Handler for keypress, hides window on pressing Escape."""
        event.Skip()
        if not event.HasModifiers() and event.KeyCode in KEYS.ESCAPE:
            self.on_toggle_settings()


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
            millis = conf.WindowTimeout * 1000
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


    def on_toggle_suspend(self, event=None):
        """Handler for toggling schedule suspension on/off."""
        if conf.SuspendedUntil:
            label, tooltip = conf.SuspendOnLabel, conf.SuspendOnToolTip
            self.suspend_interval = None
        else:
            label, tooltip = conf.SuspendOffLabel, conf.SuspendOffToolTip
            self.suspend_interval = conf.DefaultSuspendInterval
        self.skip_notification = bool(event and conf.SuspendedUntil)
        self.frame.button_suspend.Label   = label
        self.frame.button_suspend.ToolTip = tooltip
        self.frame.button_suspend.ContainingSizer.Layout()
        self.dimmer.toggle_suspend(conf.SuspendedUntil is None)


    def on_toggle_manual(self, event):
        """Handler for toggling manual dimming on/off."""
        self.skip_notification = self.dimmer.should_dim_scheduled() \
                                 and not event.IsChecked()
        self.dimmer.toggle_manual(event.IsChecked())


    def on_toggle_dimming_tray(self, event):
        """
        Handler for toggling dimming on/off from the tray, can affect either
        schedule or global flag.
        """
        self.dt_tray_click = None
        self.skip_notification = True
        do_dim = not self.dimmer.should_dim()
        if do_dim and self.dimmer.should_dim_scheduled(flag=True):
            self.dimmer.toggle_schedule(True)
        elif not do_dim and self.dimmer.should_dim_scheduled():
            self.dimmer.toggle_manual(False)
            self.dimmer.toggle_schedule(False)
        else: self.dimmer.toggle_manual(do_dim)


    def on_toggle_schedule(self, event):
        """Handler for toggling schedule on/off."""
        self.skip_notification = event.IsChecked()
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
        ThemeImaging.ClearCache()
        args = {"graycolour": ColourManager.ColourHex(wx.SYS_COLOUR_GRAYTEXT),
                "textcolour": ColourManager.ColourHex(wx.SYS_COLOUR_BTNTEXT),
                "linkcolour": ColourManager.ColourHex(wx.SYS_COLOUR_HOTLIGHT)}
        self.frame.label_about.SetPage(conf.AboutHTMLTemplate % args)
        if conf.SuspendedUntil:
            args["time"] = conf.SuspendedUntil.strftime("%H:%M")
            self.frame.label_suspend.SetPage(conf.SuspendedHTMLTemplate % args)


    def on_change_suspend(self, event):
        """Handler for clicking time link in suspend label, opens interval choice dialog."""
        dt = datetime.datetime.now()
        choices = ["%s minutes (until %s)" % 
                   (x, (dt + datetime.timedelta(minutes=x)).strftime("%H:%M"))
                   for x in conf.SuspendIntervals]
        dlg = wx.SingleChoiceDialog(self.frame, "Suspend for:", conf.Title, choices)
        dlg.CenterOnParent()
        dlg.SetSelection(conf.SuspendIntervals.index(self.suspend_interval))
        resp = self.modal(dlg.ShowModal)
        if wx.ID_OK != resp: return

        interval = conf.SuspendIntervals[dlg.GetSelection()]        
        dt2 = dt + datetime.timedelta(minutes=interval)
        if dt2 <= datetime.datetime.now(): # Selected date already past
            return self.dimmer.toggle_suspend(False)

        if not conf.SuspendedUntil: # Already unsuspended while dialog open
            self.dimmer.toggle_suspend(True)
        self.suspend_interval = interval
        conf.SuspendedUntil = dt2
        args = {"graycolour": ColourManager.ColourHex(wx.SYS_COLOUR_GRAYTEXT),
                "linkcolour": ColourManager.ColourHex(wx.SYS_COLOUR_HOTLIGHT),
                "time":       conf.SuspendedUntil.strftime("%H:%M")}
        self.frame.label_suspend.SetPage(conf.SuspendedHTMLTemplate % args)
        self.frame.label_suspend.BackgroundColour = ColourManager.GetColour(wx.SYS_COLOUR_WINDOW)


    def create_frame(self):
        """Creates and returns the settings window."""
        frame = wx.Dialog(parent=None, title=conf.Title, size=conf.WindowSize,
            style=wx.CAPTION | wx.SYSTEM_MENU | wx.CLOSE_BOX | wx.STAY_ON_TOP
        )

        panel = frame.panel = wx.Panel(frame)
        sizer = panel.Sizer = wx.BoxSizer(wx.VERTICAL)
        sizer_checkboxes = wx.BoxSizer(wx.HORIZONTAL)

        cb_schedule = frame.cb_schedule = wx.CheckBox(panel, label="Apply on schedule")
        cb_schedule.ToolTip = "Apply automatically during the highlighted hours"
        cb_manual = frame.cb_manual = wx.CheckBox(panel, label="Apply now")
        cb_manual.ToolTip = "Apply colour theme regardless of schedule"
        sizer_checkboxes.Add(cb_schedule)
        sizer_checkboxes.AddStretchSpacer()
        sizer_checkboxes.Add(cb_manual)
        sizer.Add(sizer_checkboxes, border=5, flag=wx.ALL | wx.GROW)

        notebook = frame.notebook = wx.lib.agw.flatnotebook.FlatNotebook(panel)
        notebook.SetAGWWindowStyleFlag(wx.lib.agw.flatnotebook.FNB_FANCY_TABS |
                                       wx.lib.agw.flatnotebook.FNB_NO_X_BUTTON |
                                       wx.lib.agw.flatnotebook.FNB_NO_NAV_BUTTONS |
                                       wx.lib.agw.flatnotebook.FNB_NODRAG |
                                       wx.lib.agw.flatnotebook.FNB_NO_TAB_FOCUS)
        ColourManager.Manage(notebook, "ActiveTabTextColour",    wx.SYS_COLOUR_BTNTEXT)
        ColourManager.Manage(notebook, "NonActiveTabTextColour", wx.SYS_COLOUR_GRAYTEXT)
        ColourManager.Manage(notebook, "TabAreaColour",          wx.SYS_COLOUR_BTNFACE)
        ColourManager.Manage(notebook, "GradientColourBorder",   wx.SYS_COLOUR_BTNSHADOW)
        ColourManager.Manage(notebook, "GradientColourFrom",     wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(notebook, "GradientColourTo",       wx.SYS_COLOUR_WINDOW)
        ColourManager.Manage(notebook, "NonActiveTabTextColour", wx.SYS_COLOUR_GRAYTEXT)
        sizer.Add(notebook, proportion=1, border=5, flag=wx.GROW | wx.LEFT | wx.RIGHT)

        panel_config = self.panel_config = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_config.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel_config, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        notebook.AddPage(panel_config, "Schedule ")
        panel_themes = self.panel_themes = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_themes.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel_themes, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        notebook.AddPage(panel_themes, "Saved themes ")
        panel_editor = self.panel_editor = wx.Panel(notebook, style=wx.BORDER_SUNKEN)
        panel_editor.Sizer = wx.BoxSizer(wx.VERTICAL)
        ColourManager.Manage(panel_editor, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        notebook.AddPage(panel_editor, "Theme editor ")
        panel_about = self.panel_about = wx.Panel(notebook, style=wx.BORDER_NONE)
        panel_about.Sizer = wx.BoxSizer(wx.VERTICAL)
        notebook.AddPage(panel_about, "About ")

        # Create config page, with time selector and scheduling checkboxes
        panel_middle = wx.Panel(panel_config)
        ColourManager.Manage(panel_middle, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        sizer_middle  = wx.BoxSizer(wx.HORIZONTAL)
        sizer_right   = wx.BoxSizer(wx.VERTICAL)
        sizer_combo   = wx.BoxSizer(wx.VERTICAL)
        selector_time = frame.selector_time = ClockSelector(panel_config)
        frame.label_combo = wx.StaticText(panel_config, label="Colour theme:")

        combo_themes = BitmapComboBox(panel_config, bitmapsize=conf.ThemeNamedBitmapSize,
                                     imagehandler=ThemeImaging)
        frame.combo_themes = combo_themes
        combo_themes.SetPopupMaxHeight(250)

        label_error = frame.label_error = wx.StaticText(panel_config, style=wx.ALIGN_CENTER)
        ColourManager.Manage(label_error, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)

        label_suspend = frame.label_suspend = wx.html.HtmlWindow(panel_config,
            size=(-1, 16), style=wx.html.HW_SCROLLBAR_NEVER)
        ColourManager.Manage(label_suspend, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        label_suspend.SetBorders(0)
        label_suspend.ToolTip = "Click on time to change interval"
        label_suspend.Hide()
        frame.button_suspend = wx.Button(panel_config, label=conf.SuspendOnLabel)
        frame.button_suspend.ToolTip = conf.SuspendOnToolTip
        if "\n" in conf.SuspendOnLabel:
            sz = (-1,  frame.button_suspend.CharHeight * 2 + 9) if "nt" == os.name else \
                 (140, frame.button_suspend.BestSize[1])
            frame.button_suspend.Size = frame.button_suspend.MinSize = sz
        frame.button_suspend.Hide()
        panel_startup = frame.panel_startup = wx.Panel(panel_config)
        frame.cb_startup = wx.CheckBox(panel_startup, label="Run at startup       ")
        frame.cb_startup.ToolTip = "Add %s to startup programs" % conf.Title

        sizer_middle.Add(selector_time, proportion=1, border=5, flag=wx.GROW | wx.ALL)
        sizer_combo.Add(frame.label_combo)
        sizer_combo.Add(combo_themes)
        sizer_right.Add(sizer_combo, border=5,  flag=wx.LEFT | wx.ALIGN_RIGHT)
        sizer_right.Add(label_error, border=10, flag=wx.LEFT | wx.TOP | wx.BOTTOM)
        sizer_right.AddStretchSpacer()
        sizer_right.Add(label_suspend, border=5, flag=wx.LEFT | wx.TOP | wx.GROW)
        sizer_right.Add(frame.button_suspend, border=5, flag=wx.ALL ^ wx.BOTTOM | wx.GROW)
        panel_startup.Sizer = wx.BoxSizer(wx.VERTICAL)
        panel_startup.Sizer.Add(frame.cb_startup, border=5, flag=wx.LEFT)
        sizer_right.Add(panel_startup, border=5, flag=wx.TOP)
        sizer_middle.Add(sizer_right, border=5, flag=wx.BOTTOM | wx.GROW)
        panel_config.Sizer.Add(sizer_middle, proportion=1, border=5, flag=wx.GROW | wx.ALL)


        # Create saved themes page
        list_themes = BitmapListCtrl(panel_themes, imagehandler=ThemeImaging)
        list_themes.SetThumbSize(*conf.ThemeBitmapSize, border=5)
        list_themes.SetToolTipFunction(lambda n: ThemeImaging.Repr(conf.Themes[n]))
        ColourManager.Manage(list_themes, "BackgroundColour", wx.SYS_COLOUR_WINDOW)
        frame.list_themes = list_themes

        panel_saved_buttons = wx.Panel(panel_themes)
        panel_saved_buttons.Sizer = wx.BoxSizer(wx.HORIZONTAL)
        frame.button_apply   = wx.Button(panel_saved_buttons, label="Apply theme")
        frame.button_restore = wx.Button(panel_saved_buttons, label="Restore defaults")
        frame.button_delete  = wx.Button(panel_saved_buttons, label="Remove theme")
        frame.button_restore.ToolTip = "Restore original themes"
        frame.button_apply.Enabled = frame.button_delete.Enabled = False

        panel_themes.Sizer.Add(list_themes, border=5, proportion=1, flag=wx.TOP | wx.GROW)
        panel_themes.Sizer.Add(panel_saved_buttons, border=5,
                                     flag=wx.GROW | wx.ALL)
        panel_saved_buttons.Sizer.Add(frame.button_apply)
        panel_saved_buttons.Sizer.AddStretchSpacer()
        panel_saved_buttons.Sizer.Add(frame.button_restore)
        panel_saved_buttons.Sizer.AddStretchSpacer()
        panel_saved_buttons.Sizer.Add(frame.button_delete)


        # Create theme editor page, with RGB sliders and color sample panel
        text_detail = wx.StaticText(panel_editor,
            style=wx.ALIGN_CENTER, label=conf.InfoEditorText)
        dfont = text_detail.Font; dfont.SetPointSize(8 + bool("nt" != os.name))
        text_detail.Font = dfont
        ColourManager.Manage(text_detail, "ForegroundColour", wx.SYS_COLOUR_GRAYTEXT)

        sizer_bar = wx.BoxSizer(wx.HORIZONTAL)
        sizer_right = wx.BoxSizer(wx.VERTICAL)

        sizer_sliders = wx.FlexGridSizer(rows=4, cols=3, vgap=2, hgap=5)
        sizer_sliders.AddGrowableCol(1, proportion=1)
        frame.sliders = []
        kws = dict(red=0, green=0, blue=0)
        for i, text in enumerate(["brightness", "red", "green", "blue"]):
            if i: bmp1, bmp2 = [make_colour_bitmap(wx.Colour(**dict(kws, **{text: x})))
                                for x in conf.ValidColourRange]
            else: bmp1, bmp2 = map(wx.Bitmap,         conf.BrightnessIcons)
            sbmp1 = wx.StaticBitmap(panel_editor, bitmap=bmp1)
            sbmp2 = wx.StaticBitmap(panel_editor, bitmap=bmp2)
            slider = wx.Slider(panel_editor, size=(-1, 20),
                minValue=conf.ValidColourRange[0]  if i else   0, # Brightness
                maxValue=conf.ValidColourRange[-1] if i else 255, # goes 0..255
            )
            slider.ToolTip = str(slider.Value)
            tooltip = "%s colour channel" % text.capitalize() if i else \
                      "Brightness (center is default, " \
                      "higher goes brighter than normal)"
            sbmp1.ToolTip = sbmp2.ToolTip = tooltip
            sizer_sliders.Add(sbmp1,  flag=wx.ALIGN_CENTER)
            sizer_sliders.Add(slider, flag=wx.ALIGN_CENTER_VERTICAL | wx.GROW)
            sizer_sliders.Add(sbmp2,  flag=wx.ALIGN_CENTER)
            frame.sliders.append(slider)
        frame.sliders.append(frame.sliders.pop(0)) # Make brightness first

        combo_editor = BitmapComboBox(panel_editor, bitmapsize=conf.ThemeNamedBitmapSize,
                                     imagehandler=ThemeImaging)
        frame.combo_editor = combo_editor
        combo_editor.SetPopupMaxHeight(200)

        sizer_tbuttons = wx.BoxSizer(wx.HORIZONTAL)
        button_save  = frame.button_save  = wx.Button(panel_editor, label=" Save..")
        button_reset = frame.button_reset = wx.Button(panel_editor, label="Reset")
        button_reset.MinSize = combo_editor.Size[0] / 2 - 3, -1
        button_save.MinSize  = combo_editor.Size[0] / 2 - 2, -1
        button_save.ToolTip  = "Save settings as a named theme"
        button_reset.ToolTip = "Restore original settings"

        panel_editor.Sizer.Add(text_detail, proportion=10, border=5,
            flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)
        panel_editor.Sizer.AddStretchSpacer()
        sizer_right.Add(combo_editor,   border=5, flag=wx.TOP)
        sizer_tbuttons.Add(button_save, border=5, flag=wx.RIGHT)
        sizer_tbuttons.Add(button_reset, flag=wx.ALIGN_BOTTOM)
        sizer_right.Add(sizer_tbuttons, border=5, flag=wx.TOP)
        sizer_bar.Add(sizer_sliders, border=10, proportion=1, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_BOTTOM)
        sizer_bar.Add(sizer_right, border=5, flag=wx.ALL | wx.GROW)
        panel_editor.Sizer.Add(sizer_bar, proportion=1, flag=wx.GROW)


        # Create About-page
        label_about = frame.label_about = wx.html.HtmlWindow(panel_about)
        args = {"textcolour": ColourManager.ColourHex(wx.SYS_COLOUR_BTNTEXT),
                "linkcolour": ColourManager.ColourHex(wx.SYS_COLOUR_HOTLIGHT)}
        label_about.SetPage(conf.AboutHTMLTemplate % args)
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

        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_ok = frame.button_ok = wx.lib.agw.gradientbutton.GradientButton(
            panel, label="Minimize", size=(100, -1))
        button_exit = frame.button_exit = wx.lib.agw.gradientbutton.GradientButton(
            panel, label="Exit program", size=(100, -1))
        for b in (button_ok, button_exit):
            b.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT).Bold()
            b.SetTopStartColour(wx.Colour(96, 96, 96))
            b.SetTopEndColour(wx.Colour(112, 112, 112))
            b.SetBottomStartColour(b.GetTopEndColour())
            b.SetBottomEndColour(wx.Colour(160, 160, 160))
            b.SetPressedTopColour(wx.Colour(160, 160, 160))
            b.SetPressedBottomColour(wx.Colour(160, 160, 160))
        if button_exit.CharWidth * len("Exit program") > button_exit.MinSize[0]:
            button_exit.MinSize = 120, -1
        button_ok.ToolTip = "Minimize window%s [Escape]" % \
            (" to tray" if wx.adv.TaskBarIcon.IsAvailable() else "")

        sizer_buttons.Add(button_ok, border=5, flag=wx.TOP)
        sizer_buttons.AddStretchSpacer()
        sizer_buttons.Add(button_exit, border=5, flag=wx.TOP)
        sizer.Add(sizer_buttons, border=5, flag=wx.GROW | wx.ALL)

        frame.Layout()

        x1, y1, x2, y2 = wx.GetClientDisplayRect() # Set in lower right corner
        frame.Position = (x2 - frame.Size.x, y2 - frame.Size.y)

        self.frame_console = wx.py.shell.ShellFrame(parent=None,
          title="%s Console" % conf.Title, size=(800, 300)
        )
        self.frame_console.Bind(wx.EVT_CLOSE, lambda e: self.frame_console.Hide())

        icons = wx.IconBundle()
        for p in conf.WindowIcons: icons.AddIcon(wx.Icon(p))
        frame.SetIcons(icons)
        self.frame_console.SetIcons(icons)
        frame.ToggleWindowStyle(wx.STAY_ON_TOP)
        panel_config.SetFocus()
        return frame


    def populate(self):
        """Populates controls with data."""
        for name, theme in conf.Themes.items():
            ThemeImaging.Add(name, theme)
        if conf.UnsavedTheme:
            ThemeImaging.Add(self.unsaved_name(), conf.UnsavedTheme)
        self.frame.button_restore.Shown = any(
            conf.Themes.get(k) != v for k, v in conf.Defaults["Themes"].items())
        self.frame.button_restore.ContainingSizer.Layout()

        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        lst = self.frame.list_themes
        items = sorted(conf.Themes, key=lambda x: x.lower())
        citems = ([self.unsaved_name()] if conf.UnsavedTheme else []) + items
        cmb.SetItems(citems)
        lst.SetItems(items)
        cmb2.SetItems(citems)

        names = filter(bool, [conf.ThemeName, self.unsaved_name()])
        for ctrl in cmb, cmb2:
            idx = next((i for n in names for i in [ctrl.FindItem(n)] if i >= 0), -1)
            if idx >= 0:
                ctrl.SetSelection(idx)
                theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
                ctrl.ToolTip = ThemeImaging.Repr(theme)
        if conf.ThemeName:
            lst.SetSelection(lst.FindItem(conf.ThemeName))
            enabled = (0 <= lst.GetSelection() < lst.GetItemCount())
            self.frame.button_apply.Enabled  = enabled
            self.frame.button_delete.Enabled = enabled
        if not conf.UnsavedTheme:
            conf.UnsavedName = cmb2.GetItemValue(cmb2.GetSelection())

        theme = conf.Themes.get(cmb.Value, conf.UnsavedTheme)
        for s, v in zip(self.frame.sliders, theme): s.Value, s.ToolTip = v, str(v)



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
    FONT_SIZE     = 8
    INTERVAL      = 30
    INTERVAL_TOOLTIP = 1
    RADIUS_CENTER = 20
    ANGLE_START   = math.pi / 2 # 0-hour position, in radians from horizontal

    def __init__(self, parent, id=-1, pos=wx.DefaultPosition,
                 size=(400, 400), style=0, name=wx.PanelNameStr,
                 selections=(0, )*24*4):
        """
        @param   selections  the selections to use, as [0,1,] for each time
                             unit in 24 hours. Length of selections determines
                             the minimum selectable step. Defaults to a quarter
                             hour step.
        """
        super(ClockSelector, self).__init__(parent, id, pos, size,
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
        sections, start = [], None # sections=[(start, len), ]
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
        gc.SetPen(wx.Pen(ClockSelector.COLOUR_LINES, style=wx.TRANSPARENT))
        gc.SetBrush(wx.Brush(self.BackgroundColour, wx.SOLID))
        gc.DrawRoundedRectangle(0, 0, width - 1, height - 1, 18)

        # Draw and fill all selected sectors
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

        dc.Background = wx.Brush(self.BackgroundColour)
        dc.Clear()

        # Draw highlighted sectors
        dc.Pen = wx.TRANSPARENT_PEN
        dc.Brush = wx.Brush(ClockSelector.COLOUR_ON, wx.SOLID)
        for sect in (x for i, x in enumerate(self.sectors) if self.selections[i]):
            dc.DrawPolygon(sect)

        # Draw outer border
        dc.Pen = wx.Pen(ClockSelector.COLOUR_LINES)
        dc.Brush = wx.TRANSPARENT_BRUSH
        dc.DrawRectangle(0, 0, width, height)

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

        refresh, do_tooltip = False, False
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
            event = TimeSelectorEvent()
            wx.PostEvent(self.TopLevelParent.EventHandler, event)
        if do_tooltip:
            if self.tooltip_timer: self.tooltip_timer.Stop()
            self.tooltip_timer = wx.CallLater(self.INTERVAL_TOOLTIP * 1000,
                                              self.OnToolTip)



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
        # Hack to get around ThumbnailCtrl's internal monkey-patching
        setattr(self._scrolled, "GetThumbInfo", self._GetThumbInfo)

        self.EnableDragging(False)
        self.EnableToolTips(True)
        self.SetDropShadow(False)
        self.ShowFileNames(True)

        self._scrolled.Bind(wx.EVT_CHAR_HOOK, self._OnChar)
        self._scrolled.Bind(wx.EVT_MOUSEWHEEL, None) # Disable zoom
        self._scrolled.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_SEL_CHANGED,
                            self._OnSelectionChanged)
        self._scrolled.Bind(wx.lib.agw.thumbnailctrl.EVT_THUMBNAILS_DCLICK,
                            self._OnDoubleClick)
        ColourManager.Manage(self._scrolled, "BackgroundColour", wx.SYS_COLOUR_WINDOW)


    def GetItemValue(self, index):
        """Returns item value at specified index."""
        if not (0 <= index < self.GetItemCount()): return
        thumb = self.GetItem(index)
        if thumb: return thumb.GetFileName()


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
        self.ShowThumbs([wx.lib.agw.thumbnailctrl.Thumb(self, folder="", filename=x,
                         caption=x) for x in items], caption="")


    def SetToolTipFunction(self, get_info):
        """Registers callback(name) for image tooltips."""
        self._get_info = get_info


    def _GetThumbInfo(self, index):
        """Returns the thumbnail information for the specified index."""
        thumb = self.GetItem(index)
        if thumb and self._get_info: return self._get_info(thumb.GetFileName())


    def _OnChar(self, event):
        """Handler for keypress, allows navigation, activation and deletion."""
        if not self.GetItemCount(): return event.Skip()

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
        evt = wx.lib.agw.thumbnailctrl.ThumbnailEvent(
            wx.lib.agw.thumbnailctrl.wxEVT_THUMBNAILS_SEL_CHANGED, self.Id)
        evt.SetEventObject(self)
        evt.Selection = self.GetSelection()
        wx.PostEvent(self, evt)


    def _OnDoubleClick(self, event=None):
        """Handler for double-clicking item, fires EVT_THUMBNAILS_DCLICK."""
        if event: event.Skip()
        evt = wx.lib.agw.thumbnailctrl.ThumbnailEvent(
            wx.lib.agw.thumbnailctrl.wxEVT_THUMBNAILS_DCLICK, self.Id)
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)



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



class ThemeImaging(object):
    """
    Loader for theme images, uses dynamically generated bitmaps.
    Suitable as imagehandler for wx.lib.agw.thumbnailctrl.ThumbnailCtrl.
    """
    _themes    = {} # {name: theme, }
    _bitmaps   = {} # {name: {args: wx.Bitmap}, }
    _supported = {} # {theme: bool, }
    _ctrls     = set() # {control to refresh on registering theme, }


    @classmethod
    def Add(cls, name, theme):
        """Registers or overwrites theme bitmap."""
        cls._themes[name] = copy.deepcopy(theme)
        cls._bitmaps.pop(name, None)
        for c in list(cls._ctrls):
            if c: c.Refresh()
            else: cls._ctrls.discard(c) # Widget destroyed


    @classmethod
    def Remove(cls, name):
        """Drops theme bitmap."""
        for d in cls._bitmaps, cls._themes: d.pop(name, None)


    @classmethod
    def GetBitmap(cls, name, border=False, label=None):
        """Returns bitmap for named theme, created with other args."""
        theme, args = cls._themes[name], dict(border=border, label=label)
        if cls._supported.get(tuple(theme)) == False:
            args["supported"] = False
        key = tuple((k, bool(v)) for k, v in args.items() if v)
        cls._bitmaps.setdefault(name, {})
        if key not in cls._bitmaps[name]:
            bmp = cls.MakeBitmap(theme, **args)
            cls._bitmaps[name][key] = bmp
        return cls._bitmaps[name][key]


    @classmethod
    def IsSupported(cls, theme):
        """Returns whether theme has been marked as supported, or None."""
        return cls._supported.get(tuple(theme))


    @classmethod
    def MarkSupported(cls, theme, supported=True):
        if not supported: cls._supported[tuple(theme)] = bool(supported)


    @classmethod
    def AddControls(cls, *ctrls):
        """Adds wx controls to refresh on Add()."""
        cls._ctrls.update(ctrls)


    @classmethod
    def ClearCache(cls):
        """Clears generated bitmap cache."""
        cls._bitmaps.clear()


    @classmethod
    def Repr(cls, theme, supported=True, short=False):
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


    @classmethod
    def MakeBitmap(cls, theme, supported=True, border=False, label=None):
        """
        Returns a wx.Bitmap for the specified theme, with colour and brightness
        information as both text and visual.
        
        @param   supported  whether the theme is supported by hardware
        @param   border     whether to draw border around bitmap
        @param   label      label to draw underneath, if any
        """
        size = conf.ThemeBitmapSize if label is None else conf.ThemeNamedBitmapSize
        bmp = wx.Bitmap(size)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(wx.Colour(*theme[:-1])))
        dc.Clear() # Floodfill background with theme colour

        btext = "%d%%" % math.ceil(100 * (theme[-1] + 1) / conf.NormalBrightness)
        dc.SetFont(wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_BOLD, faceName="Tahoma"))
        twidth, theight = dc.GetTextExtent(btext)
        ystart = (conf.ThemeBitmapSize[1] - theight) / 2 - 4

        # Draw brightness text shadow (dark text shifted +-1px from each corner)
        dc.SetTextForeground(wx.BLACK)
        for dx, dy in [(-1, 1), (1, 1), (1, -1), (-1, -1)]:
            dc.DrawText(btext, (size[0] - twidth) / 2 + dx, ystart + dy)
            
        # Draw brightness text
        dc.SetTextForeground(wx.WHITE)
        dc.DrawText(btext, (size[0] - twidth) / 2, ystart)

        # Draw colour code on white background
        dc.SetFont(wx.Font(8, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL,
                           wx.FONTWEIGHT_BOLD, faceName="Terminal"))
        ctext = "#%2X%2X%2X" % tuple(theme[:-1])
        cwidth, cheight = dc.GetTextExtent(ctext)
        dc.Brush, dc.Pen = wx.WHITE_BRUSH, wx.WHITE_PEN
        ystart = conf.ThemeBitmapSize[1] - cheight
        dc.DrawRectangle(0, ystart - 3, *bmp.Size)
        dc.Pen = wx.LIGHT_GREY_PEN # Draw separator above colour code
        dc.DrawLine(0, ystart - 4, bmp.Size[0], ystart - 4)
        dc.SetTextForeground(wx.BLACK if supported else wx.RED)
        dc.DrawText(ctext, (bmp.Size[0] - cwidth) / 2 - 1, ystart - 1)
        dc.DrawLine(0, ystart + cheight, bmp.Size[0], ystart + cheight)

        if border: # Draw outer border
            dc.Brush, dc.Pen = wx.TRANSPARENT_BRUSH, wx.LIGHT_GREY_PEN
            dc.DrawRectangle(0, 0, *bmp.Size)

        if not supported: # Draw unsupported cross-through
            dc.Pen = wx.RED_PEN
            dc.DrawLine(0, 0, *conf.ThemeBitmapSize)
            dc.DrawLine(0, conf.ThemeBitmapSize[1], size[0], 0)

        if label is not None:
            ystart, ystop = conf.ThemeBitmapSize[1], conf.ThemeNamedBitmapSize[1]
            dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                               wx.FONTWEIGHT_BOLD, faceName="Arial"))
            dc.Brush = wx.Brush(ColourManager.GetColour(wx.SYS_COLOUR_WINDOW))
            dc.Pen   = wx.Pen(ColourManager.GetColour(wx.SYS_COLOUR_WINDOW))
            dc.DrawRectangle(0, ystart, size[0], ystop)

            text = text0 = label
            (tw, th), cut = dc.GetTextExtent(text), 0
            while tw > size[0]: # Ellipsize from the beginning until text fits
                cut += 1
                text = ".." + text0[cut:]
                tw, th = dc.GetTextExtent(text)
            dc.SetTextForeground("#7D7D7D") # Same as hard-coded in ThumbnailCtrl
            dc.DrawText(text, (size[0] - tw) / 2, ystart)

        del dc
        return bmp


    def LoadThumbnail(self, filename, thumbnailsize=None):
        """Hook for ThumbnailCtrl, returns (wx.Image, (w, h), hasAlpha)."""
        name = os.path.basename(filename) # ThumbnailCtrl gives absolute paths
        if name not in self._themes: return wx.NullImage, (0, 0), False

        args = {}
        if thumbnailsize == conf.ThemeNamedBitmapSize: args["label"] = name
        img = self.GetBitmap(name, **args).ConvertToImage()
        return img, img.GetSize(), img.HasAlpha()


    def HighlightImage(self, img, factor):
        """Hook for ThumbnailCtrl, returns unchanged img."""
        return img



class KEYS(object):
    """Keycode groupings, includes numpad keys."""
    UP         = wx.WXK_UP,       wx.WXK_NUMPAD_UP
    DOWN       = wx.WXK_DOWN,     wx.WXK_NUMPAD_DOWN
    LEFT       = wx.WXK_LEFT,     wx.WXK_NUMPAD_LEFT
    RIGHT      = wx.WXK_RIGHT,    wx.WXK_NUMPAD_RIGHT
    PAGEUP     = wx.WXK_PAGEUP,   wx.WXK_NUMPAD_PAGEUP
    PAGEDOWN   = wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN
    ENTER      = wx.WXK_RETURN,   wx.WXK_NUMPAD_ENTER
    INSERT     = wx.WXK_INSERT,   wx.WXK_NUMPAD_INSERT
    DELETE     = wx.WXK_DELETE,   wx.WXK_NUMPAD_DELETE
    HOME       = wx.WXK_HOME,     wx.WXK_NUMPAD_HOME
    END        = wx.WXK_END,      wx.WXK_NUMPAD_END
    SPACE      = wx.WXK_SPACE,    wx.WXK_NUMPAD_SPACE
    BACKSPACE  = wx.WXK_BACK,
    TAB        = wx.WXK_TAB,      wx.WXK_NUMPAD_TAB
    ESCAPE     = wx.WXK_ESCAPE,

    ARROW      = UP + DOWN + LEFT + RIGHT
    PAGING     = PAGEUP + PAGEDOWN
    NAVIGATION = ARROW + PAGING + HOME + END + TAB
    COMMAND    = ENTER + INSERT + DELETE + SPACE + BACKSPACE + ESCAPE



def make_colour_bitmap(colour, size=(16, 16)):
    """Returns a rounded wx.Bitmap filled with specified colour."""
    bmp = wx.Bitmap(size)
    dc = wx.MemoryDC(bmp)
    dc.Background = wx.TRANSPARENT_BRUSH
    dc.Clear()

    dc.Brush, dc.Pen = wx.Brush(colour), wx.Pen(colour)
    dc.DrawRectangle(1, 1, size[0] - 2, size[1] - 2)

    pts = (1, 1), (1, size[1] - 2), (size[0] - 2, 1), (size[0] - 2, size[1] - 2)
    dc.Pen = wx.TRANSPARENT_PEN if "nt" == os.name else \
             wx.Pen(ColourManager.GetColour(wx.SYS_COLOUR_WINDOW))
    dc.DrawPointList(pts)

    del dc
    bmp.SetMaskColour(wx.TRANSPARENT_PEN.Colour)
    return bmp



if __name__ == '__main__':
    warnings.simplefilter("ignore", UnicodeWarning)
    app = NightFall(redirect=0) # stdout and stderr redirected to wx popup
    locale = wx.Locale(wx.LANGUAGE_ENGLISH) # Avoid dialog buttons in native language
    app.MainLoop()
