#-*- coding: utf-8 -*-
"""
A tray application that can make screen colors darker and softer during
nocturnal hours, can activate on schedule.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     15.10.2012
@modified    25.01.2022
------------------------------------------------------------------------------
"""
import copy
import datetime
import functools
import math
import os
import re
import sys
import webbrowser

import wx
import wx.adv
import wx.html
import wx.lib.agw.flatnotebook
import wx.lib.agw.gradientbutton
import wx.lib.newevent
import wx.py
try: import wx.lib.agw.scrolledthumbnail as thumbnailevents             # Py3
except ImportError: import wx.lib.agw.thumbnailctrl as thumbnailevents  # Py2

from . import conf
from . import controls
from . import gamma
from . controls import ColourManager


"""Event class and event binder for events in Dimmer."""
DimmerEvent, EVT_DIMMER = wx.lib.newevent.NewEvent()


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

        self.current_theme = conf.NormalTheme # Applied colour theme
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
                         or isinstance(v, text_types) and isinstance(v0, text_types))

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
        if conf.UnsavedName and not conf.UnsavedTheme \
        and conf.UnsavedName not in conf.Themes:
            conf.UnsavedName = None
        if not conf.UnsavedName and not conf.UnsavedTheme and conf.Themes:
            conf.UnsavedName = sorted(conf.Themes, key=lambda x: x.lower())[0]
        conf.ScheduleEnabled = bool(conf.ScheduleEnabled)
        conf.ManualEnabled   = bool(conf.ManualEnabled)
        for n in (x for x in conf.OptionalFileDirectives if x != "UnsavedTheme"):
            if not is_var_valid(n): setattr(conf, n, conf.Defaults[n])

        if not isinstance(conf.Schedule, list) \
        or len(conf.Schedule) != len(conf.Defaults["Schedule"]) \
        or any(g not in [True, False] for g in conf.Schedule):
            conf.Schedule = conf.Defaults["Schedule"][:]
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

        if ThemeImaging.IsSupported(theme) is False:
            result = False
        elif conf.FadeSteps > 0 and fade and theme != self.current_theme:
            self.fade_steps = conf.FadeSteps
            self.fade_target_theme = theme[:]
            self.fade_current_theme = list(map(float, self.current_theme))
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
            result = bool(conf.Schedule[int(t.hour * H_MUL + t.minute / M_DIV)])
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
            current_theme = list(map(int, map(round, self.fade_current_theme)))
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
        self.theme_original    = None  # Original values of theme selected in editor
        self.frame = frame = self.create_frame()

        frame.Bind(wx.EVT_CHECKBOX, self.on_toggle_schedule, frame.cb_schedule)
        frame.Bind(thumbnailevents.EVT_THUMBNAILS_SEL_CHANGED,
            self.on_select_list_themes, frame.list_themes)
        frame.Bind(thumbnailevents.EVT_THUMBNAILS_DCLICK,
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

        frame.Bind(controls.EVT_TIME_SELECTOR, self.on_change_schedule)
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
            dim, sch = (False if i < 2 else True), (True if i % 2 else False)
            self.TRAYICONS[dim][sch] = wx.Icon(wx.Bitmap(f))
        trayicon = self.trayicon = wx.adv.TaskBarIcon()
        self.set_tray_icon(self.TRAYICONS[False][False])
        trayicon.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_toggle_dimming_tray)
        trayicon.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN,   self.on_lclick_tray)
        trayicon.Bind(wx.adv.EVT_TASKBAR_RIGHT_DOWN,  self.on_open_tray_menu)

        self.theme_original = conf.UnsavedTheme or conf.Themes.get(conf.UnsavedName)
        self.populate(init=True)
        frame.notebook.SetSelection(1); frame.notebook.SetSelection(0) # Layout hack
        self.dimmer.start()
        if conf.StartMinimizedParameter not in sys.argv:
            self.frame_move_ignore = True # Skip first move event on Show()
            frame.Show()
        wx.CallAfter(lambda: frame and self.populate_suspend)


    def InitLocale(self):
        """Override wx.App.InitLocale() to avoid dialogs in native language."""
        self.ResetLocale()
        if "win32" == sys.platform:  # Avoid dialog buttons in native language
            mylocale = wx.Locale(wx.LANGUAGE_ENGLISH_US, wx.LOCALE_LOAD_DEFAULT)
            mylocale.AddCatalog("wxstd")
            self._initial_locale = mylocale  # Override wx.App._initial_locale


    def on_dimmer_event(self, event):
        """Handler for all events sent from Dimmer, updates UI state."""
        topic, data = event.Topic, event.Data
        if "THEME FAILED" == topic:
            for c in self.frame.combo_themes, self.frame.combo_editor:
                c.Refresh()
            self.frame.label_error.Label = "Setting unsupported by hardware."
            self.frame.label_error.Show()
            self.frame.label_error.ContainingSizer.Layout()
            self.frame.label_error.Wrap(self.frame.label_error.Size[0])
        elif "MANUAL TOGGLED" == topic:
            self.frame.cb_manual.Value = data
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
            self.populate_suspend()
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
            self.populate_suspend()
        elif "SUSPEND TOGGLED" == topic:
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
            self.populate_suspend()
        elif "STARTUP TOGGLED" == topic:
            self.frame.cb_startup.Value = data
        elif "STARTUP POSSIBLE" == topic:
            self.frame.panel_startup.Show(data)
            self.frame.panel_startup.ContainingSizer.Layout()
        elif "MANUAL IN EFFECT" == topic:
            dimming = not conf.SuspendedUntil
            self.set_tray_icon(self.TRAYICONS[dimming][conf.ScheduleEnabled])
            self.skip_notification = False
            self.populate_suspend()
        elif "NORMAL DISPLAY" == topic:
            self.set_tray_icon(self.TRAYICONS[False][conf.ScheduleEnabled])
            self.skip_notification = False
            self.populate_suspend()
        elif topic in ("THEME APPLIED", "THEME CHANGED"):
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
        return None


    def set_tray_icon(self, icon):
        """Sets the icon into tray and sets a configured tooltip."""
        self.trayicon.SetIcon(icon, conf.TrayTooltip)


    def on_select_list_themes(self, event):
        """Handler for selecting a theme in list, toggles buttons enabled."""
        event.Skip()
        lst = self.frame.list_themes
        enabled = (0 <= lst.GetSelection() < lst.GetItemCount())
        self.frame.button_apply.Enabled  = enabled
        self.frame.button_delete.Enabled = enabled


    def on_apply_list_themes(self, event=None):
        """Applies the colour theme selected in list."""
        cmb, lst = self.frame.combo_themes, self.frame.list_themes
        selected = lst.GetSelection()
        if not (0 <= selected < lst.GetItemCount()): return

        name = lst.GetItemValue(selected)
        conf.ThemeName = name
        conf.save()
        if not self.dimmer.should_dim(): self.dimmer.toggle_manual(True)
        self.dimmer.toggle_suspend(False)
        self.dimmer.set_theme(conf.Themes[name], fade=True)
        self.populate()


    def on_select_combo_themes(self, event):
        """Handler for selecting an item in schedule combobox."""
        name = self.frame.combo_themes.GetItemValue(event.Selection)
        theme = conf.Themes.get(name, conf.UnsavedTheme)
        conf.ThemeName = name if event.Selection or not conf.UnsavedTheme else None
        self.dimmer.toggle_suspend(False)
        self.dimmer.set_theme(theme, fade=True)


    def on_select_combo_editor(self, event):
        """Handler for selecting an item in editor combobox."""
        name = self.frame.combo_editor.GetItemValue(event.Selection)
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
            ThemeImaging.Remove(self.unsaved_name())
            conf.UnsavedTheme = None

        theme = conf.Themes.get(name, conf.UnsavedTheme)
        self.theme_original = theme
        conf.UnsavedName = name
        conf.UnsavedTheme = None if name in conf.Themes else theme
        if self.dimmer.should_dim():
            conf.ThemeName = name
            self.dimmer.toggle_suspend(False)
            self.dimmer.set_theme(theme, fade=True)
        conf.save()
        self.populate()


    def on_change_theme_slider(self, event):
        """Handler for a change in theme component slider."""
        theme = []
        for s in self.frame.sliders:
            new = isinstance(event, wx.ScrollEvent) and s is event.EventObject
            value = event.GetPosition() if new else s.GetValue()
            s.ToolTip = str(value)
            theme.append(value)
        if theme == conf.UnsavedTheme: return

        conf.UnsavedTheme = theme
        if self.dimmer.should_dim():
            conf.ThemeName = None
            self.dimmer.toggle_suspend(False)
            self.dimmer.set_theme(theme)
        self.populate()


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

        if theme == conf.Themes.get(name): # No change from saved
            if conf.UnsavedTheme: # Had changes before
                ThemeImaging.Remove(self.unsaved_name())
                conf.UnsavedTheme = None
                conf.save()
            self.populate()
            return

        theme_existed = name in conf.Themes
        if theme_existed and wx.OK != self.modal(wx.MessageBox,
            'Theme "%s" already exists, are you sure you want to overwrite it?' % name,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        ThemeImaging.Remove(self.unsaved_name())
        conf.Themes[name] = self.theme_original = theme
        conf.UnsavedName, conf.UnsavedTheme = name, None
        if not conf.ThemeName: conf.ThemeName = name
        conf.save()
        self.populate()


    def on_reset_theme(self, event=None):
        """Resets the currently set rgb+brightness values in theme editor."""
        if not conf.UnsavedTheme: return

        theme0 = None if conf.UnsavedName in conf.Themes else self.theme_original
        conf.UnsavedTheme = theme0

        if self.dimmer.should_dim():
            name2 = conf.UnsavedName if conf.UnsavedName in conf.Themes else None
            if not conf.ThemeName: conf.ThemeName = name2
            theme2 = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
            self.dimmer.toggle_suspend(False)
            self.dimmer.apply_theme(theme2, fade=False)
        conf.save()
        self.populate()


    def on_delete_theme(self, event=None):
        """Deletes the stored theme on confirm."""
        lst = self.frame.list_themes
        selected = lst.GetSelection()
        if not (0 <= selected < lst.GetItemCount()): return
        was_focused = lst.HasFocus()

        name = lst.GetItemValue(selected)
        theme = conf.Themes[name]
        resp = self.modal(wx.MessageBox, 'Delete theme "%s"?' % name,
                          conf.Title, wx.OK | wx.CANCEL | wx.ICON_WARNING)
        if was_focused: lst.SetFocus()
        if wx.OK != resp: return

        conf.Themes.pop(name, None)
        ThemeImaging.Remove(name)
        was_current = (conf.ThemeName == name)

        if was_current:
            if self.dimmer.should_dim_scheduled():
                self.dimmer.toggle_schedule(False)
            if self.dimmer.should_dim():
                self.dimmer.toggle_manual(False)
            conf.ThemeName = None
            if conf.Themes:
                items = sorted(conf.Themes, key=lambda x: x.lower())
                conf.ThemeName = items[max(0, min(selected, len(items) - 1))]
        if conf.ThemeName and conf.UnsavedName == name and not conf.UnsavedTheme:
            conf.UnsavedName = conf.ThemeName
            self.theme_original = conf.Themes.get(conf.ThemeName)

        if not conf.Themes and not conf.UnsavedTheme:
            # Deleted last theme and nothing being modified: add theme as unsaved
            conf.ThemeName, conf.UnsavedName = None, name
            conf.UnsavedTheme = self.theme_original = theme
        conf.save()
        if was_current:
            self.dimmer.set_theme(conf.Themes.get(conf.ThemeName, conf.UnsavedTheme))
        self.populate()


    def on_restore_themes(self, event=None):
        """Restores original themes."""
        conf.Themes.update(conf.Defaults["Themes"])
        conf.save()
        self.populate()


    def on_open_tray_menu(self, event=None):
        """Creates and opens a popup menu for the tray icon."""
        menu = wx.Menu()

        def on_apply_theme(name, theme, event):
            conf.ThemeName = name if name != self.unsaved_name() else None
            if not self.dimmer.should_dim(): self.dimmer.toggle_manual(True)
            conf.save()
            self.dimmer.toggle_suspend(False)
            self.dimmer.set_theme(theme, fade=True)
            self.populate()

        def on_suspend_interval(interval, event):
            if not event.IsChecked():
                self.on_toggle_suspend()
                return

            self.suspend_interval = interval
            conf.SuspendedUntil = dt + datetime.timedelta(minutes=interval)
            self.populate_suspend()


        item = wx.MenuItem(menu, -1, "Apply &now", kind=wx.ITEM_CHECK)
        item.Font = self.frame.Font.Bold()
        menu.Append(item)
        item.Check(self.dimmer.should_dim() and not self.dimmer.should_dim_scheduled())
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
                accels = set()
                for x in conf.SuspendIntervals:
                    accel = next((str(x).replace(c, "&" + c, 1) for c in str(x)
                                  if c not in accels), "&%s" % x)
                    accels.add(accel[accel.index("&") + 1])
                    label = "%s minutes (until %s)" % \
                            (accel, (dt + datetime.timedelta(minutes=x)).strftime("%H:%M"))
                    item = menu_intervals.Append(-1, label, kind=wx.ITEM_CHECK)
                    item.Check(x == self.suspend_interval)
                    handler = functools.partial(on_suspend_interval, x)
                    menu.Bind(wx.EVT_MENU, handler, id=item.GetId())
                label = conf.SuspendedTemplate % conf.SuspendedUntil.strftime("%H:%M")
                menu.Append(-1, label.replace("u", "&u", 1), menu_intervals)
            else:
                label = conf.SuspendOnLabel.strip().replace("u", "&u", 1)
                label = re.sub(r"\s+", " ", label)
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
            item.Check(name == conf.ThemeName or
                       name == self.unsaved_name() and not conf.ThemeName)
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
        if not event.HasModifiers() and event.KeyCode in controls.KEYS.ESCAPE:
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
        self.suspend_interval = None if conf.SuspendedUntil else \
                                conf.DefaultSuspendInterval
        self.skip_notification = bool(event and conf.SuspendedUntil)
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
        do_dim = not self.dimmer.should_dim() or bool(conf.SuspendedUntil)
        if do_dim and conf.SuspendedUntil:
            self.dimmer.toggle_suspend(False)
        elif do_dim and self.dimmer.should_dim_scheduled(flag=True):
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
            self.dimmer.toggle_suspend(False)
            return

        if not conf.SuspendedUntil: # Already unsuspended while dialog open
            self.dimmer.toggle_suspend(True)
        self.suspend_interval = interval
        conf.SuspendedUntil = dt2
        self.populate_suspend()


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
        selector_time = controls.ClockSelector(panel_config, centericon=conf.ClockIcon)
        frame.selector_time = selector_time
        frame.label_combo = wx.StaticText(panel_config, label="Colour theme:")

        combo_themes = controls.BitmapComboBox(panel_config, bitmapsize=conf.ThemeNamedBitmapSize,
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
        frame.button_suspend = wx.Button(panel_config, label=conf.SuspendOnLabel)
        frame.button_suspend.ToolTip = conf.SuspendOnToolTip
        if "\n" in conf.SuspendOnLabel:
            sz = ( -1, frame.button_suspend.CharHeight * 2 + 9) if "nt" == os.name else \
                 (140, frame.button_suspend.BestSize[1])
            frame.button_suspend.Size = frame.button_suspend.MinSize = sz
        panel_startup = frame.panel_startup = wx.Panel(panel_config)
        frame.cb_startup = wx.CheckBox(panel_startup, label="Run at startup")
        frame.cb_startup.ToolTip = "Add %s to startup programs" % conf.Title

        sizer_middle.Add(selector_time, proportion=2, border=5, flag=wx.GROW | wx.ALL)
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
        sizer_middle.Add(sizer_right, proportion=1, border=5, flag=wx.BOTTOM | wx.GROW)
        panel_config.Sizer.Add(sizer_middle, proportion=1, border=5, flag=wx.GROW | wx.ALL)


        # Create saved themes page
        list_themes = controls.BitmapListCtrl(panel_themes, imagehandler=ThemeImaging)
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
            else: bmp1, bmp2 = map(wx.Bitmap, conf.BrightnessIcons)
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

        combo_editor = controls.BitmapComboBox(panel_editor, bitmapsize=conf.ThemeNamedBitmapSize,
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


    def populate_suspend(self):
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


    def populate(self, init=False):
        """Populates controls from configuration data."""
        cmb, cmb2 = self.frame.combo_themes, self.frame.combo_editor
        lst = self.frame.list_themes
        states = {cmb:  {"Value": conf.ThemeName or self.unsaved_name()},
                  cmb2: {"Value": self.unsaved_name() if conf.UnsavedTheme else
                                  conf.UnsavedName},
                  lst:  {"Value": conf.ThemeName} if init else
                        {"Selection": lst.GetSelection(), "Value": lst.Value}}

        for name, theme in conf.Themes.items():
            ThemeImaging.Add(name, theme)
        if conf.UnsavedTheme:
            ThemeImaging.Add(self.unsaved_name(), conf.UnsavedTheme)

        items = sorted(conf.Themes, key=lambda x: x.lower())
        citems = ([self.unsaved_name()] if conf.UnsavedTheme else []) + items

        self.frame.Freeze()
        try:
            for ctrl in cmb, cmb2, lst:
                ctrl.SetItems(citems if isinstance(ctrl, controls.BitmapComboBox) else items)
                idx = ctrl.FindItem(states[ctrl]["Value"])
                if idx < 0 and "Selection" in states[ctrl]:
                    idx = min(states[ctrl]["Selection"], ctrl.GetItemCount() - 1)
                if idx >= 0:
                    ctrl.SetSelection(idx)
                    if isinstance(ctrl, controls.BitmapComboBox):
                        theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
                        ctrl.ToolTip = ThemeImaging.Repr(theme)

            btnenabled = (0 <= lst.GetSelection() < lst.GetItemCount())
            for b in self.frame.button_apply, self.frame.button_delete:
                b.Enabled = btnenabled
            restorable = any(conf.Themes.get(k) != v
                             for k, v in conf.Defaults["Themes"].items())
            self.frame.button_restore.Shown = restorable
            self.frame.button_restore.ContainingSizer.Layout()

            theme = conf.UnsavedTheme or conf.Themes.get(cmb2.Value)
            for s, v in zip(self.frame.sliders, theme) if theme else ():
                s.Value, s.ToolTip = v, str(v)
        finally: self.frame.Thaw()



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
            if not target.lower().endswith(("exe", "bat", "cmd")):
                # pythonw leaves no DOS window open
                python = sys.executable.replace("python.exe", "pythonw.exe")
                shortcut.Targetpath = '"%s"' % python
                shortcut.Arguments = "-m %s %s" % (target, conf.StartMinimizedParameter)
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
    _supported = {} # {theme: False, }


    @classmethod
    def Add(cls, name, theme):
        """Registers or overwrites theme data, clears cached bitmap if changed."""
        if theme == cls._themes.get(name): return

        cls._themes[name] = theme
        cls._bitmaps.pop(name, None)


    @classmethod
    def MarkSupported(cls, theme, supported=True):
        """Marks theme supported or unsupported, clears cached bitmap if changed."""
        key = tuple(theme)
        supported = supported if supported is None else bool(supported)
        if supported == cls._supported.get(key) \
        or key not in cls._supported and supported is not False: return

        if supported is False: cls._supported[key] = supported
        else: cls._supported.pop(key, None)
        for n, t in cls._themes.items():
            if t == theme: cls._bitmaps.pop(n, None)


    @classmethod
    def Remove(cls, name):
        """Unregisters theme data."""
        for d in cls._bitmaps, cls._themes: d.pop(name, None)


    @classmethod
    def GetBitmap(cls, name, border=False, label=None):
        """Returns bitmap for named theme, using cache if possible."""
        theme, args = cls._themes[name], dict(border=border, label=label)
        if cls._supported.get(tuple(theme)) is False:
            args["supported"] = False
        cls._bitmaps.setdefault(name, {})
        key = tuple((k, bool(v)) for k, v in args.items() if v)
        if key not in cls._bitmaps[name]:
            bmp = cls.MakeBitmap(theme, **args)
            cls._bitmaps[name][key] = bmp
        return cls._bitmaps[name][key]


    @classmethod
    def IsSupported(cls, theme):
        """Returns False if theme has been marked as not supported, else None."""
        return cls._supported.get(tuple(theme))


    @classmethod
    def Repr(cls, theme, short=False):
        """Returns a readable string representation of the theme."""
        btext = "%d%%" % math.ceil(100 * (theme[-1] + 1) / conf.NormalBrightness)
        if short:
            result = "%s #%2X%2X%2X" % ((btext, ) + tuple(theme[:3]))
        else:
            result = "%s brightness.\n%s" % (btext,
                     ", ".join("%s at %d%%" % (s, theme[i] / 255. * 100)
                               for i, s in enumerate(("Red", "green", "blue"))))
            if cls._supported.get(tuple(theme)) is False:
                result += "\n\nNot supported by hardware."
        return result


    @classmethod
    def ClearCache(cls):
        """Clears all generated bitmaps."""
        cls._bitmaps.clear()


    @staticmethod
    def MakeBitmap(theme, supported=True, border=False, label=None):
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


    def Load(self, filename, thumbnailsize=None):
        """Hook for ThumbnailCtrl, returns (wx.Image, (w, h), hasAlpha)."""
        name = os.path.basename(filename) # ThumbnailCtrl gives absolute paths
        if name not in self._themes: return wx.NullImage, (0, 0), False

        args = {}
        if thumbnailsize == conf.ThemeNamedBitmapSize: args["label"] = name
        img = self.GetBitmap(name, **args).ConvertToImage()
        return img, img.GetSize(), img.HasAlpha()


    def LoadThumbnail(self, filename, thumbnailsize=None):
        """Hook for ThumbnailCtrl, returns (wx.Image, (w, h), hasAlpha)."""
        return self.Load(filename, thumbnailsize)  # LoadThumbnail() is Py2


    def HighlightImage(self, img, factor):
        """Hook for ThumbnailCtrl, returns unchanged img."""
        return img



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


try: text_types = (str, unicode)       # Py2
except Exception: text_types = (str, ) # Py3
