import os
import sys
import wx
import traceback
import numpy as np
import weakref

import ifigure.widgets.dialog as dialog
import ifigure.events

from ifigure.widgets.book_viewer import FramePlus
from ifigure.utils.cbook import BuildMenu
from petram.mfem_viewer import MFEM_menus

class SimpleFramePlus(FramePlus):
    def __init__(self, parent, *args, **kargs):
        super(SimpleFramePlus, self).__init__(parent, *args, **kargs)
        self.Bind(wx.EVT_CLOSE, self.onClose)        
        wx.GetApp().add_palette(self)
        self._atable = []
        self._atable.append((wx.ACCEL_NORMAL,  wx.WXK_F2, wx.ID_BACKWARD))
        self._atable.append((wx.ACCEL_NORMAL,  wx.WXK_F1, wx.ID_FORWARD))   
        atable = wx.AcceleratorTable(self._atable)
        self.SetAcceleratorTable(atable)

        # need to remove self from table 
        tw = wx.GetApp().TopWindow
        tw.windowlist.remove_item(self)

        #self.Bind(wx.EVT_MENU, lambda evt: frame.ProcessEvent(evt))
        extra_menu = wx.Menu()  
        self.menuBar.Insert(self.menuBar.GetMenuCount(), extra_menu,"MFEM")
        menus = MFEM_menus(parent)
        ret = BuildMenu(extra_menu, menus)
        if not "wxMac" in wx.PlatformInfo:        
            self.SetMenuBar(None)
        
    def onResize(self, evt):
        evt.Skip()

    def onActivate(self, evt):
        pass

    def onUpdateUI(self, evt):
        pass
        
    def onClose(self, evt):
        wx.GetApp().rm_palette(self)
        self.Destroy()
        evt.Skip()
