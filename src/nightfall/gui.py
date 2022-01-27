#-*- coding: utf-8 -*-
"""
A tray application that can make screen colors darker and softer during
nocturnal hours, can activate on schedule.

------------------------------------------------------------------------------
This file is part of NightFall - screen color dimmer for late hours.
Released under the MIT License.

@author      Erki Suurjaak
@created     15.10.2012
@modified    27.01.2022
------------------------------------------------------------------------------
"""
import datetime
import functools
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

from . import components
from . import conf
from . import controls
from . import images
from . components import ThemeImaging
from . controls   import ColourManager



class NightFall(wx.App):
    """
    The NightFall application, controller managing the GUI elements 
    and communication with the dimmer model.
    """

    def __init__(self, redirect=False, filename=None,
                 useBestVisual=False, clearSigInt=True):
        super(NightFall, self).__init__(redirect, filename, useBestVisual, clearSigInt)
        self.dimmer = components.Dimmer(self)

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
        frame.Bind(wx.EVT_BUTTON,     self.on_toggle_suspend,      frame.button_suspend)
        frame.Bind(wx.EVT_COMBOBOX,   self.on_select_combo_themes, frame.combo_themes)
        frame.label_suspend.Bind(wx.html.EVT_HTML_LINK_CLICKED, self.on_change_suspend)
        frame.link_www.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                            lambda e: webbrowser.open(e.GetLinkInfo().Href))
        frame.label_about.Bind(wx.html.EVT_HTML_LINK_CLICKED,
                            lambda e: webbrowser.open(e.GetLinkInfo().Href))

        frame.Bind(controls.EVT_TIME_SELECTOR, self.on_change_schedule)
        frame.Bind(wx.EVT_CLOSE,               self.on_toggle_settings)
        frame.Bind(wx.EVT_ACTIVATE,            self.on_activate_window)
        frame.Bind(wx.EVT_MOVE,                self.on_move)
        frame.Bind(wx.EVT_CHAR_HOOK,           self.on_key)
        frame.Bind(wx.EVT_SYS_COLOUR_CHANGED,  self.on_sys_colour_change)
        self.Bind(components.EVT_DIMMER,       self.on_dimmer_event)
        self.Bind(components.EVT_THEME_EDITOR, lambda _: self.populate())
        self.Bind(wx.EVT_LEFT_DCLICK,          self.on_toggle_console, frame.label_combo)

        self.TRAYICONS = {False: {}, True: {}}
        # Cache tray icons in dicts [dimming now][schedule enabled]
        for i, img in enumerate([images.IconTray_Off, images.IconTray_Off_Scheduled,
                                 images.IconTray_On,  images.IconTray_On_Scheduled]):
            dim, sch = (False if i < 2 else True), (True if i % 2 else False)
            self.TRAYICONS[dim][sch] = img.Icon
        trayicon = self.trayicon = wx.adv.TaskBarIcon()
        self.set_tray_icon()
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
            self.frame.combo_themes.Refresh()
            self.frame.theme_editor.Refresh() # @todo vbl peab overridema
            self.frame.label_error.Label = "Setting unsupported by hardware."
            self.frame.label_error.Show()
            self.frame.label_error.ContainingSizer.Layout()
            self.frame.label_error.Wrap(self.frame.label_error.Size[0])
        elif "MANUAL TOGGLED" == topic:
            self.frame.cb_manual.Value = data
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(dimming, conf.ScheduleEnabled)
            self.populate_suspend()
        elif "SCHEDULE TOGGLED" == topic:
            self.frame.cb_schedule.Value = data
            dimming = not conf.SuspendedUntil and self.dimmer.should_dim()
            self.set_tray_icon(dimming, conf.ScheduleEnabled)
        elif "SCHEDULE CHANGED" == topic:
            self.frame.selector_time.SetSelections(data)
        elif "SCHEDULE IN EFFECT" == topic:
            dimming = not conf.SuspendedUntil
            self.set_tray_icon(dimming, True)
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
            self.set_tray_icon(dimming, conf.ScheduleEnabled)
            self.populate_suspend()
        elif "STARTUP TOGGLED" == topic:
            self.frame.cb_startup.Value = data
        elif "STARTUP POSSIBLE" == topic:
            self.frame.panel_startup.Show(data)
            self.frame.panel_startup.ContainingSizer.Layout()
        elif "MANUAL IN EFFECT" == topic:
            dimming = not conf.SuspendedUntil
            self.set_tray_icon(dimming, conf.ScheduleEnabled)
            self.skip_notification = False
            self.populate_suspend()
        elif "NORMAL DISPLAY" == topic:
            self.set_tray_icon(False, conf.ScheduleEnabled)
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


    def set_tray_icon(self, dimming=False, scheduled=False):
        """Sets the relevant icon into tray, with the configured tooltip."""
        icon = self.TRAYICONS[dimming][scheduled]
        if conf.SuspendedUntil: icon = images.IconTray_Off_Paused.Icon
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
        lst = self.frame.list_themes
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
        else:
            item = menu.Append(-1, "S&uspend")
            item.Enable(False)
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
        selector_time = controls.ClockSelector(panel_config,
                                               centericon=images.Icon48x48_32bit.Bitmap)
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

        frame.theme_editor = components.ThemeEditor(panel_editor, dimmer=self.dimmer)
        frame.theme_editor.SetModalWrapper(self.modal)

        panel_editor.Sizer.Add(text_detail, proportion=10, border=5,
            flag=wx.ALL | wx.ALIGN_CENTER_HORIZONTAL)
        panel_editor.Sizer.AddStretchSpacer()
        panel_editor.Sizer.Add(frame.theme_editor, proportion=1, flag=wx.GROW)


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

        icons = images.get_appicons()
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
        cmb, lst = self.frame.combo_themes, self.frame.list_themes
        states = {cmb:  {"Value": conf.ThemeName or self.unsaved_name()},
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
            for ctrl in (cmb, lst):
                ctrl.SetItems(citems if isinstance(ctrl, controls.BitmapComboBox) else items)
                idx = ctrl.FindItem(states[ctrl]["Value"])
                if idx < 0 and "Selection" in states[ctrl]:
                    idx = min(states[ctrl]["Selection"], ctrl.GetItemCount() - 1)
                if idx >= 0:
                    ctrl.SetSelection(idx)
                    if isinstance(ctrl, controls.BitmapComboBox):
                        theme = conf.Themes.get(conf.ThemeName, conf.UnsavedTheme)
                        ctrl.ToolTip = ThemeImaging.Repr(theme)
            self.frame.theme_editor.Populate()

            btnenabled = (0 <= lst.GetSelection() < lst.GetItemCount())
            for b in self.frame.button_apply, self.frame.button_delete:
                b.Enabled = btnenabled
            restorable = any(conf.Themes.get(k) != v
                             for k, v in conf.Defaults["Themes"].items())
            self.frame.button_restore.Shown = restorable
            self.frame.button_restore.ContainingSizer.Layout()

        finally: self.frame.Thaw()
