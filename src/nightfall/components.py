#-*- coding: utf-8 -*-
"""
Separable components for application.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     25.01.2022
@modified    26.01.2022
------------------------------------------------------------------------------
"""
import copy
import datetime
import math
import os
import sys

import wx
import wx.lib.newevent

from . import conf
from . import gamma
from . import images
from . controls import BitmapComboBox, ColourManager


"""Event class and event binder for events in Dimmer."""
DimmerEvent, EVT_DIMMER = wx.lib.newevent.NewEvent()

"""Event class and event binder for events in ThemeEditor."""
ThemeEditorEvent, EVT_THEME_EDITOR = wx.lib.newevent.NewEvent()


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
            if isinstance(v, (list, tuple)) and isinstance(v0, (list, tuple)):
                return len(v) == len(v0) and all(isinstance(a, type(b)) for a, b in zip(v, v0))
            return isinstance(v, type(v0)) \
                   or isinstance(v, text_types) and isinstance(v0, text_types)

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
            msg = ("MANUAL IN EFFECT", "SCHEDULE IN EFFECT")[self.should_dim_scheduled()]
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
            msg = ("MANUAL IN EFFECT", "SCHEDULE IN EFFECT")[self.should_dim_scheduled()]
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
            msg = ("MANUAL IN EFFECT", "SCHEDULE IN EFFECT")[self.should_dim_scheduled()]
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
            msg = ("MANUAL IN EFFECT", "SCHEDULE IN EFFECT")[self.should_dim_scheduled()]
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
            msg = ("MANUAL IN EFFECT", "SCHEDULE IN EFFECT")[self.should_dim_scheduled()]
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



class ThemeEditor(wx.Panel):
    """Theme editor component, with value sliders and theme management."""


    def __init__(self, parent, dimmer, style=0):
        """
        @param   dimmer  instance of Dimmer
        """
        super(ThemeEditor, self).__init__(parent, style=style)

        self.dimmer         = dimmer
        self.sliders        = []    # [wx.Slider] for brightness-r-g-b
        self.theme_original = None  # Original values of theme selected in editor
        self.modal_wrapper  = lambda f, *a, **kw: f(*a, **kw)

        self.Sizer  = wx.BoxSizer(wx.VERTICAL)
        sizer_bar   = wx.BoxSizer(wx.HORIZONTAL)
        sizer_right = wx.BoxSizer(wx.VERTICAL)

        sizer_sliders = wx.FlexGridSizer(rows=4, cols=3, vgap=2, hgap=5)
        sizer_sliders.AddGrowableCol(1, proportion=1)
        kws = dict(red=0, green=0, blue=0)
        for i, text in enumerate(["brightness", "red", "green", "blue"]):
            if i: bmp1, bmp2 = [make_colour_bitmap(wx.Colour(**dict(kws, **{text: x})))
                                for x in conf.ValidColourRange]
            else: bmp1, bmp2 = images.Brightness_Low.Bitmap, images.Brightness_High.Bitmap
            sbmp1 = wx.StaticBitmap(self, bitmap=bmp1)
            sbmp2 = wx.StaticBitmap(self, bitmap=bmp2)
            slider = wx.Slider(self, size=(-1, 20),
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
            self.sliders.append(slider)
        self.sliders.append(self.sliders.pop(0)) # Make brightness first

        combo_editor = BitmapComboBox(self, bitmapsize=conf.ThemeNamedBitmapSize,
                                      imagehandler=ThemeImaging)
        self.combo_editor = combo_editor
        combo_editor.SetPopupMaxHeight(200)

        sizer_tbuttons = wx.BoxSizer(wx.HORIZONTAL)
        button_save  = self.button_save  = wx.Button(self, label=" Save..")
        button_reset = self.button_reset = wx.Button(self, label="Reset")
        button_reset.MinSize = combo_editor.Size[0] / 2 - 3, -1
        button_save.MinSize  = combo_editor.Size[0] / 2 - 2, -1
        button_save.ToolTip  = "Save settings as a named theme"
        button_reset.ToolTip = "Restore original settings"

        sizer_right.Add(combo_editor,   border=5, flag=wx.TOP)
        sizer_tbuttons.Add(button_save, border=5, flag=wx.RIGHT)
        sizer_tbuttons.Add(button_reset, flag=wx.ALIGN_BOTTOM)
        sizer_right.Add(sizer_tbuttons, border=5, flag=wx.TOP)
        sizer_bar.Add(sizer_sliders, border=10, proportion=1, flag=wx.LEFT | wx.BOTTOM | wx.ALIGN_BOTTOM)
        sizer_bar.Add(sizer_right, border=5, flag=wx.ALL | wx.GROW)
        self.Sizer.Add(sizer_bar, proportion=1, flag=wx.GROW)

        self.Bind(wx.EVT_BUTTON,   self.on_save_theme,   self.button_save)
        self.Bind(wx.EVT_BUTTON,   self.on_reset_theme,  self.button_reset)
        self.Bind(wx.EVT_COMBOBOX, self.on_select_theme, self.combo_editor)

        for s in self.sliders:
            self.Bind(wx.EVT_SCROLL, self.on_change_theme_slider, s)
            self.Bind(wx.EVT_SLIDER, self.on_change_theme_slider, s)

        self.theme_original = conf.UnsavedTheme or conf.Themes.get(conf.UnsavedName)


    def GetModalWrapper(self):
        """Returns current modal dialog wrapper function."""
        return self.modal_wrapper
    def SetModalWrapper(self, wrapper):
        """Sets modal dialog wrapper function."""
        self.modal_wrapper = wrapper
    ModalWrapper = property(GetModalWrapper, SetModalWrapper)


    def Populate(self):
        """Populates editor from configuration data."""
        for name, theme in conf.Themes.items():
            ThemeImaging.Add(name, theme)
        if conf.UnsavedTheme:
            ThemeImaging.Add(self.unsaved_name(), conf.UnsavedTheme)

        items = [self.unsaved_name()] if conf.UnsavedTheme else []
        items += sorted(conf.Themes, key=lambda x: x.lower())
        value = self.unsaved_name() if conf.UnsavedTheme else conf.UnsavedName

        cmb = self.combo_editor
        self.Freeze()
        try:
            cmb.SetItems(items)
            idx = cmb.FindItem(value)
            if idx >= 0:
                cmb.SetSelection(idx)
                theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
                cmb.ToolTip = ThemeImaging.Repr(theme)

            theme = conf.UnsavedTheme or conf.Themes.get(cmb.Value)
            for s, v in zip(self.sliders, theme) if theme else ():
                s.Value, s.ToolTip = v, str(v)
        finally: self.Thaw()


    def unsaved_name(self):
        """Returns current unsaved name for display, as "name *" or " (unsaved) "."""
        if conf.UnsavedName:  return conf.ModifiedTemplate % conf.UnsavedName
        if conf.UnsavedTheme: return conf.UnsavedLabel
        return None


    def post_event(self):
        """Posts EVT_THEME_EDITOR to parent, signalling update."""
        event = ThemeEditorEvent()
        event.SetEventObject(self)
        event.SetId(self.Id)
        wx.PostEvent(self.Parent, event)


    def on_select_theme(self, event):
        """Handler for selecting an item in editor combobox."""
        name = self.combo_editor.GetItemValue(event.Selection)
        if conf.UnsavedTheme and not event.Selection: name = conf.UnsavedName

        if event.Selection and conf.UnsavedTheme \
        and conf.Themes.get(conf.UnsavedName) != conf.UnsavedTheme \
        and wx.OK != self.modal_wrapper(wx.MessageBox, 'Theme%s has changed, '
            'are you sure you want to discard changes?' %
            (' "%s"' % conf.UnsavedName if conf.UnsavedName else ""),
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ):
            self.combo_editor.SetSelection(0)
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
        self.post_event()


    def on_change_theme_slider(self, event):
        """Handler for a change in theme component slider."""
        theme = []
        for s in self.sliders:
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
        self.post_event()


    def on_save_theme(self, event=None):
        """Stores the currently set rgb+brightness values in theme editor."""
        theme = conf.UnsavedTheme or conf.Themes[conf.UnsavedName]
        name0 = name = conf.UnsavedName or ThemeImaging.Repr(theme, short=True)

        dlg = wx.TextEntryDialog(self.Parent, "Name:", conf.Title,
                                 value=name, style=wx.OK | wx.CANCEL)
        dlg.CenterOnParent()
        if wx.ID_OK != self.modal_wrapper(dlg.ShowModal): return

        name = dlg.GetValue().strip()
        if not name: return

        if theme == conf.Themes.get(name): # No change from saved
            if conf.UnsavedTheme: # Had changes before
                ThemeImaging.Remove(self.unsaved_name())
                conf.UnsavedTheme = None
                conf.save()
            self.post_event()
            return

        theme_existed = name in conf.Themes
        if theme_existed and wx.OK != self.modal_wrapper(wx.MessageBox,
            'Theme "%s" already exists, are you sure you want to overwrite it?' % name,
            conf.Title, wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        ): return

        ThemeImaging.Remove(self.unsaved_name())
        conf.Themes[name] = self.theme_original = theme
        conf.UnsavedName, conf.UnsavedTheme = name, None
        if not conf.ThemeName: conf.ThemeName = name
        conf.save()
        self.post_event()


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
        self.post_event()



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
        path = os.path.join("~", "Start Menu", "Programs", "Startup", "%s.lnk" % conf.Title)
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
            ctext = ", ".join("%s at %d%%" % (s, theme[i] / 255. * 100)
                              for i, s in enumerate(("Red", "green", "blue")))
            result = "%s brightness.\n%s" % (btext, ctext)
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
