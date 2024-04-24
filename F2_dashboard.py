import os, sys
from sys import exit
from epics import caput, caget
from time import sleep
from socket import gethostname

import pydm
from pydm import Display
from pydm.widgets.label import PyDMLabel
from pydm.widgets.frame import PyDMFrame
from pydm.widgets.base import PyDMWidget
from pydm.widgets.channel import PyDMChannel
from pydm.widgets.byte import PyDMByteIndicator

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QHBoxLayout, QWidget, QFrame, QPushButton
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont

SELF_PATH = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(*os.path.split(SELF_PATH)[:-1])
sys.path.append(REPO_ROOT)

from F2_pytools.widgets import SCPSteeringToggleButton

FONT_CTRL_REG  = STAT_BOLD = QFont('Sans Serif', 10)
FONT_CTRL_BOLD = STAT_BOLD = QFont('Sans Serif', 10, QFont.Bold)

PV_MPS_UNLATCH = 'IOC:SYS1:MP01:UNLATCHALL'

PV_FB_CONTROL = 'SIOC:SYS1:ML00:AO856'
PV_FB_STATUS  = 'SIOC:SYS1:ML00:AO859'
I_DL10E  = 0
I_BC11E  = 2
I_BC11BL = 3
I_BC14E  = 1
I_BC14BL = 5
I_BC20E  = 4

# stupid magic numbers because I can't find a FBCK HSTA bit decoder
HSTA_FBCK_ON = 268601505
HSTA_FBCK_COMP = 268599457

STYLE_GREEN = """
PyDMLabel[alarmSensitiveBorder="true"][alarmSeverity="0"] {
  color: rgb(80,200,120);
  border-color: rgb(80,255,120);
  border-width: 2px;
  border-style: solid;
}

PyDMLabel[alarmSensitiveBorder="true"][alarmSeverity="1"] {
  color: rgb(192,192,0);
  border-color: rgb(255,255,0);
  border-width: 2px;
  border-style: solid;
}
"""
STYLE_YELLOW = """
PyDMLabel[alarmSensitiveBorder="true"][alarmSeverity="0"] {
  color: rgb(192,192,0);
  border-color: rgb(255,255,0);
  border-width: 2px;
  border-style: solid;
}

PyDMLabel[alarmSensitiveBorder="true"][alarmSeverity="1"] {
  color: rgb(192,192,0);
  border-color: rgb(255,255,0);
  border-width: 2px;
  border-style: solid;
}
"""

STYLE_TEXT_GREEN = """
color: rgb(0,255,0);
"""

STYLE_TEXT_RED = """
color: rgb(255,0,0);
"""

STYLE_TEXT_WHITE = """
color: rgb(255,255,255);
"""

ACR_WORKSTATIONS = [
    'opi20',
    'opi21',
    'opi22',
    'opi23',
    ]

STYLE_BRD_GREEN = """
QFrame{
border-color: rgb(80,255,120);
border-width: 2px;
border-style: solid;
}
"""

STYLE_BRD_RED = """
QFrame{
border-color: rgb(220,0,0);
border-width: 2px;
border-style: solid;
}
"""

class F2_dashboard(Display):

    def __init__(self, parent=None, args=None):
        super(F2_dashboard, self).__init__(parent=parent, args=args)

        toggle_DL10E  = F2FeedbackToggle(bit_ID=I_DL10E,  parent=self.ui.cont_DL10E)
        toggle_BC11E  = F2FeedbackToggle(bit_ID=I_BC11E,  parent=self.ui.cont_BC11E)
        toggle_BC11BL = F2FeedbackToggle(bit_ID=I_BC11BL, parent=self.ui.cont_BC11BL)
        toggle_BC14E  = F2FeedbackToggle(bit_ID=I_BC14E,  parent=self.ui.cont_BC14E)
        toggle_BC14BL = F2FeedbackToggle(bit_ID=I_BC14BL, parent=self.ui.cont_BC14BL)
        toggle_BC20E  = F2FeedbackToggle(bit_ID=I_BC20E,  parent=self.ui.cont_BC20E)

        self.ui.mit_FC01.setFont(FONT_CTRL_BOLD)
        self.ui.mit_TD11.setFont(FONT_CTRL_BOLD)
        self.ui.mit_gunRF.setFont(FONT_CTRL_BOLD)
        self.ui.mit_laser.setFont(FONT_CTRL_BOLD)

        for plot in [
            self.ui.plot_DL10, self.ui.plot_BC11,
            self.ui.plot_BC14,self.ui.plot_BC20
            ]:
            plot.hideAxis('bottom')

        ctl_LI11 = SCPSteeringToggleButton(micro='LI11', parent=self.ui.cont_LI11FB)
        ctl_LI18 = SCPSteeringToggleButton(micro='LI18', parent=self.ui.cont_LI18FB)
        ctl_LI11.setGeometry(0,0,92,26)
        ctl_LI18.setGeometry(0,0,92,26)

        if gethostname() not in ACR_WORKSTATIONS:
            self.ui.start_matlab_server.setEnabled(False)
            self.ui.start_matlab_server.setStyleSheet("color:rgba(255,255,255,120);")

        return

    def ui_filename(self):
        return os.path.join(SELF_PATH, 'F2_dashboard.ui')

class F2SteeringFeedbackIndicator(PyDMLabel):
    """ checks FBCK hardware status to check for feedback enable/compute """

    def __init__(self, init_channel, parent=None, args=None):
        PyDMLabel.__init__(self, init_channel=init_channel, parent=parent)
        self.setAlignment(Qt.AlignCenter)

    def value_changed(self, new_value):
        PyDMLabel.value_changed(self, new_value)
        if new_value == HSTA_FBCK_ON:    
            self.setText('Enabled')
            self.setStyleSheet(STYLE_GREEN)
        elif new_value == HSTA_FBCK_COMP:
            self.setText('Compute')
            self.setStyleSheet(STYLE_YELLOW)
        else:                            
            self.setText('Off/Sample')

class F2FeedbackToggle(QFrame):
    """
    subclass to make a toggle button for F2 feedback controls
    needs to set single bits of an overall status word
    """

    def __init__(self, bit_ID, parent=None, args=None):
        QFrame.__init__(self, parent=parent)
        self.bit = bit_ID
        self.toggle_on = QPushButton('ON')
        self.toggle_off = QPushButton('OFF')

        self.setStyleSheet(STYLE_BRD_GREEN)

        self.FB_state = PyDMChannel(address=PV_FB_CONTROL, value_slot=self.set_button_enable_states)
        self.FB_state.connect()

        self.toggle_on.clicked.connect(self.enable_fb)
        self.toggle_off.clicked.connect(self.disable_fb)

        self.toggle_on.setFixedWidth(50)
        self.toggle_off.setFixedWidth(50)

        L = QHBoxLayout()
        L.addWidget(self.toggle_on)
        L.addWidget(self.toggle_off)
        L.setSpacing(1)
        L.setContentsMargins(0,0,0,0)
        self.setLayout(L)

    def enable_fb(self):
        init_ctrl_state = int(caget(PV_FB_CONTROL))
        new_ctrl_state = init_ctrl_state | (1 << self.bit)
        caput(PV_FB_CONTROL, new_ctrl_state)

    def disable_fb(self):
        init_ctrl_state = int(caget(PV_FB_CONTROL))
        new_ctrl_state = init_ctrl_state & ~(1 << self.bit)
        caput(PV_FB_CONTROL, new_ctrl_state)

    def set_button_enable_states(self, new_value):
        feedback_on = (int(abs(new_value)) >> (self.bit)) & 1

        on_style = STYLE_TEXT_GREEN if feedback_on else STYLE_TEXT_WHITE
        off_style = STYLE_TEXT_RED if not feedback_on else STYLE_TEXT_WHITE

        border = STYLE_BRD_GREEN if feedback_on else STYLE_BRD_RED
        self.setStyleSheet(border)

        self.toggle_on.setDown(feedback_on)
        self.toggle_on.setEnabled(not feedback_on)
        self.toggle_on.setStyleSheet(on_style)

        self.toggle_off.setDown(not feedback_on)
        self.toggle_off.setEnabled(feedback_on)
        self.toggle_off.setStyleSheet(off_style)

