# -*- coding: utf-8 -*-
import sys
#sys.path.append('..')  # help python find open_bci_v3.py relative to scripts folder
from PyQt4 import QtGui, QtCore, Qt, QtOpenGL
import pyqtgraph as pg
import open_bci_v3 as bci
import logging
import cls_algo1 as clsa
import math
import numpy as np
import OpenBCI_csv_collect as OBCIcsv
import OBCI_board_simulator as OBCIsim
import ShamCrypter
import datetime
import time
import timeit
import csv
import collections
import alsaaudio
import Montage
from vispychannelview import ChannelView



class StreamToLogger(object):
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)

    def CAtoMain(self, msg):
        self.emit(QtCore.SIGNAL("updateSignalViewerSendViewer"), msg)

    def DSVWtoMain(self, msg):
        if msg[0] == "start":
            self.emit(QtCore.SIGNAL("sendCAStartStim"))
        elif msg[0] == "pause":
            self.emit(QtCore.SIGNAL("sendCAPauseStim"))
        elif msg[0] == "test":
            self.emit(QtCore.SIGNAL("sendCATestStim"))
        if msg[0] == "checkEEG":
            self.emit(QtCore.SIGNAL("sendCACheckEEG"))
        elif msg[0] == "lightsoff":
            self.emit(QtCore.SIGNAL("sendCALightsOff"))
        elif msg[0] == "lightson":
            self.emit(QtCore.SIGNAL("sendCALightsOn"))
        elif msg[0] == "reconnect":
            self.emit(QtCore.SIGNAL("sendCAReconnect"))
        elif msg[0] == "forced-stim":
            self.emit(QtCore.SIGNAL("sendCAForcedStim"))
        elif msg[0] == "auto-stim":
            self.emit(QtCore.SIGNAL("sendCAAutoStim"))
        elif msg[0] == "sound-rise-level":
            new_sound_rise_from_base_level_db = int(msg[1])
            self.emit(QtCore.SIGNAL("sendCASoundRiseLevel"), new_sound_rise_from_base_level_db)
        elif msg[0] == "EEG-channel-change":
            new_channelEEG = int(msg[1])
            self.emit(QtCore.SIGNAL("sendCAEEGchannel"), new_channelEEG)
        elif msg[0] == "update-view-refresh-interval":
            updateIntervalSeconds = float(msg[1])
            self.emit(QtCore.SIGNAL("sendCAUpdateIntervalChange"), updateIntervalSeconds)

    def getFile(self, dialogName, initFolder='', filterList='all formats (*.*)'):
        fname = QtGui.QFileDialog.getOpenFileName(self, dialogName,
                                                  initFolder, filterList)
        return fname

    def getInteger(self, dialogName, inputName, from_int, to_int, steps_int, default_int):
        i, okPressed = QtGui.QInputDialog.getInt(self, dialogName, inputName, default_int, from_int, to_int, steps_int)
        res = [i, okPressed]
        return res

    def getDouble(self, dialogName, inputName, from_double, to_double, decimals_int, default_double):
        d, okPressed = QtGui.QInputDialog.getDouble(self, dialogName, inputName, default_double, from_double, to_double, decimals_int)
        res = [d, okPressed]
        return res

    def showMessageBox(self, messageTitle, message, isWarning, isRichtext, hasAbortOption, isOKbuttonDefault=True):
        okPressed = False

        msgBox = QtGui.QMessageBox()
        msgBox.setWindowTitle(self.tr(messageTitle))
        if isRichtext:
            msgBox.setTextFormat(QtCore.Qt.RichText)

        if isWarning:
            msgBox.setIcon(QtGui.QMessageBox.Warning)

        msgBox.setText(message)
        if hasAbortOption:
            msgBox.setStandardButtons(QtGui.QMessageBox.Ok | QtGui.QMessageBox.Abort)
        else:
            msgBox.setStandardButtons(QtGui.QMessageBox.Ok)

        if isOKbuttonDefault:
            msgBox.setDefaultButton(QtGui.QMessageBox.Ok)
        elif hasAbortOption:
            msgBox.setDefaultButton(QtGui.QMessageBox.Abort)


        retvals = msgBox.exec_()

        if retvals == QtGui.QMessageBox.Ok:
            okPressed = True
        return okPressed

    def getChoice(self, dialogName, inputName, items_list, current_item_int=0):
        item, okPressed = QtGui.QInputDialog.getItem(self, dialogName, inputName, items_list, current_item_int, False)
        res = [item, okPressed]
        return res

    def getText(self, dialogName, inputName, inital_text):
        text, okPressed = QtGui.QInputDialog.getText(self, dialogName, inputName, QtGui.QLineEdit.Normal, inital_text)
        res = [text, okPressed]
        return res

class QWidget2(QtGui.QWidget):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        self.connect(self, QtCore.SIGNAL('triggered()'), self.closeEvent)

    def keyPressEvent(self, event):
        super(QWidget2, self).keyPressEvent(event)
        self.emit(QtCore.SIGNAL('keyPressedEvent'), event)

    def closeEvent(self, event):
        print("attempt to close...if confirmed...")
        quit_msg = "Are you sure you want to quit?\n\nIf you still want to continue recording on the SD card of the device\nthen plug out the dongle BEFORE you press \"Yes\" to exit."
        reply = QtGui.QMessageBox.question(self, 'Quit?',
                                           quit_msg, QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)

        if reply == QtGui.QMessageBox.Yes:
            event.accept()
            print(" accepted")
            sys.exit(0)
        else:
            event.ignore()
            print(" ignored")


class DisplaySignalFullViewWidget(QtCore.QThread):
    keyPressed = QtCore.pyqtSignal(int)
    def __init__(self, t, ys, ca, montage, board,updateSendOutDelaySeconds,doAntiAlias=True,useOpenGL=True,doDownSamplingForPlot=False,useVispyPlot=False):
        QtCore.QThread.__init__(self)
        self.updateSendOutDelaySeconds = updateSendOutDelaySeconds
        self.updateSendOutDelaySecondsAdjusted = updateSendOutDelaySeconds
        # self.lastUpdateTime = None

        self.montage = montage
        self.useVispyPlot = useVispyPlot

        self.doAntiAlias = doAntiAlias
        self.useOpenGL = useOpenGL
        self.doDownSamplingForPlot = doDownSamplingForPlot

        self.win = QWidget2()

        self.win.setAutoFillBackground(True)
        self.palette = self.win.palette()
        self.palette.setColor(self.win.backgroundRole(), QtCore.Qt.black)
        self.win.setPalette(self.palette)

        self.win.setWindowTitle('Extended GUI signal viewer - by Frederik D. Weber')

        self.layout = QtGui.QGridLayout(self.win)
        self.win.setLayout(self.layout)

        self.nDisplayChannels = len(self.montage.GUI_signalviewer_order_channelNumbers)
        self.displayChannels = self.montage.GUI_signalviewer_order_channelNumbers

        self.LabelPlots = []
        smallfont = QtGui.QFont()
        smallfont.setPointSize(6)

        for iPlot in range(0, self.nDisplayChannels):
            label = QtGui.QLabel()
            label.setFont(smallfont)
            channelNumber = self.displayChannels[iPlot]
            label.setText(self.montage.getChannelDescriptionByChannelNumber(channelNumber, ca.realTimeFilterOrder, wrap=True))
            label.setAlignment(QtCore.Qt.AlignVCenter)
            label.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
            self.LabelPlots.append(label)

        if not self.useVispyPlot:

            try:
                pg.PlotWidget(useOpenGL=self.useOpenGL)
            except Exception as e:
                print('OpenGL cannot be assured to be loaded problem')
                print(e.message)
                okpressed = main.showMessageBox("OpenGL problem",
                                                "Your System does not support OpenGL yet.\nMaybe install your graphics card driver (if available)\nError message:\n\n" + e.message + "\n\nContinue anyway or abort?",
                                                True, False, True, isOKbuttonDefault=False)
                if not okpressed:
                    sys.exit(0)

            self.plotWidgets = []
            for iPlot in range(0,self.nDisplayChannels):
                self.plotWidgets.append(pg.PlotWidget(useOpenGL=self.useOpenGL))

            for iPlot in range(0, self.nDisplayChannels):
                self.plotWidgets[iPlot].setMinimumHeight(30 if iPlot < self.nDisplayChannels-1 else 50)



            self.plots = []
            for iPlot in range(0, self.nDisplayChannels):
                self.plots.append(self.plotWidgets[iPlot].getPlotItem())



            for iPlot in range(0, self.nDisplayChannels):
                self.plots[iPlot].setDownsampling(ds=self.doDownSamplingForPlot)

            for iPlot in range(0, self.nDisplayChannels):
                # self.plots[iPlot].setTitle(title=self.montage.getChannelDescriptionByChannelNumber(channelNumber,ca.realTimeFilterOrder))

                # titleTextItem = pg.TextItem(text=self.montage.getChannelDescriptionByChannelNumber(channelNumber, ca.realTimeFilterOrder),
                #                         color=(128, 128, 128, 92),
                #                         html=None, anchor=(0, 0), border=None,
                #                         fill=None, angle=0, rotateAxis=None)
                # self.plots[iPlot].addItem(titleTextItem)
                # titleTextItem.setPos(0, 0.0)


                # legend = self.plots[iPlot].addLegend()
                # legend.addItem(None,"test")
                self.plots[iPlot].showGrid(x=True, y=True, alpha=0.30)
                self.plots[iPlot].getAxis("bottom").setTickSpacing(5.0, 1.0)

                mediumfont = QtGui.QFont()
                mediumfont.setPointSize(8)

                if iPlot != self.nDisplayChannels-1:
                    self.plots[self.nDisplayChannels-1].setXLink(self.plots[iPlot])
                    self.plots[iPlot].getAxis("bottom").setStyle(showValues=False)
                    self.plots[iPlot].getAxis("left").setStyle(tickFont=mediumfont)
                    # self.plots[iPlot].hideAxis('bottom')
                    self.plots[iPlot].hideAxis('top')
                else:
                    self.plots[iPlot].getAxis("bottom").setStyle(showValues=True)

                self.plots[iPlot].getAxis("bottom").showLabel(show=False)
                self.plots[iPlot].getAxis("top").showLabel(show=False)
                self.plots[iPlot].getAxis("right").showLabel(show=False)
                self.plots[iPlot].getAxis("left").showLabel(show=False)
                self.plots[iPlot].getAxis("left").setTickSpacing(50.0, 25.0)
                # self.plots[iPlot].getAxis("left").setLabel(axis="left", text="Filtered(Signal) [uV]")
                self.plots[iPlot].getAxis("left").getViewBox().setAutoPan(x=False, y=False)
                self.plots[iPlot].getAxis("left").getViewBox().enableAutoRange(x=False, y=False)
                self.plots[iPlot].showButtons()



            self.curves = []
            for iPlot in range(0, self.nDisplayChannels):
                self.curves.append(self.plots[iPlot].plot(pen=pg.mkPen(color=(255, 255, 255)), clear=False))

        else:
            self.channelRanges = []
            for iCh in range(0, self.nDisplayChannels):
                self.channelRanges.append((-100.0, 100.0))
            self.plot = ChannelView(self.win, self.nDisplayChannels, 30, self.channelRanges, clipChannelView=True,useAntialias=self.doAntiAlias,useOpenGL=self.useOpenGL)

        self.btnsetRangeFixedHigher = []
        self.btnsetRangeFixedLower = []
        for iPlot in range(0, self.nDisplayChannels):
            self.btnsetRangeFixedHigher.append(QtGui.QPushButton('-'))
            self.btnsetRangeFixedLower.append(QtGui.QPushButton('+'))


        temp_button_width = 20
        temp_button_heigth = 10

        for iPlot in range(0, self.nDisplayChannels):
            self.btnsetRangeFixedHigher[iPlot].setFixedWidth(temp_button_width)
            self.btnsetRangeFixedLower[iPlot].setFixedWidth(temp_button_width)
            self.btnsetRangeFixedHigher[iPlot].setMinimumHeight(temp_button_heigth)
            self.btnsetRangeFixedLower[iPlot].setMinimumHeight(temp_button_heigth)
            self.btnsetRangeFixedHigher[iPlot].setStyleSheet('QPushButton {background-color: #000000; color: rgb(255,255,255);}')
            self.btnsetRangeFixedLower[iPlot].setStyleSheet('QPushButton {background-color: #000000; color: rgb(255,255,255);}')


        self.isRangeAuto = False
        self.btnsetRangeFixedOrAuto = QtGui.QPushButton("[F")
        self.btnsetRangeFixedOrAuto.setFixedWidth(temp_button_width)
        self.btnsetRangeFixedOrAuto.setStyleSheet('QPushButton {background-color: #000000; color: white;}')
        self.btnsetRangeFixedOrAuto.setMinimumHeight(temp_button_heigth)


        temp_height_plot = 3
        temp_width_plot = 20
        temp_height_zoom = 1
        temp_width_zoom = 1
        temp_width_label = 3

        for iPlot in range(0, self.nDisplayChannels):
            self.layout.addWidget(self.btnsetRangeFixedHigher[iPlot], iPlot * temp_height_plot, 0, temp_height_zoom, temp_width_zoom)
            self.layout.addWidget(self.btnsetRangeFixedLower[iPlot], (iPlot+1) * temp_height_plot-temp_height_zoom,0, temp_height_zoom, temp_width_zoom)
            if not self.useVispyPlot:
                self.layout.addWidget(self.plotWidgets[iPlot], iPlot * temp_height_plot, temp_width_zoom, temp_height_plot,1)
            self.layout.addWidget(self.LabelPlots[iPlot], iPlot * temp_height_plot, temp_width_zoom+temp_width_plot, temp_height_plot,temp_width_label)

        if self.useVispyPlot:
            self.layout.addWidget(self.plot.native, 0, temp_width_zoom, temp_height_plot*self.nDisplayChannels,1)

        self.layout.addWidget(self.btnsetRangeFixedOrAuto,1,0,1,1)

        self.layout.setColumnStretch(1, temp_width_plot)

         # for iColumn in range(0, temp_width_plot+temp_width_zoom):
         #     self.layout.setColumnStretch(iColumn, 1)

        for iRow in range(0, self.nDisplayChannels*temp_height_plot):
            self.layout.setRowStretch(iRow, 10)

        self.layout.setVerticalSpacing(1)



        self.win.resize(800, 600)

        self.EEGstartRangeExtension = 100.0

        self.RangeFixed = []
        for iPlot in range(0, self.nDisplayChannels):
            self.RangeFixed.append(np.array([-self.EEGstartRangeExtension, self.EEGstartRangeExtension]))



        self.win.show()

        self.connect(self.btnsetRangeFixedOrAuto, QtCore.SIGNAL('clicked()'), self.setRangeToggle)

        for iPlot in range(0, self.nDisplayChannels):
            self.connect(self.btnsetRangeFixedHigher[iPlot], QtCore.SIGNAL('clicked()'), self.setRangeFixedHigher)
            self.connect(self.btnsetRangeFixedLower[iPlot], QtCore.SIGNAL('clicked()'), self.setRangeFixedLower)

        self.setRangeFixed()

        self.connect(self.win, QtCore.SIGNAL("keyPressedEvent"), self.on_key, QtCore.Qt.QueuedConnection)

    def on_key(self, event):
        if event.key() == QtCore.Qt.Key_7:
            self.setRangeToggle()
        event.accept()

    def sendUpdateIntervalIncrease(self):
        self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySecondsAdjusted * 1.5
        if self.updateSendOutDelaySecondsAdjusted > 30.0:
            self.updateSendOutDelaySecondsAdjusted = 30
        self.sendUpdateIntervalAdjusted()

    def sendUpdateIntervalDecrease(self):
        self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySecondsAdjusted * 1.0 / 1.5
        if self.updateSendOutDelaySecondsAdjusted < self.updateSendOutDelaySeconds:
            self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySeconds
        self.sendUpdateIntervalAdjusted()

    def sendUpdateIntervalAdjusted(self):
        self.emit(QtCore.SIGNAL("sendMainUpdateIntervalChange"), ["update-view-refresh-interval", self.updateSendOutDelaySecondsAdjusted])

    def updateReceive(self, msg):
        prePlotTime = timeit.default_timer()
        viewSendingDelay = prePlotTime - msg[17]

        self.updatePlots(np.array(msg[0]), msg[16])

        internalSendLoopduration = (msg[17]-msg[18])
        postPlotTime = timeit.default_timer()

        updateDelay = postPlotTime - msg[18]

        plottingTime = (postPlotTime - prePlotTime)

        refreshInterval = msg[19]

        self.win.setWindowTitle(
            'Extended GUI signal viewer - by Frederik D. Weber  ---' + \
            " refresh rate: {:.2f}".format(round(refreshInterval * 1000, 2)) + ' ms' + \
            " send GUI: {:.2f}".format(round(viewSendingDelay * 1000, 2)) + ' ms' + \
            " plotting: {:.2f}".format(round(plottingTime * 1000, 2)) + ' ms' + \
            " algo stuck: {:.2f}".format(round(internalSendLoopduration * 1000, 2)) + ' ms')

        # time_sended = msg[17]
        # print("Signal Viewer Full: delay "+str(nowtime-time_sended)+" time sended "+str(time_sended)+" time received "+str(nowtime))

        # if self.lastUpdateTime is not None:
        if updateDelay > (1.1 * self.updateSendOutDelaySecondsAdjusted):
            self.sendUpdateIntervalIncrease()
        elif updateDelay < (0.8 * self.updateSendOutDelaySecondsAdjusted):
            self.sendUpdateIntervalDecrease()
        # else:
        #     self.sendUpdateIntervalDecrease()

    def updatePlots(self, t, signals_allChannels):
        if not self.useVispyPlot:
            if self.isRangeAuto:
                for iPlot in range(0, self.nDisplayChannels):
                    self.plots[iPlot].getAxis("left").getViewBox().setYRange(min(signals_allChannels[self.displayChannels[iPlot]]), max(signals_allChannels[self.displayChannels[iPlot]]), update=False)

            mint = min(t)
            maxt = max(t)

            for iPlot in range(0, self.nDisplayChannels):
                self.plots[iPlot].getAxis("bottom").getViewBox().setXRange(mint, maxt, padding=0, update=(False if iPlot < (self.nDisplayChannels-1) else True))

            for iPlot in range(0, self.nDisplayChannels):
                self.curves[iPlot].setData(t, np.array(signals_allChannels[self.displayChannels[iPlot]])[0:len(t)], antialias=self.doAntiAlias)

        else:
            # if self.nDisplayChannels > 0:
            #     t = np.linspace(max(t[len(t)-1]-30,0), t[len(t)-1], len(signals_allChannels[self.displayChannels[0]]))
            #
            signals = []
            for iPlot in range(0, self.nDisplayChannels):
                signals.append(np.array(signals_allChannels[self.displayChannels[iPlot]]))

            self.plot.updateChannelData(t,signals)



    def setRangeToggle(self):
        if self.isRangeAuto:
            self.setRangeFixed()
            self.btnsetRangeFixedOrAuto.setText("[F")
        else:
            self.setRangeAuto()
            self.btnsetRangeFixedOrAuto.setText("[A")

    def setRangeAuto(self):
        if not self.useVispyPlot:
            for iPlot in range(0, self.nDisplayChannels):
                self.plots[iPlot].getAxis("left").setTickSpacing()
            self.isRangeAuto = True

    def setRangeFixed(self):
        if not self.useVispyPlot:
            self.isRangeAuto = False
            for iPlot in range(0, self.nDisplayChannels):
                self.plots[iPlot].getAxis("left").getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
                self.updateRanges(iPlot)

    def updateRanges(self,iPlot):
        if not self.useVispyPlot:
            self.plots[iPlot].getAxis("left").getViewBox().setRange(yRange=self.RangeFixed[iPlot], padding=None, update=True, disableAutoRange=True)
            self.plots[iPlot].getAxis("left").getViewBox().setLimits(yMin=self.RangeFixed[iPlot][0], yMax=self.RangeFixed[iPlot][1])
            self.plots[iPlot].getAxis("left").setTickSpacing(max(self.RangeFixed[iPlot]) / 2.0, max(self.RangeFixed[iPlot]) / 4.0)
            # self.plots[iPlot].getAxis("left").setStyle(tickTextWidth=1)
            # self.plots[iPlot].getAxis("left").setStyle(autoExpandTextSpace=True)
        else:
            self.plot.setChannelRange(iPlot,(self.RangeFixed[iPlot]))


    def getPlotNumberBySenderButton(self,sender):
        for iPlot in range(0, self.nDisplayChannels):
            if (self.btnsetRangeFixedHigher[iPlot] == sender) or (self.btnsetRangeFixedLower[iPlot] == sender):
                return iPlot

    def setRangeFixedHigher(self):
        if not self.isRangeAuto:
            sender = self.sender()
            iPlot = self.getPlotNumberBySenderButton(sender)
            self.RangeFixed[iPlot] = np.array(self.RangeFixed[iPlot] * 1.25)
            self.updateRanges(iPlot)


    def setRangeFixedLower(self):
        if not self.isRangeAuto:
            sender = self.sender()
            iPlot = self.getPlotNumberBySenderButton(sender)
            self.RangeFixed[iPlot] = np.array([min(self.RangeFixed[iPlot][0] * 0.8, -self.EEGstartRangeExtension * 0.8 ** 12),
                                           max(self.RangeFixed[iPlot][1] * 0.8, self.EEGstartRangeExtension * 0.8 ** 12)])
            self.updateRanges(iPlot)

class DisplaySignalViewWidget(QtCore.QThread):
    keyPressed = QtCore.pyqtSignal(int)
    def __init__(self, t, y1, y2, y3, ca, montage, board, isStimulationTurnedOn, sound_base_level_dB, sound_rise_from_base_level_db,soundlatency_seconds,filterdelay_seconds, updateSendOutDelaySeconds, language,
                 threshold_EEGSignal_from_away_zero_disengage_algo, threshold_EOGSignal_from_away_zero_disengage_algo, threshold_EMGSignal_from_away_zero_disengage_algo,doSpindleHighlight,doAntiAlias=True,useOpenGL=True,doDownSamplingForPlot=False,):
        QtCore.QThread.__init__(self)
        self.updateSendOutDelaySeconds = updateSendOutDelaySeconds
        self.updateSendOutDelaySecondsAdjusted = updateSendOutDelaySeconds
        # self.lastUpdateTime = None

        self.montage = montage
        self.ca = ca

        self.soundlatency_seconds = soundlatency_seconds
        self.filterdelay_seconds = filterdelay_seconds

        self.doAntiAlias = doAntiAlias
        self.useOpenGL = useOpenGL

        self.doDownSamplingForPlot = doDownSamplingForPlot

        self.doSpindleHighlight = doSpindleHighlight


        self.isStimulationTurnedOn = isStimulationTurnedOn
        self.language = language
        self.threshold_EEGSignal_from_away_zero_disengage_algo = threshold_EEGSignal_from_away_zero_disengage_algo
        self.threshold_EOGSignal_from_away_zero_disengage_algo = threshold_EOGSignal_from_away_zero_disengage_algo
        self.threshold_EMGSignal_from_away_zero_disengage_algo = threshold_EMGSignal_from_away_zero_disengage_algo

        self.timeOfLightsOff = None

        self.win = QWidget2()

        self.win.setAutoFillBackground(True)
        self.palette = self.win.palette()
        self.palette.setColor(self.win.backgroundRole(), QtCore.Qt.black)
        self.win.setPalette(self.palette)

        self.win.setWindowTitle('Main GUI signal viewer and stimulator - by Frederik D. Weber')

        self.layout = QtGui.QGridLayout(self.win)
        self.win.setLayout(self.layout)

        try:
            pg.PlotWidget(useOpenGL=self.useOpenGL)
        except Exception as e:
            print('OpenGL cannot be assured to be loaded problem')
            print(e.message)
            okpressed = main.showMessageBox("OpenGL problem",
                                            "Your System does not support OpenGL yet.\nMaybe install your graphics card driver (if available)\nError message:\n\n" + e.message + "\n\nContinue anyway or abort?",
                                            True, False, True, isOKbuttonDefault=False)
            if not okpressed:
                sys.exit(0)

        if self.isStimulationTurnedOn:
            self.pw0 = pg.PlotWidget(useOpenGL=self.useOpenGL)
            self.pw0avg = pg.PlotWidget(useOpenGL=self.useOpenGL)
        self.pw1 = pg.PlotWidget(useOpenGL=self.useOpenGL)
        self.pw2 = pg.PlotWidget(useOpenGL=self.useOpenGL)
        self.pw3 = pg.PlotWidget(useOpenGL=self.useOpenGL)

        if self.isStimulationTurnedOn:
            self.p0 = self.pw0.getPlotItem()
            self.p0avg = self.pw0avg.getPlotItem()
            self.p0.setDownsampling(ds=self.doDownSamplingForPlot)
            self.p0avg.setDownsampling(ds=self.doDownSamplingForPlot)
        self.p1 = self.pw1.getPlotItem()
        self.p2 = self.pw2.getPlotItem()
        self.p3 = self.pw3.getPlotItem()
        self.p1.setDownsampling(ds=self.doDownSamplingForPlot)
        self.p2.setDownsampling(ds=self.doDownSamplingForPlot)
        self.p3.setDownsampling(ds=self.doDownSamplingForPlot)

        smallfont = QtGui.QFont()
        smallfont.setPointSize(6)

        # if self.isStimulationTurnedOn:
        #     # self.p0.setTitle(title="ERP (Brain) last")
        #     # self.p0avg.setTitle(title="ERP (Brain) avg 0")
        #     self.Label_p0 = QtGui.QLabel()
        #     self.Label_p0.setFont(smallfont)
        #     self.Label_p0.setText("ERP (EEG) last")
        #     self.Label_p0.setAlignment(QtCore.Qt.AlignRight)
        #     self.Label_p0avg = QtGui.QLabel()
        #     self.Label_p0avg.setFont(smallfont)
        #     self.Label_p0avg.setText("ERP (EEG) avg 0")
        #     self.Label_p0avg.setAlignment(QtCore.Qt.AlignRight)



        # self.p1.setTitle(title="EEG (Brain) " + self.montage.getChannelDescriptionByChannelNumber(ca.channelEEG,ca.realTimeFilterOrder))
        # self.p2.setTitle(title="EOG (Eyes) " + self.montage.getChannelDescriptionByChannelNumber(ca.channelEOG,ca.realTimeFilterOrder))
        # self.p2.setTitle(title="EMG (Muscles) " + self.montage.getChannelDescriptionByChannelNumber(ca.channelEMG,ca.realTimeFilterOrder))

        # self.Label_p1 = QtGui.QLabel()
        # self.Label_p1.setFont(smallfont)
        # self.Label_p1.setText("EEG\n" + self.montage.getChannelDescriptionByChannelNumber(self.ca.channelEEG,self.ca.realTimeFilterOrder,wrap=True))
        # self.Label_p1.setAlignment(QtCore.Qt.AlignRight)
        # self.Label_p1.setAlignment(QtCore.Qt.AlignVCenter)
        #
        # self.Label_p2 = QtGui.QLabel()
        # self.Label_p2.setFont(smallfont)
        # self.Label_p2.setText("EOG\n" + self.montage.getChannelDescriptionByChannelNumber(self.ca.channelEOG,self.ca.realTimeFilterOrder,wrap=True))
        # self.Label_p2.setAlignment(QtCore.Qt.AlignRight)
        # self.Label_p2.setAlignment(QtCore.Qt.AlignVCenter)
        #
        # self.Label_p3 = QtGui.QLabel()
        # self.Label_p3.setFont(smallfont)
        # self.Label_p3.setText("EMG\n" + self.montage.getChannelDescriptionByChannelNumber(self.ca.channelEMG,self.ca.realTimeFilterOrder,wrap=True))
        # self.Label_p3.setAlignment(QtCore.Qt.AlignRight)
        # self.Label_p3.setAlignment(QtCore.Qt.AlignVCenter)


        self.btnReconnect = QtGui.QPushButton('[R]')
        self.btnReconnect.setEnabled(False)

        self.Label_lastLightsOff = QtGui.QLabel()
        self.Label_lastLightsOff.setText("last lights-off: ")
        self.Label_lastLightsOff.setAlignment(QtCore.Qt.AlignLeft)

        self.Label_updateView = QtGui.QLabel()
        self.Label_updateView.setText("update:")
        self.Label_updateView.setAlignment(QtCore.Qt.AlignRight)


        self.SpBx_updateView = QtGui.QDoubleSpinBox()
        self.SpBx_updateView.setRange(0.05, 30.0)
        self.SpBx_updateView.setSingleStep(0.05)
        self.SpBx_updateView.setDecimals(2)
        self.SpBx_updateView.setValue(self.updateSendOutDelaySeconds)

        self.Label_EEGchan = QtGui.QPushButton()
        self.Label_EEGchan.setFlat(True)
        self.Label_EEGchan.setText("EEG (" + self.montage.getChannelLabelReRefByChannelNumber(ca.channelEEG) + ")")
        #self.Label_EEGchan.setAlignment(QtCore.Qt.AlignRight)
        self.Label_EEGchan_clickcounter = 0

        self.SpBx_EEGchan = QtGui.QSpinBox()
        self.SpBx_EEGchan.setRange(0, (16 if ca.useDaisy else 8))
        self.SpBx_EEGchan.setSingleStep(1)
        self.SpBx_EEGchan.setValue(ca.channelEEG)
        self.SpBx_EEGchan.setEnabled(False)

        if self.isStimulationTurnedOn:
            self.btnStartStim = QtGui.QPushButton('Start(S)')
            self.btnPauseStim = QtGui.QPushButton('Pause(P)')
            self.btnTestStim = QtGui.QPushButton('Test Noise(T)')
            self.btnForceEngageStimulation = QtGui.QPushButton("Auto Stim.(A)")

            self.Label_nextPlayListItem = QtGui.QLabel()
            self.Label_nextPlayListItem.setText("next item: ")
            self.Label_nextPlayListItem.setAlignment(QtCore.Qt.AlignLeft)

            self.Label_PlayListItemsPlayed = QtGui.QLabel()
            self.Label_PlayListItemsPlayed.setText("# items: ")
            self.Label_PlayListItemsPlayed.setAlignment(QtCore.Qt.AlignLeft)

            self.Label_lastStimulusPlayed = QtGui.QLabel()
            self.Label_lastStimulusPlayed.setText("last item: ")
            self.Label_lastStimulusPlayed.setAlignment(QtCore.Qt.AlignLeft)

            self.Label_sound_rise_from_base_level_db = QtGui.QLabel()
            self.Label_sound_rise_from_base_level_db.setText("Vol. Adj. of basel. [dB]:(up/down)")
            self.Label_sound_rise_from_base_level_db.setAlignment(QtCore.Qt.AlignRight)

            self.SpBx_sound_rise_from_base_level_db = QtGui.QSpinBox()
            self.SpBx_sound_rise_from_base_level_db.setRange(-84 + sound_base_level_dB, -sound_base_level_dB)
            self.SpBx_sound_rise_from_base_level_db.setSingleStep(1)
            self.SpBx_sound_rise_from_base_level_db.setValue(sound_rise_from_base_level_db)



        self.btnEEGcheck = QtGui.QPushButton('Check(C)')
        self.btnLightsOff = QtGui.QPushButton('Lights-OFF(O)')
        self.btnLightsOn = QtGui.QPushButton('Lights-ON(L)')

        self.btnsetRangeFixedHigherEEG = QtGui.QPushButton('-')
        self.btnsetRangeFixedHigherEOG = QtGui.QPushButton('-')
        self.btnsetRangeFixedHigherEMG = QtGui.QPushButton('-')

        self.btnsetRangeFixedLowerEEG = QtGui.QPushButton('+')
        self.btnsetRangeFixedLowerEOG = QtGui.QPushButton('+')
        self.btnsetRangeFixedLowerEMG = QtGui.QPushButton('+')

        temp_button_width = 30
        self.btnsetRangeFixedHigherEEG.setFixedWidth(temp_button_width)
        self.btnsetRangeFixedHigherEOG.setFixedWidth(temp_button_width)
        self.btnsetRangeFixedHigherEMG.setFixedWidth(temp_button_width)

        self.btnsetRangeFixedLowerEEG.setFixedWidth(temp_button_width)
        self.btnsetRangeFixedLowerEOG.setFixedWidth(temp_button_width)
        self.btnsetRangeFixedLowerEMG.setFixedWidth(temp_button_width)

        self.isRangeAuto = False
        self.btnsetRangeFixedOrAuto = QtGui.QPushButton("[F")
        self.btnsetRangeFixedOrAuto.setFixedWidth(temp_button_width)

        self.btnsetRangeFixedHigherEEG.setStyleSheet('QPushButton {background-color: #000000; color: rgb(255,255,255);}')
        self.btnsetRangeFixedHigherEOG.setStyleSheet('QPushButton {background-color: #000000; color: rgb(0,255,255);}')
        self.btnsetRangeFixedHigherEMG.setStyleSheet('QPushButton {background-color: #000000; color: rgb(255,128,0);}')
        self.btnsetRangeFixedLowerEEG.setStyleSheet('QPushButton {background-color: #000000; color: rgb(255,255,255);}')
        self.btnsetRangeFixedLowerEOG.setStyleSheet('QPushButton {background-color: #000000; color: rgb(0,255,255);}')
        self.btnsetRangeFixedLowerEMG.setStyleSheet('QPushButton {background-color: #000000; color: rgb(255,128,0);}')

        self.btnsetRangeFixedOrAuto.setStyleSheet('QPushButton {background-color: #000000; color: white;}')

        self.btnEEGcheck.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')
        self.btnLightsOff.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')
        self.btnLightsOn.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')

        self.btnLightsOff.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')
        self.btnLightsOff.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')

        self.btnReconnect.setStyleSheet('QPushButton {background-color: #777777; color: white; border: 1px solid red;}')

        self.Label_lastLightsOff.setStyleSheet('QLabel {background-color: #000000; color: gray;}')

        # self.Label_p1.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
        # self.Label_p2.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
        # self.Label_p3.setStyleSheet('QLabel {background-color: #000000; color: gray;}')


        self.Label_updateView.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
        self.SpBx_updateView.setStyleSheet('QDoubleSpinBox {background-color: #000000; color: white; border: 1px solid gray;}')

        self.Label_EEGchan.setStyleSheet('QPushButton {background-color: #000000; color: red; border: 0px solid black;}')
        self.SpBx_EEGchan.setStyleSheet('QSpinBox {background-color: #000000; color: white; border: 1px solid red;}')


        if self.isStimulationTurnedOn:
            self.btnStartStim.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')
            self.btnPauseStim.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')
            self.btnTestStim.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')
            self.btnForceEngageStimulation.setStyleSheet('QPushButton {background-color: #000000; color: white; border: 1px solid gray;}')

            self.Label_nextPlayListItem.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
            self.Label_PlayListItemsPlayed.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
            self.Label_lastStimulusPlayed.setStyleSheet('QLabel {background-color: #000000; color: gray;}')

            self.Label_sound_rise_from_base_level_db.setStyleSheet('QLabel {background-color: #000000; color: gray;}')
            self.SpBx_sound_rise_from_base_level_db.setStyleSheet('QSpinBox {background-color: #000000; color: white; border: 1px solid gray;}')





        self.layout.addWidget(self.btnsetRangeFixedHigherEEG, 0, 0, 1, 1)
        # self.layout.addWidget(self.Label_p1, 1, 0, 1, 1)
        self.layout.addWidget(self.btnsetRangeFixedLowerEEG, 2, 0, 1, 1)

        self.layout.addWidget(self.btnsetRangeFixedHigherEOG, 3, 0, 1, 1)
        # self.layout.addWidget(self.Label_p2, 4, 0, 1, 1)
        self.layout.addWidget(self.btnsetRangeFixedLowerEOG, 5, 0, 1, 1)

        self.layout.addWidget(self.btnsetRangeFixedHigherEMG, 6, 0, 1, 1)
        # self.layout.addWidget(self.Label_p3, 7, 0, 1, 1)
        self.layout.addWidget(self.btnsetRangeFixedLowerEMG, 8, 0, 1, 1)

        self.layout.addWidget(self.btnsetRangeFixedOrAuto, 9, 0, 1, 1)


        print(pg.systemInfo())
        if self.isStimulationTurnedOn:
            self.layout.addWidget(self.pw0, 0, 25, 3, 4)
            self.layout.addWidget(self.pw0avg, 3, 25, 3, 4)
        self.layout.addWidget(self.pw1, 0, 1, 3, 24)

        self.layout.addWidget(self.pw2, 3, 1, 3, 24)
        self.layout.addWidget(self.pw3, 6, 1, 3, 24)

        self.layout.addWidget(self.btnEEGcheck, 9, 1, 1, 3)
        self.layout.addWidget(self.btnLightsOff, 9, 4, 1, 3)
        self.layout.addWidget(self.btnLightsOn, 9, 21, 1, 3)
        self.layout.addWidget(self.btnReconnect, 9, 24, 1, 1)

        if self.isStimulationTurnedOn:
            self.layout.addWidget(self.Label_EEGchan, 9, 7, 1, 3)
            self.layout.addWidget(self.SpBx_EEGchan, 9, 10, 1, 1)
            self.layout.addWidget(self.btnStartStim, 9, 11, 1, 3)
            self.layout.addWidget(self.btnTestStim, 9, 14, 1, 2)
            self.layout.addWidget(self.btnForceEngageStimulation, 9, 16, 1, 2)
            self.layout.addWidget(self.btnPauseStim, 9, 18, 1, 3)

            self.layout.addWidget(self.Label_nextPlayListItem, 6, 25, 1, 1)
            self.layout.addWidget(self.Label_PlayListItemsPlayed, 6, 26, 1, 1)
            self.layout.addWidget(self.Label_lastStimulusPlayed, 6, 27, 1, 2)



            self.layout.addWidget(self.Label_lastLightsOff, 8, 25, 1, 2)
            self.layout.addWidget(self.Label_updateView, 8, 27, 1, 1)
            self.layout.addWidget(self.SpBx_updateView, 8, 28, 1, 1)

            self.layout.addWidget(self.SpBx_sound_rise_from_base_level_db, 9, 28, 1, 1)
            self.layout.addWidget(self.Label_sound_rise_from_base_level_db, 9, 25, 1, 3)

            for iColumn in range(0, 29):
                self.layout.setColumnStretch(iColumn, 1)
        else:
            self.layout.addWidget(self.Label_lastLightsOff, 9, 8, 1, 2)

            self.layout.addWidget(self.Label_EEGchan, 9, 10, 1, 1)
            self.layout.addWidget(self.SpBx_EEGchan, 9, 11, 1, 1)

            self.layout.addWidget(self.Label_updateView, 9, 12, 1, 1)
            self.layout.addWidget(self.SpBx_updateView, 9, 13, 1, 1)



            for iColumn in range(0, 25):
                self.layout.setColumnStretch(iColumn, 1)

        for iRow in range(0, 10):
            self.layout.setRowStretch(iRow, 1)

        self.layout.setColumnStretch(0, 1)

        self.layout.setVerticalSpacing(2)
        self.layout.setHorizontalSpacing(2)


        self.win.resize(1200, 600)

        self.p1.showGrid(x=True, y=True, alpha=0.30)
        self.p2.showGrid(x=True, y=True, alpha=0.30)
        self.p3.showGrid(x=True, y=True, alpha=0.30)

        self.p1.getAxis("bottom").setTickSpacing(5.0, 1.0)
        self.p2.getAxis("bottom").setTickSpacing(5.0, 1.0)
        self.p3.getAxis("bottom").setTickSpacing(5.0, 1.0)

        self.p1.getAxis("left").setTickSpacing(50.0, 25.0)
        self.p2.getAxis("left").setTickSpacing(50.0, 25.0)
        self.p3.getAxis("left").setTickSpacing(25.0, 5.0)

        if self.doSpindleHighlight:
            self.curve1_spindles = self.p1.plot(pen=pg.mkPen(color=(0,192,0)))
        if self.isStimulationTurnedOn:
            self.curve0 = self.p0.plot(pen=pg.mkPen(color=(255,255,255)))
            self.curve0avg = self.p0avg.plot(pen=pg.mkPen(color=(255,255,255)))
        self.curve1 = self.p1.plot(pen=pg.mkPen(color=(255,255,255)),clear=False)
        self.curve2 = self.p2.plot(pen=pg.mkPen(color=(0,255,255)))
        self.curve3 = self.p3.plot(pen=pg.mkPen(color=(255,128,0)))

        self.l1_th = None

        self.EEGstartRangeExtension = 100.0
        self.EOGstartRangeExtension = 100.0
        self.EMGstartRangeExtension = 50.0

        if self.isStimulationTurnedOn:
            self.RangeERPfixed = np.array([-self.EEGstartRangeExtension, self.EEGstartRangeExtension])
            self.RangeERPavgfixed = np.array([-self.EEGstartRangeExtension, self.EEGstartRangeExtension])
        self.RangeEEGfixed = np.array([-self.EEGstartRangeExtension, self.EEGstartRangeExtension])
        self.RangeEOGfixed = np.array([-self.EOGstartRangeExtension, self.EOGstartRangeExtension])
        self.RangeEMGfixed = np.array([-self.EMGstartRangeExtension, self.EMGstartRangeExtension])

        self.plotsYLabelStyle = {'font-size': '6pt'}

        if self.isStimulationTurnedOn:
            self.p0.getAxis("left").setLabel(axis="left", text="ERP (EEG) last", **self.plotsYLabelStyle)
            self.p0avg.getAxis("left").setLabel(axis="left", text="ERP (EEG) avg 0", **self.plotsYLabelStyle)
        self.p1.getAxis("left").setLabel(axis="left", text="EEG " + self.montage.getChannelDescriptionByChannelNumber(self.ca.channelEEG,self.ca.realTimeFilterOrder,wrap=False), **self.plotsYLabelStyle)
        self.p2.getAxis("left").setLabel(axis="left", text="EOG " + self.montage.getChannelDescriptionByChannelNumber(self.ca.channelEOG,self.ca.realTimeFilterOrder,wrap=False), **self.plotsYLabelStyle)
        self.p3.getAxis("left").setLabel(axis="left", text="EMG " + self.montage.getChannelDescriptionByChannelNumber(self.ca.channelEMG,self.ca.realTimeFilterOrder,wrap=False), **self.plotsYLabelStyle)

        # if self.isStimulationTurnedOn:
        #     self.p0.getAxis("left").showLabel(show=False)
        #     self.p0avg.getAxis("left").showLabel(show=False)
        # self.p1.getAxis("left").showLabel(show=False)
        # self.p2.getAxis("left").showLabel(show=False)
        # self.p3.getAxis("left").showLabel(show=False)


        if self.isStimulationTurnedOn:
            self.p0.getAxis("left").getViewBox().setAutoPan(x=False, y=False)
            self.p0avg.getAxis("left").getViewBox().setAutoPan(x=False, y=False)
        self.p1.getAxis("left").getViewBox().setAutoPan(x=False, y=False)
        self.p2.getAxis("left").getViewBox().setAutoPan(x=False, y=False)
        self.p3.getAxis("left").getViewBox().setAutoPan(x=False, y=False)

        if self.isStimulationTurnedOn:
            self.p0.getAxis("top").showLabel(show=False)
            self.p0avg.getAxis("top").showLabel(show=False)
        self.p1.getAxis("top").showLabel(show=False)
        self.p2.getAxis("top").showLabel(show=False)
        self.p3.getAxis("top").showLabel(show=False)


        if self.isStimulationTurnedOn:
            self.p0.getAxis("left").getViewBox().enableAutoRange(x=False, y=False)
            self.p0avg.getAxis("left").getViewBox().enableAutoRange(x=False, y=False)
        self.p1.getAxis("left").getViewBox().enableAutoRange(x=False, y=False)
        self.p2.getAxis("left").getViewBox().enableAutoRange(x=False, y=False)
        self.p3.getAxis("left").getViewBox().enableAutoRange(x=False, y=False)

        if self.isStimulationTurnedOn:
            self.p0.showLabel("left")
            self.p0avg.showLabel("left")
        self.p1.showLabel("left")
        self.p2.showLabel("left")
        self.p3.showLabel("left")

        self.win.show()

        if self.isStimulationTurnedOn:
            self.p0.showButtons()
            self.p0avg.showButtons()
        self.p1.showButtons()
        self.p2.showButtons()
        self.p3.showButtons()

        self.stimsLinesQueue1 = collections.deque(maxlen=200)
        self.stimsLinesQueue2 = collections.deque(maxlen=200)
        self.stimsLinesQueue3 = collections.deque(maxlen=200)
        self.stimsLinesQueueSpindle = collections.deque(maxlen=200)

        self.stimsLinesQueue1Text = collections.deque(maxlen=200)

        self.isStimAuto = True

        if self.isStimulationTurnedOn:
            self.btnPauseStim.setEnabled(False)

        self.connect(self.btnsetRangeFixedOrAuto, QtCore.SIGNAL('clicked()'), self.setRangeToggle)

        self.connect(self.btnsetRangeFixedHigherEEG, QtCore.SIGNAL('clicked()'), self.setRangeFixedHigherEEG)
        self.connect(self.btnsetRangeFixedLowerEEG, QtCore.SIGNAL('clicked()'), self.setRangeFixedLowerEEG)

        self.connect(self.btnsetRangeFixedHigherEOG, QtCore.SIGNAL('clicked()'), self.setRangeFixedHigherEOG)
        self.connect(self.btnsetRangeFixedLowerEOG, QtCore.SIGNAL('clicked()'), self.setRangeFixedLowerEOG)

        self.connect(self.btnsetRangeFixedHigherEMG, QtCore.SIGNAL('clicked()'), self.setRangeFixedHigherEMG)
        self.connect(self.btnsetRangeFixedLowerEMG, QtCore.SIGNAL('clicked()'), self.setRangeFixedLowerEMG)

        self.connect(self.btnEEGcheck, QtCore.SIGNAL('clicked()'), self.sendCheckEEG)
        self.connect(self.btnLightsOff, QtCore.SIGNAL('clicked()'), self.sendLightsOff)
        self.connect(self.btnLightsOn, QtCore.SIGNAL('clicked()'), self.sendLightsOn)
        self.connect(self.btnReconnect, QtCore.SIGNAL('clicked()'), self.sendReconnect)


        if self.isStimulationTurnedOn:
            self.connect(self.btnStartStim, QtCore.SIGNAL('clicked()'), self.sendStartStim)
            self.connect(self.btnPauseStim, QtCore.SIGNAL('clicked()'), self.sendPauseStim)
            self.connect(self.btnTestStim, QtCore.SIGNAL('clicked()'), self.sendTestStim)
            self.connect(self.btnForceEngageStimulation, QtCore.SIGNAL('clicked()'), self.setForceStimToggle)
            self.connect(self.SpBx_sound_rise_from_base_level_db, QtCore.SIGNAL('valueChanged(int)'), self.sendSoundRiseLevelChanged)

        self.connect(self.SpBx_updateView, QtCore.SIGNAL('valueChanged(double)'), self.sendViewUpdateIntervalChanged)
        self.connect(self.SpBx_EEGchan, QtCore.SIGNAL('valueChanged(int)'), self.sendViewEEGchannelChanged)
        self.connect(self.Label_EEGchan, QtCore.SIGNAL('clicked()'), self.sendViewEEGLabelClicked)




        self.setRangeFixed()

        if self.isStimulationTurnedOn:
            l0_v = self.p0.addLine(x=0.0)
            l0_h = self.p0.addLine(y=0.0)
            l0_v.setPen(color=(255, 255, 0), style=QtCore.Qt.DotLine)
            l0_h.setPen(color=(255, 0, 0), style=QtCore.Qt.DotLine)
            l0_v_unfilt = self.p0.addLine(x=0.0 - self.filterdelay_seconds)
            l0_v_unfilt.setPen(color=(255, 0, 0), style=QtCore.Qt.DotLine)
            l0_v_audio = self.p0.addLine(x=0.0 + self.soundlatency_seconds)
            l0_v_audio.setPen(color=(0, 255, 0), style=QtCore.Qt.DotLine)


            l0avg_v = self.p0avg.addLine(x=0.0)
            l0avg_h = self.p0avg.addLine(y=0.0)
            l0avg_v.setPen(color=(255, 255, 0), style=QtCore.Qt.DotLine)
            l0avg_h.setPen(color=(255, 0, 0), style=QtCore.Qt.DotLine)
            l0avg_v_unfilt = self.p0avg.addLine(x=0.0 - self.filterdelay_seconds)
            l0avg_v_unfilt.setPen(color=(255, 0, 0), style=QtCore.Qt.DotLine)
            l0avg_v_audio = self.p0avg.addLine(x=0.0 + self.soundlatency_seconds)
            l0avg_v_audio.setPen(color=(0, 255, 0), style=QtCore.Qt.DotLine)

            # self.p0avg.setTitle("ERP (EEG) avg " + str(0))
            self.p0avg.getAxis("left").setLabel(axis="left", text="ERP (EEG) avg 0")


        l_SO_up = self.p1.addLine(y=37.5)
        l_SO_down = self.p1.addLine(y=-37.5)
        l_SO_up.setPen(color=(0, 128, 0), style=QtCore.Qt.DotLine)
        l_SO_down.setPen(color=(0, 128, 0), style=QtCore.Qt.DotLine)

        l_EEG_up = self.p1.addLine(y=self.threshold_EEGSignal_from_away_zero_disengage_algo)
        l_EEG_down = self.p1.addLine(y=-1 * self.threshold_EEGSignal_from_away_zero_disengage_algo)
        l_EEG_up.setPen(color=(128, 0, 0), style=QtCore.Qt.DotLine)
        l_EEG_down.setPen(color=(128, 0, 0), style=QtCore.Qt.DotLine)

        l_EOG_up = self.p2.addLine(y=self.threshold_EOGSignal_from_away_zero_disengage_algo)
        l_EOG_down = self.p2.addLine(y=-1 * self.threshold_EOGSignal_from_away_zero_disengage_algo)
        l_EOG_up.setPen(color=(128, 0, 0), style=QtCore.Qt.DotLine)
        l_EOG_down.setPen(color=(128, 0, 0), style=QtCore.Qt.DotLine)

        self.l_EMG_up = self.p3.addLine(y=self.threshold_EMGSignal_from_away_zero_disengage_algo)
        self.l_EMG_down = self.p3.addLine(y=-1 * self.threshold_EMGSignal_from_away_zero_disengage_algo)
        self.l_EMG_up.setPen(color=(128, 0, 0), style=QtCore.Qt.DotLine)
        self.l_EMG_down.setPen(color=(128, 0, 0), style=QtCore.Qt.DotLine)

        self.connect(self.win, QtCore.SIGNAL("keyPressedEvent"), self.on_key, QtCore.Qt.QueuedConnection)

    def on_key(self, event):
        if event.key() == QtCore.Qt.Key_S:
            self.sendStartStim()
        elif event.key() == QtCore.Qt.Key_P:
            if self.btnPauseStim.isEnabled():
                self.sendPauseStim()
        elif event.key() == QtCore.Qt.Key_C:
            self.sendCheckEEG()
        elif event.key() == QtCore.Qt.Key_L:
            self.sendLightsOn()
        elif event.key() == QtCore.Qt.Key_O:
            self.sendLightsOff()
        elif event.key() == QtCore.Qt.Key_T:
            if self.isStimulationTurnedOn:
                self.sendTestStim()
        elif event.key() == QtCore.Qt.Key_A:
            if self.isStimulationTurnedOn:
                self.setForceStimToggle()
        elif event.key() == QtCore.Qt.Key_1:
            self.setRangeFixedHigherEEG()
        elif event.key() == QtCore.Qt.Key_2:
            self.setRangeFixedLowerEEG()
        elif event.key() == QtCore.Qt.Key_3:
            self.setRangeFixedHigherEOG()
        elif event.key() == QtCore.Qt.Key_4:
            self.setRangeFixedLowerEOG()
        elif event.key() == QtCore.Qt.Key_5:
            self.setRangeFixedHigherEMG()
        elif event.key() == QtCore.Qt.Key_6:
            self.setRangeFixedLowerEMG()
        elif event.key() == QtCore.Qt.Key_7:
            self.setRangeToggle()
        elif event.key() == QtCore.Qt.Key_Up:
            if self.isStimulationTurnedOn:
                self.SpBx_sound_rise_from_base_level_db.setValue(self.SpBx_sound_rise_from_base_level_db.value() + 1)
            # self.btnsetRangeFixedHigherEEG.setFocus()
        elif event.key() == QtCore.Qt.Key_Down:
            if self.isStimulationTurnedOn:
                self.SpBx_sound_rise_from_base_level_db.setValue(self.SpBx_sound_rise_from_base_level_db.value() - 1)
            # self.btnsetRangeFixedHigherEEG.setFocus()
        event.accept()

    def sendCheckEEG(self):
        print("clicked check EEG button send to main ...")
        self.emit(QtCore.SIGNAL("sendMainCheckEEG"), ["checkEEG"])
        if self.language == "en":
            checkEEGText = \
                "< br/>" \
                "<b> Checklist:</b>" \
                "< br/> " \
                "<b>1.</b> Look to your <b>left and right</b>, left and right,... (3-4 left-rights). OK well done.< br/>" \
                "  <b> Pause 5-10 sec </b>< br/>" \
                "<b>2.</b> Look to <b>up and down</b>, up and down,  (3-4 up-downs). OK you are doing great.< br/>" \
                "  <b> Pause 5-10 sec </b>< br/>" \
                "<b>3.</b> Ok now <b>blink</b> with your eyes... blink blink blink... WOW you blink nicely.< br/>" \
                "  <b> Pause 5-10 sec </b>< br/>" \
                "<b>4.</b> Now strongly <b>bite your teeth</b> together for a few seconds, now make an <b>angry face</b>, < br/>" \
                "   and try to move your lower lip over your upper lip, I know, difficult, right (-:< br/>" \
                "  <b> Pause 5-10 sec </b>< br/>" \
                "<b>5.</b> Now <b>relax and close your eyes and keep them closed</b> until I counted down to 1 " \
                "  (Experimenter now counts loud from 30 to 1)... 1! < br/>" \
                "   Open your eyes again and think of something nice.< br/>"

        elif self.language == "zh":
            checkEEGText = \
                "<br/>" \
                "<b> 检查表:</b>" \
                "<br/> " \
                "<b>1.</b> 眼睛请看向 <b>左、右</b>, 左、右,... (3-4 左-右). OK 做的很好.<br/>" \
                "  <b> 休息 5-10 秒钟 </b><br/>" \
                "<b>2.</b> 眼睛请看向 <b>上 、下</b>, 上 、下,  (3-4 上 -下). OK 你做的很不错.<br/>" \
                "  <b> 休息 5-10 秒钟 </b><br/>" \
                "<b>3.</b> Ok 现在 <b>开始眨眼</b> 眨眼... 眨眼 眨眼 眨眼... WOW 做的很好.<br/>" \
                "  <b> 休息 5-10 秒钟 </b><br/>" \
                "<b>4.</b> 现在 用力的 <b>咬牙</b> 几秒钟, 现在做一个 <b>生气的脸</b>, <br/>" \
                "   并试着用你的下嘴唇包着上嘴唇，我知道这有一点困难 (-: <br/>" \
                "  <b> 休息 5-10 秒钟 </b><br/>" \
                "<b>5.</b> 现在 <b>放松， 请闭上你的眼睛 </b> 直到我倒数到1 " \
                "  (主试开始大声从30倒数到1) 30... 1! <br/>" \
                "   现在睁开你的眼睛，想象一些美好的事情.<br/>"

        checkEEGText = QtCore.QString.fromUtf8(checkEEGText)
        MainWindow().showMessageBox("EEG Check Procedure", checkEEGText, False, True, False)

    def sendLightsOff(self):
        print("clicked lights off button send to main ...")
        self.emit(QtCore.SIGNAL("sendMainLightsOff"), ["lightsoff"])
        self.timeOfLightsOff = timeit.default_timer()

    def sendLightsOn(self):
        print("clicked lights on button send to main ...")
        self.emit(QtCore.SIGNAL("sendMainLightsOn"), ["lightson"])

    def sendReconnect(self):
        print("clicked reconnect on button send to main ...")
        self.emit(QtCore.SIGNAL("sendMainReconnect"), ["reconnect"])

    def sendStartStim(self):
        if self.isStimulationTurnedOn:
            print("clicked start button send to main ...")
            self.emit(QtCore.SIGNAL("sendMainStartStim"), ["start"])
            self.btnStartStim.setStyleSheet("background-color: green")
            self.btnPauseStim.setStyleSheet("background-color: grey")
            self.btnStartStim.setEnabled(False)
            self.btnPauseStim.setEnabled(True)

    def sendPauseStim(self):
        if self.isStimulationTurnedOn:
            print("clicked pause button send to main ...")
            self.emit(QtCore.SIGNAL("sendMainPauseStim"), ["pause"])
            self.btnStartStim.setStyleSheet("background-color: grey")
            self.btnPauseStim.setStyleSheet("background-color: red")
            self.btnStartStim.setEnabled(True)
            self.btnPauseStim.setEnabled(False)

    def sendTestStim(self):
        if self.isStimulationTurnedOn:
            print("clicked test button send to main ...")
            self.emit(QtCore.SIGNAL("sendMainTestStim"), ["test"])

    def sendSoundRiseLevelChanged(self):
        if self.isStimulationTurnedOn:
            print("clicked sound base level changed send to main ...")
            self.emit(QtCore.SIGNAL("sendMainSoundLevelChange"), ["sound-rise-level", self.SpBx_sound_rise_from_base_level_db.value()])

    def sendViewUpdateIntervalChanged(self):
        print("clicked view update interval changed send to main ...")
        self.updateSendOutDelaySeconds = self.SpBx_updateView.value()
        if self.updateSendOutDelaySeconds >= self.updateSendOutDelaySecondsAdjusted:
            self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySeconds
            self.sendUpdateIntervalAdjusted()

    def sendViewEEGLabelClicked(self):
        self.Label_EEGchan_clickcounter += 1
        if self.Label_EEGchan_clickcounter >= 10:
            self.Label_EEGchan.setStyleSheet('QPushButton {background-color: #000000; color: grey; border: 0px solid black;}')
            self.SpBx_EEGchan.setStyleSheet('QSpinBox {background-color: #000000; color: white; border: 1px solid gray;}')
            self.SpBx_EEGchan.setEnabled(True)
            self.Label_EEGchan.setText("EEG (" + self.montage.getChannelLabelReRefByChannelNumber(self.SpBx_EEGchan.value()) + ")")
        else:
            self.Label_EEGchan.setText("EEG (" + self.montage.getChannelLabelReRefByChannelNumber(self.SpBx_EEGchan.value()) + ")<"+str(10-self.Label_EEGchan_clickcounter))

    def sendViewEEGchannelChanged(self):
        print("clicked EEG channel changed send to main ...")
        if self.isStimulationTurnedOn:
            self.sendPauseStim()
        self.Label_EEGchan.setText("EEG (" + self.montage.getChannelLabelReRefByChannelNumber(self.SpBx_EEGchan.value()) + ")")
        # self.Label_p1.setText(title="EEG\n" + self.montage.getChannelDescriptionByChannelNumber(self.SpBx_EEGchan.value(),self.ca.realTimeFilterOrder,wrap=True))
        self.p1.getAxis("left").setLabel(axis="left", text="EEG " + self.montage.getChannelDescriptionByChannelNumber(self.SpBx_EEGchan.value(),self.ca.realTimeFilterOrder,wrap=False), **self.plotsYLabelStyle)
        self.emit(QtCore.SIGNAL("sendMainEEGchannelChange"), ["EEG-channel-change", self.SpBx_EEGchan.value()])


    def sendUpdateIntervalIncrease(self):
        self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySecondsAdjusted * 1.3
        if self.updateSendOutDelaySecondsAdjusted > 30.0:
            self.updateSendOutDelaySecondsAdjusted = 30
        self.sendUpdateIntervalAdjusted()

    def sendUpdateIntervalDecrease(self):
        self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySecondsAdjusted * 1.0 / 1.3
        if self.updateSendOutDelaySecondsAdjusted < self.updateSendOutDelaySeconds:
            self.updateSendOutDelaySecondsAdjusted = self.updateSendOutDelaySeconds
        self.sendUpdateIntervalAdjusted()

    def sendUpdateIntervalAdjusted(self):
        self.emit(QtCore.SIGNAL("sendMainUpdateIntervalChange"), ["update-view-refresh-interval", self.updateSendOutDelaySecondsAdjusted])

    def updateReceive(self, msg):

        prePlotTime = timeit.default_timer()
        viewSendingDelay = prePlotTime - msg[17]

        self.updatePlots(np.array(msg[0]), np.array(msg[1]), np.array(msg[2]), np.array(msg[3]), msg[4], np.array(msg[5]), np.array(msg[6]), np.array(msg[7]), msg[8], msg[9],
                         list(msg[10]), msg[11], msg[12], msg[13], msg[14], msg[15])

        internalSendLoopduration = (msg[17] - msg[18])
        postPlotTime = timeit.default_timer()

        updateDelay = postPlotTime - msg[18]

        plottingTime = (postPlotTime - prePlotTime)

        refreshInterval = msg[19]

        self.win.setWindowTitle(
            'Extended GUI signal viewer - by Frederik D. Weber  ---' + \
            " refresh rate: {:.2f}".format(round(refreshInterval * 1000, 2)) + ' ms' + \
            " send GUI: {:.2f}".format(round(viewSendingDelay * 1000, 2)) + ' ms' + \
            " plotting: {:.2f}".format(round(plottingTime * 1000, 2)) + ' ms' + \
            " algo stuck: {:.2f}".format(round(internalSendLoopduration * 1000, 2)) + ' ms')

        # time_sended = msg[17]
        # print("Signal Viewer Full: delay "+str(nowtime-time_sended)+" time sended "+str(time_sended)+" time received "+str(nowtime))

        # if self.lastUpdateTime is not None:
        if updateDelay > (1.1 * self.updateSendOutDelaySecondsAdjusted):
            self.sendUpdateIntervalIncrease()
        elif updateDelay < (0.8 * self.updateSendOutDelaySecondsAdjusted):
            self.sendUpdateIntervalDecrease()
        # else:
        #     self.sendUpdateIntervalDecrease()


    def reinitiateERPPlots(self):
        self.p0.clear()
        self.p0avg.clear()

    def updatePlots(self, t, y1, y2, y3, stimEvents, tERP, y0, y0avg, ERPavgCount, spindles_signalTimesIndices,y1_spindles,threshold_winsample_samplesago,threshold_EMGSignal_from_away_zero_disengage_algo,nextPlaylistItem,PlayListItemsPlayed,timeSinceLastStimulusPlayedSeconds):
        # start = timeit.default_timer()
        # self.reinitiateERPPlots()

        # timeEndwindow = self.timeSinceStart()
        # timeStartwindow = timeEndwindow - len(self.signalEEG) / self.fs
        # self.signalTime = np.linspace(timeStartwindow, timeEndwindow, len(self.signalEEG))
        # tempNSamples = len(self.signalEEG)

        # t = np.linspace(max(t[len(t)-1]-30,0), t[len(t)-1], len(y1))

        if self.threshold_EMGSignal_from_away_zero_disengage_algo != threshold_EMGSignal_from_away_zero_disengage_algo:
            self.threshold_EMGSignal_from_away_zero_disengage_algo = threshold_EMGSignal_from_away_zero_disengage_algo
            self.l_EMG_up.setValue(self.threshold_EMGSignal_from_away_zero_disengage_algo)
            self.l_EMG_down.setValue(-self.threshold_EMGSignal_from_away_zero_disengage_algo)

        if threshold_winsample_samplesago:
            if self.l1_th:
                self.p1.removeItem(self.l1_th)
            if len(t) > (threshold_winsample_samplesago[1]+threshold_winsample_samplesago[2]+2):
                self.l1_th = self.p1.plot(x=t[(len(t)-threshold_winsample_samplesago[1]-threshold_winsample_samplesago[2]):(len(t)-threshold_winsample_samplesago[2])], y=np.repeat(threshold_winsample_samplesago[0],threshold_winsample_samplesago[1] ), pen=pg.mkPen(color=(0, 255, 40), style=QtCore.Qt.DotLine, width=1), clear=False,
                                         style=QtCore.Qt.DotLine)

        if self.isRangeAuto:
            if self.isStimulationTurnedOn:
                self.p0.getAxis("left").getViewBox().setYRange(min(y0), max(y0), update=False)
                self.p0avg.getAxis("left").getViewBox().setYRange(min(y0avg), max(y0avg), update=False)
            self.p1.getAxis("left").getViewBox().setYRange(min(y1), max(y1), update=False)
            self.p2.getAxis("left").getViewBox().setYRange(min(y2), max(y2), update=False)
            self.p3.getAxis("left").getViewBox().setYRange(min(y3), max(y3), update=False)

        mint = min(t)
        maxt = max(t)
        mintERP = min(tERP)
        maxtERP = max(tERP)

        # print(maxt - mint)

        if self.isStimulationTurnedOn:
            self.p0.getAxis("bottom").getViewBox().setXRange(mintERP, maxtERP, padding=0, update=False)
            self.p0avg.getAxis("bottom").getViewBox().setXRange(mintERP, maxtERP, padding=0, update=False)
        self.p1.getAxis("bottom").getViewBox().setXRange(mint, maxt, padding=0, update=False)
        self.p2.getAxis("bottom").getViewBox().setXRange(mint, maxt, padding=0, update=False)
        self.p3.getAxis("bottom").getViewBox().setXRange(mint, maxt, padding=0, update=True)


        #self.doAntiAlias = not self.doAntiAlias
        if self.isStimulationTurnedOn:
            self.curve0.setData(tERP, y0, antialias=self.doAntiAlias)
            self.curve0avg.setData(tERP, y0avg, antialias=self.doAntiAlias)
        self.curve1.setData(t, y1, antialias=self.doAntiAlias)
        self.curve2.setData(t, y2, antialias=self.doAntiAlias)
        self.curve3.setData(t, y3, antialias=self.doAntiAlias)
        if self.doSpindleHighlight:
            self.curve1_spindles.setData(t[0:len(y1_spindles)], y1_spindles, antialias=self.doAntiAlias)


        if self.isStimulationTurnedOn:
            # self.Label_p0avg.setText("ERP (EEG) avg " + str(ERPavgCount))
            self.p0avg.getAxis("left").setLabel(axis="left", text="ERP (EEG) avg " + str(ERPavgCount))

        if self.isStimulationTurnedOn:
            self.Label_nextPlayListItem.setText("next item: "+str(nextPlaylistItem+1))
            self.Label_PlayListItemsPlayed.setText("# items: "+str(PlayListItemsPlayed))

            if timeSinceLastStimulusPlayedSeconds is not None:
                if timeSinceLastStimulusPlayedSeconds > 60.0:
                    self.Label_lastStimulusPlayed.setText("last item: " + "{:.2f}".format(round(timeSinceLastStimulusPlayedSeconds/60.0, 2))+" min")
                elif timeSinceLastStimulusPlayedSeconds > 3600.0:
                    self.Label_lastStimulusPlayed.setText("last item: " + "{:.2f}".format(round(timeSinceLastStimulusPlayedSeconds / 3600.0, 2)) + " h")
                else:
                    self.Label_lastStimulusPlayed.setText("last item: " + "{:.2f}".format(round(timeSinceLastStimulusPlayedSeconds, 2))+" s")

        if self.timeOfLightsOff is not None:
            temp_timeSinceLastLightsOff = (timeit.default_timer() - self.timeOfLightsOff)
            if temp_timeSinceLastLightsOff > 3600.0:
                self.Label_lastLightsOff.setText("last lights-off: " + "{:.2f}".format(round(temp_timeSinceLastLightsOff / 3600.0, 2)) + " h")
            else:
                self.Label_lastLightsOff.setText("last lights-off: " + "{:.2f}".format(round(temp_timeSinceLastLightsOff / 60.0, 2)) + " min")

        iOddEven = 0
        for se in stimEvents:
            l1 = self.p1.addLine(x=se.getTime())
            stextitem = pg.TextItem(text=se.getString(),
                                    color=(0, 0, 255, 192),
                                    html=None, anchor=(0, iOddEven % 2), border=None,
                                    fill=None, angle=12, rotateAxis=None)
            iOddEven += 1
            self.p1.addItem(stextitem)
            stextitem.setPos(se.getTime(), 0.0)
            self.stimsLinesQueue1Text.append([stextitem, se.getTime()])

            l1.setPen(color=(0, 0, 255,192), style=QtCore.Qt.DotLine)

            self.stimsLinesQueue1.append(l1)

        self.removeAllSpindleLine(self.stimsLinesQueueSpindle, self.p1)
        for sptp in spindles_signalTimesIndices:
            l1_sp = self.p1.plot(x=t[sptp], y=np.repeat(np.mean(y1[sptp]),len(sptp)), pen=pg.mkPen(color=(255, 255, 0, 192),style=QtCore.Qt.DotLine,width=1), clear=False, style=QtCore.Qt.DotLine)
            self.stimsLinesQueueSpindle.append(l1_sp)


        self.removeStimLine(self.stimsLinesQueue1, self.p1, t[0])
        self.removeStimText(self.stimsLinesQueue1Text, self.p1, t[0])

        # print(timeit.default_timer()-start)

    def removeAllSpindleLine(self, dq, p):
        for iPop in range(0, len(dq)):
            p.removeItem(dq.popleft())

    def removeStimLine(self, dq, p, tpassed):
        popCount = 0
        for infiniteLine in dq:
            if infiniteLine.value() <= tpassed:
                popCount += 1
            else:
                break
        for iPop in range(0, popCount):
            p.removeItem(dq.popleft())

    def removeStimText(self, dq, p, tpassed):
        popCount = 0
        for tupelTextItemAndTime in dq:
            tstim = tupelTextItemAndTime[1]
            if tstim <= tpassed:
                popCount += 1
            else:
                break
        for iPop in range(0, popCount):
            p.removeItem(dq.popleft()[0])

    def setForceStimToggle(self):
        if self.isStimAuto:
            self.setStimForced()
            self.btnForceEngageStimulation.setText("Force Stim.(A)")
        else:
            self.setStimAuto()
            self.btnForceEngageStimulation.setText("Auto Stim.(A)")

    def setStimAuto(self):
        if self.isStimulationTurnedOn:
            print("clicked Stim Forced button send to main auto stim...")
            self.emit(QtCore.SIGNAL("sendMainAutoStim"), ["auto-stim"])
            self.btnForceEngageStimulation.setStyleSheet("background-color: green")
            self.isStimAuto = True

    def setStimForced(self):
        if self.isStimulationTurnedOn:
            print("clicked Stim Forced button send to main auto stim...")
            self.emit(QtCore.SIGNAL("sendMainForcedStim"), ["forced-stim"])
            self.btnForceEngageStimulation.setStyleSheet("background-color: red")
            self.isStimAuto = False

    def setRangeToggle(self):
        if self.isRangeAuto:
            self.setRangeFixed()
            self.btnsetRangeFixedOrAuto.setText("[F")
        else:
            self.setRangeAuto()
            self.btnsetRangeFixedOrAuto.setText("[A")

    def setRangeAuto(self):
        if self.isStimulationTurnedOn:
            self.p0.getAxis("left").setTickSpacing()
            self.p0avg.getAxis("left").setTickSpacing()
        self.p1.getAxis("left").setTickSpacing()
        self.p2.getAxis("left").setTickSpacing()
        self.p3.getAxis("left").setTickSpacing()
        self.isRangeAuto = True

    def setRangeFixed(self):
        self.isRangeAuto = False
        if self.isStimulationTurnedOn:
            self.p0.getAxis("left").getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
            self.p0avg.getAxis("left").getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.p1.getAxis("left").getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.p2.getAxis("left").getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.p3.getAxis("left").getViewBox().enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.updateRangeERP()
        self.updateRangeERPavg()
        self.updateRangeEEG()
        self.updateRangeEOG()
        self.updateRangeEMG()

    def updateRangeERP(self):
        if self.isStimulationTurnedOn:
            self.p0.getAxis("left").getViewBox().setRange(yRange=self.RangeERPfixed, padding=None, update=True,
                                                          disableAutoRange=True)
            self.p0.getAxis("left").getViewBox().setLimits(yMin=self.RangeERPfixed[0], yMax=self.RangeERPfixed[1])
            self.p0.getAxis("left").setTickSpacing(max(self.RangeERPfixed) / 2.0, max(self.RangeERPfixed) / 4.0)

    def updateRangeERPavg(self):
        if self.isStimulationTurnedOn:
            self.p0avg.getAxis("left").getViewBox().setRange(yRange=self.RangeERPavgfixed, padding=None, update=True,
                                                             disableAutoRange=True)
            self.p0avg.getAxis("left").getViewBox().setLimits(yMin=self.RangeERPavgfixed[0], yMax=self.RangeERPavgfixed[1])
            self.p0avg.getAxis("left").setTickSpacing(max(self.RangeERPavgfixed) / 2.0, max(self.RangeERPavgfixed) / 4.0)

    def updateRangeEEG(self):
        self.p1.getAxis("left").getViewBox().setRange(yRange=self.RangeEEGfixed, padding=None, update=True,
                                                      disableAutoRange=True)
        self.p1.getAxis("left").getViewBox().setLimits(yMin=self.RangeEEGfixed[0], yMax=self.RangeEEGfixed[1])
        self.p1.getAxis("left").setTickSpacing(max(self.RangeEEGfixed) / 2.0, max(self.RangeEEGfixed) / 4.0)

    def updateRangeEOG(self):
        self.p2.getAxis("left").getViewBox().setRange(yRange=self.RangeEOGfixed, padding=None, update=True,
                                                      disableAutoRange=True)
        self.p2.getAxis("left").getViewBox().setLimits(yMin=self.RangeEOGfixed[0], yMax=self.RangeEOGfixed[1])
        self.p2.getAxis("left").setTickSpacing(max(self.RangeEOGfixed) / 2.0, max(self.RangeEOGfixed) / 4.0)

    def updateRangeEMG(self):
        self.p3.getAxis("left").getViewBox().setRange(yRange=self.RangeEMGfixed, padding=None, update=True,
                                                      disableAutoRange=True)
        self.p3.getAxis("left").getViewBox().setLimits(yMin=self.RangeEMGfixed[0], yMax=self.RangeEMGfixed[1])
        self.p3.getAxis("left").setTickSpacing(max(self.RangeEMGfixed) / 2.0, max(self.RangeEMGfixed) / 4.0)

    def setRangeFixedHigherEEG(self):
        if not self.isRangeAuto:
            if self.isStimulationTurnedOn:
                self.RangeERPfixed = np.array(self.RangeERPfixed * 1.25)
                self.RangeERPavgfixed = np.array(self.RangeERPavgfixed * 1.25)
            self.RangeEEGfixed = np.array(self.RangeEEGfixed * 1.25)
            self.updateRangeERP()
            self.updateRangeERPavg()
            self.updateRangeEEG()

    def setRangeFixedHigherEOG(self):
        if not self.isRangeAuto:
            self.RangeEOGfixed = np.array(self.RangeEOGfixed * 1.25)
            self.updateRangeEOG()

    def setRangeFixedHigherEMG(self):
        if not self.isRangeAuto:
            self.RangeEMGfixed = np.array(self.RangeEMGfixed * 1.25)

            self.updateRangeEMG()

    def setRangeFixedLowerEEG(self):
        if not self.isRangeAuto:
            if self.isStimulationTurnedOn:
                self.RangeERPfixed = np.array([min(self.RangeERPfixed[0] * 0.8, -self.EEGstartRangeExtension * 0.8 ** 12),
                                               max(self.RangeERPfixed[1] * 0.8, self.EEGstartRangeExtension * 0.8 ** 12)])
                self.RangeERPavgfixed = np.array([min(self.RangeERPavgfixed[0] * 0.8, -self.EEGstartRangeExtension * 0.8 ** 12),
                                                  max(self.RangeERPavgfixed[1] * 0.8, self.EEGstartRangeExtension * 0.8 ** 12)])

            self.RangeEEGfixed = np.array([min(self.RangeEEGfixed[0] * 0.8, -self.EEGstartRangeExtension * 0.8 ** 12),
                                           max(self.RangeEEGfixed[1] * 0.8, self.EEGstartRangeExtension * 0.8 ** 12)])
            self.updateRangeERP()
            self.updateRangeERPavg()
            self.updateRangeEEG()

    def setRangeFixedLowerEOG(self):
        if not self.isRangeAuto:
            self.RangeEOGfixed = np.array([min(self.RangeEOGfixed[0] * 0.8, -self.EOGstartRangeExtension * 0.8 ** 12),
                                           max(self.RangeEOGfixed[1] * 0.8, self.EOGstartRangeExtension * 0.8 ** 12)])
            self.updateRangeEOG()

    def setRangeFixedLowerEMG(self):
        if not self.isRangeAuto:
            self.RangeEMGfixed = np.array([min(self.RangeEMGfixed[0] * 0.8, -self.EMGstartRangeExtension * 0.8 ** 12),
                                           max(self.RangeEMGfixed[1] * 0.8, self.EMGstartRangeExtension * 0.8 ** 12)])
            self.updateRangeEMG()

if __name__ == "__main__":

    app = QtGui.QApplication([])

    saveSD = False
    #saveSD_sendChar = 'J'
    saveSD_sendChar = 'no'
    doTesting = False
    simulateFromCSV = False
    #baudrate_serial = 115200
    #baudrate_serial = 230400
    baudrate_serial = 921600
    nChannels = 8
    FS = 250.0
    FS_SD = 250.0
    FS_SD_char = b'6'
    FS_ds = False
    doRealTimeStreaming = True
    subject = "subj1"
    writeEDF = True
    # giveNameChannelsByMapping = True
    condition = 0
    doSham = False
    doShamObfuscation = False
    shamObfuscationCode = ''
    subject_condition_encoded_file_path = '<unused>'
    doClosedLoopNotOpenLoop = True
    doClosedLoopRepeatSequence = True
    ThresholdDownStateDetectionPassBelow = -80.0
    waitForFurtherDipInThreshold = True
    ThresholdUpStateDetectionPassAbove = -60.0
    ThresholdUpStateDetectionPassBelow = 200.0
    updateThresholdIntervalSec = 0.0
    updateThresholdTimeWindowSec = 3.0
    isStimulationTurnedOn = False
    sound_base_level_dB = -60
    soundVolume = 0.50
    masterVolumePercent = int(100)
    stimuliSoundFiles = ["stimuli/pinknoise/pink_noise_50_ms_44.1kHz_16bit_integer_full_db.wav"]
    stimuliListFilePath = "NA"
    stimuliPlayListFilePath = "NA"
    updateSendOutDelaySeconds = 1.0
    soundBufferSize = 4096  # power of 2, divided by the sampling rate of 44100 Hz gives the delay 1024 is possible with good drivers
    firstDownToUpstateDelayInSec = 0.2
    #secondUpToUpstateDelayInSec = 1.075

    # channelEEG = None
    # channelEMG = 1
    # channelEOG = 2
    # channelEEGrefs = None

    stimulusList = None
    stimulusPlayList = None
    threshold_EEGSignal_from_away_zero_disengage_algo = 350 # in microVOlt
    threshold_EOGSignal_from_away_zero_disengage_algo = 600 # in microVOlt
    threshold_EMGSignal_from_away_zero_disengage_algo = 25  # in microVOlt

    language = "en"

    soundFrequency = 44100  # in Hz

    doSpindleHighlight = True

    filterHP_EEG_spindle_freq = 11.25
    filterLP_EEG_spindle_freq = 14.75

    spindle_amplitude_threshold_detect_microVolts = 17.5
    spindle_amplitude_threshold_begin_end_microVolts = 12.5
    spindle_amplitude_max_microVolts = 100.0

    spindle_min_duration_seconds = 0.5
    spindle_max_duration_seconds = 2.0

    # pick +12 dB louder of stimuli than base level for hearing threshold volume
    sound_rise_from_base_level_db = 18

    realTimeFilterOrderSpindles = 250

    doAntiAlias = True
    useOpenGL = False
    doDownSamplingForPlot = False

    prefilterEDF_hp = 0.16
    correctInvertedChannels = True
    edfAnnotationChannels = 7
    exportEDFAnnotations = True;

    playListStartIndex = 0

    doOutputFileLogging = True


    playBackgroundNoise = False

    useDefaultSettings = True

    extendedDisplayProcessing = False

    useVispyPlot = False


    main = MainWindow()
    # main.show()

    subject, okpressed = main.getText("Provide Subject ID", "Subject:", subject)
    subject = str(subject).strip()
    if not okpressed or subject == "":
        sys.exit(0)

    now = datetime.datetime.now()
    temp_time_stamp = '%d-%d-%d_%d-%d-%d' % (now.year, now.month, now.day, now.hour, now.minute, now.second)

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s:%(levelname)s:%(name)s:%(message)s',
        filename="log_terminal/" + subject + "_" + temp_time_stamp + '.connect.output.log' + '.txt',
        filemode='a'
    )

    options = ("Default", "Details")
    res, okpressed = main.getChoice("Default Settings?", "Settings:",
                                    options,
                                    current_item_int=0)
    if not okpressed:
        sys.exit(0)

    if res == "Default":
        useDefaultSettings = True
    elif res == "Details":
        useDefaultSettings = False
    else:
        print("Default settings option " + res + " not handled yet")
        sys.exit(0)

    if not useDefaultSettings:
        options = ("terminal only", "log file only")
        res, okpressed = main.getChoice("Logging?", "logging:",
                                        options,
                                        current_item_int=1)
        if not okpressed:
            sys.exit(0)

        if res == "terminal only":
            doOutputFileLogging = False
        elif res == "log file only":
            doOutputFileLogging = True
        else:
            print("loging option " + res + " not handled yet")
            sys.exit(0)

    if doOutputFileLogging:
        stdout_logger = logging.getLogger('STDOUT')
        sl = StreamToLogger(stdout_logger, logging.INFO)
        sys.stdout = sl

        stderr_logger = logging.getLogger('STDERR')
        sl = StreamToLogger(stderr_logger, logging.ERROR)
        sys.stderr = sl


    nChannel_options = ("16","8")
    nChannel_res, okpressed = main.getChoice("#Channels", "Number of channels:",
                                             nChannel_options,
                                             current_item_int=1)
    if not okpressed:
        sys.exit(0)

    nChannels = int(nChannel_res)
    edfAnnotationChannels = nChannels-1

    useDaisyModule = False
    if nChannels == 16:
        useDaisyModule = True

    montage_filepath = 'montages/default.montage.' + str(nChannels) + '.channel.tsv'

    if not useDefaultSettings:
        montage_filepath = main.getFile("Montage File", initFolder=montage_filepath, filterList='TSV (*.tsv)')

    try:
        montage = Montage.Montage(filepath=montage_filepath, nChannels=nChannels)
    except:
        okpressed = main.showMessageBox("Montage invalid", "the montage in file\n" + montage_filepath + "\nis invalid or insufficient for the current setup!",
                                        True, False, True, isOKbuttonDefault=True)
        sys.exit(0)

    if len(montage.rerefchannelLabelsOrderedByChannelNumber) > 0:

        options = ("Full Signal Viewer (slow refresh rate)", "Only Recording View (fast refresh rate)")
        res, okpressed = main.getChoice("Use Full Signal Viewer?", "Use:",
                                              options,
                                              current_item_int=1)

        if not okpressed:
            sys.exit(0)

        if res == "Full Signal Viewer (slow refresh rate)":
            extendedDisplayProcessing = True
        elif res == "Only Recording View (fast refresh rate)":
            extendedDisplayProcessing = False
        else:
            print("Full Signal Viewer option " + res + " not handled yet")
            sys.exit(0)


    if useDaisyModule:
        FS = FS / 2.0

    if nChannels == 8:
        FS_ds_options = ("250 Hz (all)", "125 Hz (odd)")
        FS_ds_res, okpressed = main.getChoice("Downsample Streaming?", "sampling rate:",
                                               FS_ds_options,
                                                 current_item_int=0)
        if not okpressed:
            sys.exit(0)

        if FS_ds_res == "250 Hz (all)":
            FS_ds = False
        elif FS_ds_res == "125 Hz (odd)":
            FS_ds = True
        else:
            print("FS downsample option " + FS_ds_res + " not handled yet")
            sys.exit(0)

    if FS_ds:
        FS = FS / 2.0


    SDcard_option_dict = collections.OrderedDict()

    if nChannels == 16:
        SDcard_option_dict['no'] = "do not record on SD"
        SDcard_option_dict['G'] = "37 min (67MB)"
        SDcard_option_dict['H'] = "1.25 hours (134MB)"
        SDcard_option_dict['J'] = "2.5 hours (267MB)"
        SDcard_option_dict['K'] = "7.5 hours (800MB)"
        SDcard_option_dict['L'] = "15 hours (1600MB)"

        SDcard_option_dict_byte = collections.OrderedDict()

        SDcard_option_dict_byte[b'no'] = "do not record on SD"
        SDcard_option_dict_byte[b'G'] = "37 min (67MB)"
        SDcard_option_dict_byte[b'H'] = "1.25 hours (134MB)"
        SDcard_option_dict_byte[b'J'] = "2.5 hours (267MB)"
        SDcard_option_dict_byte[b'K'] = "7.5 hours (800MB)"
        SDcard_option_dict_byte[b'L'] = "15 hours (1600MB)"

    elif nChannels == 8:
        SDcard_option_dict['no'] = "do not record on SD"
        SDcard_option_dict['G'] = "1 hour (67MB)"
        SDcard_option_dict['H'] = "2 hours (134MB)"
        SDcard_option_dict['J'] = "4 hours (267MB)"
        SDcard_option_dict['K'] = "12 hours (800MB)"
        SDcard_option_dict['L'] = "24 hours (1600MB)"

        SDcard_option_dict_byte = collections.OrderedDict()

        SDcard_option_dict_byte[b'no'] = "do not record on SD"
        SDcard_option_dict_byte[b'G'] = "1 hour (67MB)"
        SDcard_option_dict_byte[b'H'] = "2 hours (134MB)"
        SDcard_option_dict_byte[b'J'] = "4 hours (267MB)"
        SDcard_option_dict_byte[b'K'] = "12 hours (800MB)"
        SDcard_option_dict_byte[b'L'] = "24 hours (1600MB)"

    saveSD_rep_str, okpressed = main.getChoice("Record on SD card", "record on SD card:",
                                               SDcard_option_dict.values(), current_item_int=SDcard_option_dict.keys().index(saveSD_sendChar))

    if not okpressed:
        sys.exit(0)

    saveSD_sendChar = SDcard_option_dict.keys()[SDcard_option_dict.values().index(saveSD_rep_str)]

    saveSD_sendChar_byte = SDcard_option_dict.keys()[SDcard_option_dict_byte.values().index(saveSD_rep_str)]

    if saveSD_sendChar == "no":
        saveSD = False
    else:
        saveSD = True

    sendDeviceStopAfterSerialStop = not saveSD

    if saveSD:

        onlySDrecording_options = ("SD & real-time", "SD only")
        onlySDrecording_res, okpressed = main.getChoice("Realtime?", "Recording:",
                                                        onlySDrecording_options,
                                               current_item_int=0)
        if not okpressed:
            sys.exit(0)

        if onlySDrecording_res == "SD & real-time":
            doRealTimeStreaming = True
        elif onlySDrecording_res == "SD only":
            doRealTimeStreaming = False
        else:
            print("Recording option " + onlySDrecording_res + " not handled yet")
            sys.exit(0)

        if not doRealTimeStreaming:

            # nFS_SD_options = ("250 Hz (online)", "500 Hz (offline)","1000 Hz (offline)","2000 Hz (offline)","4000 Hz (offline)","8000 Hz (offline)","16000 Hz (offline)")
            # nFS_SD_res, okpressed = main.getChoice("SD card", "SD sampling rate:",
            #                                     nFS_SD_options,
            #                                          current_item_int=0)
            # if not okpressed:
            #     sys.exit(0)

            nFS_SD_res = "250 Hz (online)"

            if nFS_SD_res == "250 Hz (online)":
                FS_SD = 250.0
                FS_SD_char = b'~6'
            elif nFS_SD_res == "500 Hz (offline)":
                FS_SD = 500.0
                FS_SD_char = b'~5'
            elif nFS_SD_res == "1000 Hz (offline)":
                FS_SD = 1000.0
                FS_SD_char = b'~4'
            elif nFS_SD_res == "2000 Hz (offline)":
                FS_SD = 2000.0
                FS_SD_char = b'~3'
            elif nFS_SD_res == "4000 Hz (offline)":
                FS_SD = 4000.0
                FS_SD_char = b'~2'
            elif nFS_SD_res == "8000 Hz (offline)":
                FS_SD = 8000.0
                FS_SD_char = b'~1'
            elif nFS_SD_res == "16000 Hz (offline)":
                FS_SD = 16000.0
                FS_SD_char = b'~0'


    realTimeFilterOrder = round(FS/125.0)


    if doRealTimeStreaming:

        if not useDefaultSettings:
            writeEDF_option = ("write", "no")
            writeEDF_res, okpressed = main.getChoice("Write EDF+/BDF+", "write EDF+/BDF+:", writeEDF_option, current_item_int=0)

            if not okpressed:
                sys.exit(0)
            if writeEDF_res == "write":
                writeEDF = True
            elif writeEDF_res == "no":
                writeEDF = False
            else:
                print("EDF/BDF, write option " + writeEDF_res + " not handled yet")
                sys.exit(0)

            if writeEDF:
                # giveNameChannelsByMapping_option = ("channel name", "channel number")
                # giveNameChannelsByMapping_res, okpressed = main.getChoice("EDF/BDF, Label Channels?", "EDF/BDF, Label channels:", giveNameChannelsByMapping_option, current_item_int=0)
                #
                # if not okpressed:
                #     sys.exit(0)
                # if giveNameChannelsByMapping_res == "channel name":
                #     giveNameChannelsByMapping = True
                # elif giveNameChannelsByMapping_res == "channel number":
                #     giveNameChannelsByMapping = False
                # else:
                #     print("giveNameChannelsByMapping option " + giveNameChannelsByMapping_res + " not handled yet")
                #     sys.exit(0)

                EDFformat_option = ("BDF (unfiltered)", "EDF (pre-filtered)")
                EDFformat_option_res, okpressed = main.getChoice("write Format BDF or EDF?", "write format", EDFformat_option,
                                                                          current_item_int=1)

                if not okpressed:
                    sys.exit(0)
                if EDFformat_option_res == "BDF (unfiltered)":
                    prefilterEDF_hp = None
                elif EDFformat_option_res == "EDF (pre-filtered)":
                    prefilterEDF_hp = 0.16
                else:
                    print("EDFformat option " + EDFformat_option_res + " not handled yet")
                    sys.exit(0)

                if prefilterEDF_hp is not None:
                    prefilterEDF_hp, okpressed = main.getDouble("EDF, prefilter High-Pass", "EDF HP prefilter [Hz]:", 0.01, 30.0, 5, prefilterEDF_hp)

                if prefilterEDF_hp is None:
                   okpressed = main.showMessageBox("Will write BDF", "BDF format, NO filtering.\nPysical maximum/minimum is that of OpenBCI device with 24x gain\n with +187500/-187500 microVolt until saturation.\nPrecision ~0.022352 microVolt",
                                                   True, False, True, isOKbuttonDefault=True)
                else:
                    okpressed = main.showMessageBox("Will write EDF and filter", "EDF with pre-filter of "+ str(prefilterEDF_hp) + " Hz, Butterworth order 1 sample, \nPhysical maximum/minimum is +3277/-+3277 microV until saturation.\nPrecision ~0.100000 microVolt" ,
                                                    True, False, True, isOKbuttonDefault=True)
                    if not okpressed:
                        sys.exit(0)


                option = ("EDF/BDF keep inversion in non-bipolar channels", "EDF/BDF correct inversion in non-bipolar channels")
                res, okpressed = main.getChoice("EDF/BDF, correct inversion?", "Inversion correction (SR2B as ref):", option,
                                                           current_item_int=1)
                if not okpressed:
                    sys.exit(0)
                if res == "EDF/BDF keep inversion in non-bipolar channels":
                    correctInvertedChannels = False
                elif res == "EDF/BDF correct inversion in non-bipolar channels":
                    correctInvertedChannels = True
                else:
                    print("EDF/BDF inversion option " + res + " not handled yet")
                    sys.exit(0)



                edfAnnotationChannelsIndex, okpressed = main.getInteger("EDF/BDF", "#Annotation Chan.",
                                                                 0, 64, 1, edfAnnotationChannels)
                if not okpressed:
                    sys.exit(0)
                edfAnnotationChannels = edfAnnotationChannelsIndex

                if edfAnnotationChannels > (nChannels-1):
                    okpressed = main.showMessageBox("EDF/BDF # annotation channels",
                                                    "EDF/BDF annotation channel set to " + str(edfAnnotationChannels) + "\nMore than " + (edfAnnotationChannels) + " time the seconds of the recording length can be stored.\n However if there are more annotations than channels\nthen there might be problems reading this in some software.",
                                                    True, False, True, isOKbuttonDefault=True)
                    if not okpressed:
                        sys.exit(0)


                exportEDFAnnotation_option = ("export", "no")
                exportEDFAnnotation_res, okpressed = main.getChoice("Export EDF+/BDF+ annotation", "Export EDF/BDF annotation:", exportEDFAnnotation_option, current_item_int=0)

                if not okpressed:
                    sys.exit(0)
                if exportEDFAnnotation_res == "export":
                    exportEDFAnnotations = True
                elif exportEDFAnnotation_res == "no":
                    exportEDFAnnotations = False
                else:
                    print("EDF/BDF, export annotation option " + exportEDFAnnotation_res + " not handled yet")
                    sys.exit(0)

        # eegchannels_dict = collections.OrderedDict()
        #
        # eegchannels_dict[0] = "0 (Cz/Ref)"
        # eegchannels_dict[5] = "5 (C3)"
        # eegchannels_dict[6] = "6 (C4)"
        # eegchannels_dict[7] = "7 (Switch)"
        # eegchannels_dict[8] = "8 (Feedback/ECG)"
        # channelEEG = 5
        #
        # if nChannels > 8:
        #     channelEEG = 0
        #     eegchannels_dict[9] = "9 (F3)"
        #     eegchannels_dict[10] = "10 (Fz)"
        #     eegchannels_dict[11] = "11 (F4)"
        #     eegchannels_dict[12] = "12 (P3)"
        #     eegchannels_dict[13] = "13 (Pz)"
        #     eegchannels_dict[14] = "14 (P4)"
        #     eegchannels_dict[15] = "15 (O1)"
        #     eegchannels_dict[16] = "16 (O2)"
        #
        # eegchannel_rep_str, okpressed = main.getChoice("GUI, pick EEG Channel", "GUI, EEG channel:",
        #                                                eegchannels_dict.values(), current_item_int=np.where(
        #         np.array(eegchannels_dict.keys()) == int(channelEEG))[0][0])
        # if not okpressed:
        #     sys.exit(0)
        #
        # channelEEG = int(eegchannel_rep_str[0:2].trimmed())
        #
        # channelEEGrefs_option = ("3 (A1)", "4 (A2)", "3,4 (A1~A2)")
        # channelEEGrefs_choice, okpressed = main.getChoice("GUI, pick EEG reference channel(s)", "GUI, reference channels:", channelEEGrefs_option, current_item_int=2)
        #
        # if not okpressed:
        #     sys.exit(0)
        # if channelEEGrefs_choice == "3 (A1)":
        #     channelEEGrefs = [3]
        # elif channelEEGrefs_choice == "4 (A2)":
        #     channelEEGrefs = [4]
        # elif channelEEGrefs_choice == "3,4 (A1~A2)":
        #     channelEEGrefs = [3, 4]
        # else:
        #     print("EEG reference option " + channelEEGrefs_choice + " not handled yet")
        #     sys.exit(0)
        #
        # if ((channelEEG == 7) or (channelEEG == 8)):
        #     channelEEGrefs = None

        stimulation_option = ("Do a Stimulation", "Only view Recording")
        stim_condition, okpressed = main.getChoice("Stimulation?", "Stimulation option:", stimulation_option,
                                                       current_item_int=1)
        if not okpressed:
            sys.exit(0)
        if stim_condition == "Do a Stimulation":
            isStimulationTurnedOn = True
        elif stim_condition == "Only view Recording":
            isStimulationTurnedOn = False
        else:
            print("stimulation option " + stim_condition + " not handled yet")
            sys.exit(0)

        if isStimulationTurnedOn:

            agegroup_options = ("Adult (20-35 yrs.)", "Child (5-12 yrs.)")
            agegroup_res, okpressed = main.getChoice("Agegroup?", "Agegroup:",
                                                     agegroup_options,
                                                     current_item_int=0)
            if not okpressed:
                sys.exit(0)

            if agegroup_res == "Adult (20-35 yrs.)":
                pass
            elif agegroup_res == "Child (5-12 yrs.)":
                filterHP_EEG_spindle_freq = 10.5
                filterLP_EEG_spindle_freq = 14.0
                spindle_amplitude_threshold_detect_microVolts = 25
                spindle_amplitude_threshold_begin_end_microVolts = 17.5
                spindle_amplitude_max_microVolts = 150.0
                threshold_EEGSignal_from_away_zero_disengage_algo = 600  # in microVOlt
                threshold_EOGSignal_from_away_zero_disengage_algo = 700  # in microVOlt
                threshold_EMGSignal_from_away_zero_disengage_algo = 25  # in microVOlt
                ThresholdDownStateDetectionPassBelow = -130.0
                ThresholdUpStateDetectionPassAbove = -90.0
                ThresholdUpStateDetectionPassBelow = 300.0
            else:
                print("Agegroup option " + agegroup_res + " not handled yet")
                sys.exit(0)


            subject_volume_file = "data/subject/" + subject + ".volume_settings.txt"

            try:
                f = open(subject_volume_file, "r")
                reader = csv.reader(f, delimiter=',')  # creates the reader object
                for row in reader:  # iterates the rows of the file in orders
                    last_line = row

                f_subject = last_line[0]
                f_date = last_line[1]
                f_sound_base_level = last_line[2]
                f_volume = float(last_line[3])
                f_volume_master = int(last_line[4])

                f.close()

                masterVolumePercent = f_volume_master
                soundVolume = f_volume
                sound_base_level_dB = f_sound_base_level
            except:
                print('Subject volume file not found or accessible')
                okpressed = main.showMessageBox("Volume file not found or accessible", "Subject's volume file " + subject_volume_file +
                                    " could not be read.\nCheck subject ID, or create a file with program \"hearing_threshold\"! Otherwise default values will be used in the following!",
                                    True, False, True,isOKbuttonDefault=False)
                if not okpressed:
                    sys.exit(0)

            masterVolumePercent, okpressed = main.getInteger("Set Master Volume", "Master volume %:",
                                                             1, 100, 3, masterVolumePercent)
            if not okpressed:
                sys.exit(0)

            okpressed = main.showMessageBox("DON'T TOUCH VOLUME NOW!", "DO NOT touch the system's or computer's volume control now anymore!\nAlso make sure the audio is not muted by the system or in any other way.",
                                            True, False, True, isOKbuttonDefault=True)
            if not okpressed:
                sys.exit(0)

            # get PCH output card and Master Control for mixer selection
            alsaaudio.Mixer(control="Master", cardindex=np.where(np.array(alsaaudio.cards()) == u'PCH')[0][0]).setvolume(masterVolumePercent)

            sound_base_levels_dB_dict = collections.OrderedDict()

            sound_base_levels_dB_dict[-84] = "-84 dB"
            sound_base_levels_dB_dict[-72] = "-72 dB"
            sound_base_levels_dB_dict[-60] = "-60 dB"
            sound_base_levels_dB_dict[-48] = "-48 dB"
            sound_base_levels_dB_dict[-36] = "-36 dB"
            sound_base_levels_dB_dict[-24] = "-24 dB"

            sound_base_level_rep_str, okpressed = main.getChoice("Pick Sound Base Level", "sound base level:",
                                                                 sound_base_levels_dB_dict.values(), current_item_int=
                                                                 np.where(np.array(sound_base_levels_dB_dict.keys()) == int(
                                                                     sound_base_level_dB))[0][0])
            if not okpressed:
                sys.exit(0)
            sound_base_level_dB = int(sound_base_level_rep_str[0:3])

            soundVolume, okpressed = main.getDouble("Pick Subject Volume", "Subject\'s volume:", 0.0, 1.0, 6,
                                                               soundVolume)
            if not okpressed:
                sys.exit(0)

            if not useDefaultSettings:
                options = ("silence", "white noise")
                res, okpressed = main.getChoice("Background noise", "cont. background noise:", options,
                                                                  current_item_int=0)
                if not okpressed:
                    sys.exit(0)

                if res == "silence":
                    playBackgroundNoise = False
                elif res == "white noise":
                    playBackgroundNoise = True
                else:
                    print("Background noise option " + options + " not handled yet")
                    sys.exit(0)


                soundBufferSize_options_display = ("8192 (186 ms)", "4096 (93 ms)", "2048 (46.4 ms)", "1024 (23.2 ms)", "512 (11.6 ms)", "256 (5.8 ms)", "128 (2.9 ms)", "64  (1.5 ms)", "32  (<1 ms)")
                soundBufferSize_res, okpressed = main.getChoice("Sound buffer size", "sound buffer size: ",
                                                                soundBufferSize_options_display,
                                                                current_item_int=3)
                if not okpressed:
                    sys.exit(0)

                soundBufferSize = int(soundBufferSize_res[0:4].trimmed())

                if soundBufferSize < 1024:

                    okpressed = main.showMessageBox("Soundbuffer critical", "The sound buffer size " + soundBufferSize_res +
                                                    " is very low.\n Make sure you have good (sound) hardware (below 1024, is unrealistic) and the system setup to not distort sounds!\nOtherwise restart and choose conservatively 4096 or try 1024 as buffer size.",
                                                    True, False, True, isOKbuttonDefault=False)
                    if not okpressed:
                        sys.exit(0)



                sc = ShamCrypter.ShamCrypter()

                doShamObfuscation_types = ("no", "obfuscate")
                doShamObfuscation_opt, okpressed = main.getChoice("Sham Obfuscation", "Obfuscate sham condition:", doShamObfuscation_types,
                                                           current_item_int=0)
                if not okpressed:
                    sys.exit(0)
                if doShamObfuscation_opt == "no":
                    doShamObfuscation = False
                elif doShamObfuscation_opt == "obfuscate":
                    doShamObfuscation = True
                else:
                    print("doShamObfuscation option " + doShamObfuscation_opt + " not handled yet")
                    sys.exit(0)


            if doShamObfuscation:
                subject_condition_encoded_file_path = main.getFile("Encoded Experimental Condition File", initFolder='data/experiment', filterList='CSV and TXT (*.csv *.txt)')
                if sc.isSubjectContainedInSubjectConditionListWriteEcrypted(subject,subject_condition_encoded_file_path):
                    tempres = sc.isStimOrShamConditionBySubjectConditionListWriteEcrypted(subject, subject_condition_encoded_file_path)
                    if tempres[0]:
                        condition_string = tempres[1]
                        shamObfuscationCode = tempres[2]
                        if condition_string == "stim":
                            doSham = False
                        elif condition_string == "sham":
                            doSham = True
                        else:
                            okpressed = main.showMessageBox("Sham Obfuscation not matching", "Obfuscation did not work",
                                                            True, False, True, isOKbuttonDefault=True)
                            sys.exit(0)
                        okpressed = main.showMessageBox("Sham Obfuscation Code", "Your obfuscation code for subject " + subject + " is\n"
                                                         + shamObfuscationCode,
                                                        True, False, True, isOKbuttonDefault=True)
                        if not okpressed:
                            sys.exit(0)
                    else:
                        okpressed = main.showMessageBox("Sham Obfuscation not able to decode", "Obfuscation did not work, not able to decode",
                                                        True, False, True, isOKbuttonDefault=True)
                        sys.exit(0)
                else:
                    okpressed = main.showMessageBox("Subject not contained in Encoded Experimental Condition File", "File " + subject_condition_encoded_file_path +
                                                    "\ndid not contain subject " + subject + ".!\ncheck the file or subject name again and restart.",
                                                    True, False, True, isOKbuttonDefault=False)
                    if not okpressed:
                        sys.exit(0)

            else:
                stimulation_types = ("Stim", "Sham")
                stim_condition, okpressed = main.getChoice("Pick Stim/Sham", "Stimulation condition:", stimulation_types,
                                                           current_item_int=0)
                if not okpressed:
                    sys.exit(0)
                if stim_condition == "Stim":
                    doSham = False
                elif stim_condition == "Sham":
                    doSham = True
                else:
                    print("stimulation condition " + stim_condition + " not handled yet")
                    sys.exit(0)

            stimulation_method = ("Open-loop", "Closed-loop")
            stim_method, okpressed = main.getChoice("Pick Open/Closed", "Stimulation method:", stimulation_method,
                                                    current_item_int=1)
            if not okpressed:
                sys.exit(0)
            if stim_method == "Open-loop":
                doClosedLoopNotOpenLoop = False
            elif stim_method == "Closed-loop":
                doClosedLoopNotOpenLoop = True
            else:
                print("stimulation method " + stim_method + " not handled yet")
                sys.exit(0)


            stimulusPlayer = clsa.StimulusPlayer(soundBufferSize, sound_base_level_dB, soundVolume, sound_rise_from_base_level_db, doClosedLoopNotOpenLoop, doSham, main, soundFrequency,playBackgroundNoise=playBackgroundNoise)
            stimuliListFilePath = stimulusPlayer.stimuliListFilePath
            stimuliPlayListFilePath = stimulusPlayer.stimuliPlayListFilePath

            doClosedLoopRepeatSequence = (stimulusPlayer.playListLength <= 2)

            if not doClosedLoopRepeatSequence:
                playListStartIndex1, okpressed = main.getInteger("Playlist Start", "Playlist item [1..]%:",
                                                             1, stimulusPlayer.playListLength, 1, playListStartIndex + 1)
                if not okpressed:
                    sys.exit(0)
                playListStartIndex = playListStartIndex1 - 1

                if playListStartIndex > 0:
                    okpressed = main.showMessageBox("Start Stimuli is", "The first stimuli to play is\n"
                                                    + stimulusPlayer.stimuliPlayList[playListStartIndex][0],
                                                    True, False, True, isOKbuttonDefault=True)
                    if not okpressed:
                        sys.exit(0)

                stimulusPlayer.resetPlayList(playListStartIndex=playListStartIndex)




            #firstDownToUpstateDelayInSec = 0.3
            #secondUpToUpstateDelayInSec = 1.075

            if doClosedLoopNotOpenLoop:

                ThresholdDownStateDetectionPassBelow, okpressed = main.getDouble("Pick Down-State Threshold (SO)",
                                                                        "down-state threshold:", -300.0, -20.0, 1,
                                                                                 ThresholdDownStateDetectionPassBelow)
                if not okpressed:
                    sys.exit(0)

                waitForFurtherDipInThreshold_options = ("Wait", "Immediate")
                waitForFurtherDipInThreshold_option, okpressed = main.getChoice("Wait for Threshold Dip?", "Wait (negative) dip:", waitForFurtherDipInThreshold_options,
                                                              current_item_int=0)
                if not okpressed:
                    sys.exit(0)
                if waitForFurtherDipInThreshold_option == "Wait":
                    waitForFurtherDipInThreshold = True
                elif waitForFurtherDipInThreshold_option == "Immediate":
                    waitForFurtherDipInThreshold = False
                else:
                    print("wait for further dip in threshold option " + waitForFurtherDipInThreshold_option + " not handled yet")
                    sys.exit(0)


                ThresholdUpStateDetectionPassAbove, okpressed = main.getDouble("Pick Up-State Threshold Above (SO)",
                                                                                 "up-state threshold above:", -300.0, 300.0, 1,
                                                                               ThresholdUpStateDetectionPassAbove)
                if not okpressed:
                    sys.exit(0)

                ThresholdUpStateDetectionPassBelow, okpressed = main.getDouble("Pick Up-State Threshold Below (SO)",
                                                                                   "up-state threshold below:", -300.0, 300.0, 1,
                                                                               ThresholdUpStateDetectionPassBelow)
                if not okpressed:
                    sys.exit(0)

                firstDownToUpstateDelayInSec, okpressed = main.getDouble("Down-To-Upstate Interval", "down-to-upsate (seconds):",
                                                                         round(stimulusPlayer.soundlatency_seconds,3)+0.001, 2.0, 3, firstDownToUpstateDelayInSec)

                if not okpressed:
                    sys.exit(0)

                updateThresholdIntervalSec, okpressed = main.getDouble("Threshold Update Interval", "threshold update (seconds):",
                                                                         0.0, 1200.0, 3, updateThresholdIntervalSec)

                if not okpressed:
                    sys.exit(0)

                updateThresholdTimeWindowSec, okpressed = main.getDouble("Threshold Update Window", "threshold update window (seconds):",
                                                                       0.0, 1200.0, 3, updateThresholdTimeWindowSec)

                if not okpressed:
                    sys.exit(0)


                # secondUpToUpstateDelayInSec, okpressed = main.getDouble("Down To Upstate Interval", "down to upsate (seconds):",
                #                                                         0.5, 2, 3, secondUpToUpstateDelayInSec)
                # if not okpressed:
                #     sys.exit(0)

            if not useDefaultSettings:
                threshold_EEGSignal_from_away_zero_disengage_algo, okpressed = main.getDouble("EEG Auto-stop Stimulation",
                                                                                              "EEG from 0.0: ", 5.0, 1000.0, 1, threshold_EEGSignal_from_away_zero_disengage_algo)
                if not okpressed:
                    sys.exit(0)

                threshold_EOGSignal_from_away_zero_disengage_algo, okpressed = main.getDouble("EOG Auto-stop Stimulation",
                                                                                              "EOG from 0.0: ", 5.0, 2000.0, 1, threshold_EOGSignal_from_away_zero_disengage_algo)
                if not okpressed:
                    sys.exit(0)

                threshold_EMGSignal_from_away_zero_disengage_algo, okpressed = main.getDouble("EMG Auto-stop Stimulation",
                                                                                              "EMG from 0.0: ", 5.0, 2000.0, 1, threshold_EMGSignal_from_away_zero_disengage_algo)
                if not okpressed:
                    sys.exit(0)


        # updateSendOutDelaySeconds, okpressed = main.getDouble("Update Viewer Interval", "update every (seconds):",
        #                                                       0.05, 30.0, 2, updateSendOutDelaySeconds)

        if not okpressed:
            sys.exit(0)
        if not useDefaultSettings:
            spindle_highlight_options = ("Highlight spindles", "OFF")
            spindle_highlight, okpressed = main.getChoice("Hightlight Spindles?", "Spindle view:", spindle_highlight_options,
                                                       current_item_int=0)
            if not okpressed:
                sys.exit(0)
            if spindle_highlight == "Highlight spindles":
                doSpindleHighlight = True
            elif spindle_highlight == "OFF":
                doSpindleHighlight = False
            else:
                print("spindle highlight option " + spindle_highlight + " not handled yet")
                sys.exit(0)

        if doSpindleHighlight:
            if not useDefaultSettings:
                filterHP_EEG_spindle_freq, okpressed = main.getDouble("Spindle HP filter:",
                                                                        "HP-Filter-freq. -3 dB (Hz):", 8.0, 19.0, 2, filterHP_EEG_spindle_freq)
                if not okpressed:
                    sys.exit(0)

                filterLP_EEG_spindle_freq, okpressed = main.getDouble("Spindle LP filter:",
                                                                      "LP-Filter-freq. -3 dB (Hz):", 9.0, 20.0, 2, filterLP_EEG_spindle_freq)
                if not okpressed:
                    sys.exit(0)

                realTimeFilterOrderSpindles, okpressed = main.getInteger("Spindle IIR Filter",
                                                                         "Filter order:", 1, 10*FS, 1,
                                                                         realTimeFilterOrderSpindles*round(FS/125.0))
                if not okpressed:
                    sys.exit(0)

                spindle_amplitude_threshold_detect_microVolts, okpressed = main.getDouble("Detect Spindle",
                                                                      "Detect thresh. ampl. (uV):", 1.0, spindle_amplitude_max_microVolts, 1, spindle_amplitude_threshold_detect_microVolts)
                if not okpressed:
                    sys.exit(0)

                spindle_amplitude_threshold_begin_end_microVolts, okpressed = main.getDouble("Detect Spindle bounds",
                                                                                          "Bounds thresh. ampl. (uV):", 1.0, spindle_amplitude_max_microVolts-1.0, 1, spindle_amplitude_threshold_begin_end_microVolts)
                if not okpressed:
                    sys.exit(0)
            else:
                realTimeFilterOrderSpindles = realTimeFilterOrderSpindles * round(FS / 125.0)

        if not useDefaultSettings:
            antialias_option = ("Anti-aliasing", "No anti-aliasing")
            alias_option, okpressed = main.getChoice("Anti-aliasing?", "View adaptation:", antialias_option,
                                                       current_item_int=0)
            if not okpressed:
                sys.exit(0)

            if alias_option == "Anti-aliasing":
                doAntiAlias = True
            elif alias_option == "No anti-aliasing":
                doAntiAlias = False
            else:
                print("Anti-aliasing option " + alias_option + " not handled yet")
                sys.exit(0)

            OpenGL_option = ("OpenGL (pyqtgraph)", "OpenGL (vispy)", "Standard")
            # OpenGL_option = ("OpenGL",)
            opengl_option, okpressed = main.getChoice("Use OpenGL?", "View processing:", OpenGL_option,
                                                     current_item_int=2)
            if not okpressed:
                sys.exit(0)

            if opengl_option == "OpenGL (pyqtgraph)":
                useOpenGL = True
                useVispyPlot = False
            elif opengl_option == "OpenGL (vispy)":
                useOpenGL = True
                useVispyPlot = True
            elif opengl_option == "Standard":
                useOpenGL = False
                useVispyPlot = False
            else:
                print("OpenGL option " + opengl_option + " not handled yet")
                sys.exit(0)

        if useOpenGL:
            try:
                pg.setConfigOptions(useOpenGL=useOpenGL)
            except Exception as e:
                print('OpenGL cannot be assured to be loaded problem')
                print(e.message)
                okpressed = main.showMessageBox("OpenGL problem",
                                                "Your System does not support OpenGL yet.\nMaybe install your graphics card driver (if available)\nError message:\n\n" + e.message + "\n\nContinue anyway or abort?",
                                                True, False, True, isOKbuttonDefault=False)
                if not okpressed:
                    sys.exit(0)


        languages = ("en", "zh")
        languages_res, okpressed = main.getChoice("Instructions Language?", "Instructions Language:",
                                                  languages,
                                                  current_item_int=0)
        if not okpressed:
            sys.exit(0)
        language = languages_res

        run_types = ("OpenBCI Device", "Simulation (CSV)")
        run_type_res, okpressed = main.getChoice("Run from Device or Simulate", "Device or CSV-Simulation:", run_types,
                                                 current_item_int=0)
        if not okpressed:
            sys.exit(0)
        if run_type_res == "OpenBCI Device":
            simulateFromCSV = False
        elif run_type_res == "Simulation (CSV)":
            simulateFromCSV = True
        else:
            print("Run type  " + run_type_res + " not handled yet")
            sys.exit(0)

        if not useDefaultSettings:
            if not simulateFromCSV:
                options = ("115200 Hz (Firmware v1 above)", "230400 Hz (only Firmware v2 above)", "921600 Hz (only Firmware v2 above)")
                res, okpressed = main.getChoice("Baudrate FTDI", "Baudrate: ",
                                                                options,
                                                                current_item_int=2)
                if not okpressed:
                    sys.exit(0)

                baudrate_serial = int(res[0:7].trimmed())




    ConnectDeviceText = \
        "<br/>" \
        "<b>Now trying to connect to the DEVICE over DONGLE</b>" \
        "<br/>" \
        "Firmware v1 (before 2016) devices will take longer to connect!<br/>" \
        "<br/> " \
        "If it does not connect within 60 seconds, please:<br/>" \
        "  1. PLUG OUT the DONGLE<br/>" \
        "  2. PLUG IN the DONGLE<br/>" \
        "  wait, if not working after 20 seconds try...<br/>" \
        "  3. Turn the OpenBCI DEVICE OFF <br/>" \
        "  4. Turn the OpenBCI DEVICE ON <br/>" \
        "  5. Wait another 60 seconds, or repeat<br/>" \
        "  (6. Firmware v1, please TURN OFF/RESET OpenBCI DEVICE <br/>" \
        "      AND PLUG OUT and IN dongle.<br/>" \
        "      THEN a red light on dongle should flash shortly.<br/>" \
        "<br/>" \
        "Press OK to try to connect, or abort<br/>"

    if simulateFromCSV:
        ConnectDeviceText = \
            "<br/>" \
            "<b>Now Starting simulation...</b>" \
            "<br/> " \
            "<b>Choose a ***.raw.rec.csv from a previous recording</b>" \
            "<br/> " \
            "<b>(e.g. from the data/rec/ folder)</b>" \
            "<br/> " \
            "<br/> " \
            "Known bug: Markers in the GUI might shift in time while viewing (saved files are still accurate though)." \
            "<br/> " \
            "<br/> " \
            "Press OK to try to open file, or abort<br/>"


    ConnectDeviceText = QtCore.QString.fromUtf8(ConnectDeviceText)
    okpressed = main.showMessageBox("Connect ...", ConnectDeviceText, False, True, True)
    if not okpressed:
        sys.exit(0)

    csvCollectData = OBCIcsv.OpenBCIcsvCollect(FS,FS_ds,nChannels,montage,file_name=subject + "_" + temp_time_stamp + "." + str(nChannels) + "channels" + "." + str(FS) + "HzSampling" + (".downsampled" if FS_ds else "") + ".raw.rec", subfolder="data/rec/", delim=";", verbose=False,simulateFromCSV=simulateFromCSV, doRealTimeStreaming=doRealTimeStreaming,writeEDF=writeEDF,subject=subject,prefilterEDF_hp=prefilterEDF_hp,correctInvertedChannels=correctInvertedChannels,edfAnnotationChannels=edfAnnotationChannels, exportEDFAnnotations=exportEDFAnnotations)

    soundlatency_seconds = soundBufferSize / float(soundFrequency)
    soundlatency_rec_samples = int(math.ceil(soundlatency_seconds * float(FS)))

    doSham_str = str(doSham)
    if shamObfuscationCode:
        doSham_str = "<OBFUSCATED>"

    flog = open("data/log/" + subject + "_" + temp_time_stamp + '.recording_stimulator.log' + '.csv', 'a', buffering=500000)
    flog.write('subject;saveSD;saveSD_sendChar;saveSD_hours;'
               'writeEDF;correctInvertedChannels;prefilterEDF_hp;edfAnnotationChannels;exportEDFAnnotations;'
               'display_montage;extendedDisplayProcessing;'
               'doTesting;simulateFromCSV;nChannels;'
               'condition;doSham;doShamObfuscation;shamObfuscationCode;subject_condition_encoded_file_path;ThresholdDownStateDetectionPassBelow;waitForFurtherDipInThreshold;ThresholdUpStateDetectionPassAbove;ThresholdUpStateDetectionPassBelow;updateThresholdIntervalSec;updateThresholdTimeWindowSec;playBackgroundNoise;'
               'doClosedLoopNotOpenLoop;doClosedLoopRepeatSequence;isStimulationTurnedOn;'
               'doSpindleHighlight;filterHP_EEG_spindle_freq;filterLP_EEG_spindle_freq;realTimeFilterOrder;realTimeFilterOrderSpindles;spindle_amplitude_threshold_detect_microVolts;spindle_amplitude_threshold_begin_end_microVolts;'
               'doAntiAlias;doDownSamplingForPlot;useOpenGL;useVispyPlot;'
               'stimuliListFilePath;stimuliPlayListFilePath;'
               'sound_base_level_dB;soundVolume;masterVolumePercent;'
               'sound_rise_from_base_level_db_initial_value;'
               'soundOnsetDelaySeconds;soundOnsetDelayRecordingSamples;'
               'updateSendOutDelaySeconds;soundBufferSize;'
               'montage_filepath;FS;FS_SD;FS_ds;baudrate_serial;doRealTimeStreaming;instruction_language\n')


    flog.write(subject + ";" + str(saveSD) + ";" + saveSD_sendChar + ";" + SDcard_option_dict[saveSD_sendChar] + ";" + \
               str(writeEDF) + ";" + str(correctInvertedChannels) + ";" + str(prefilterEDF_hp) + ";" + str(edfAnnotationChannels) + ";" + str(exportEDFAnnotations) + ";" +\
               str(montage.filepath) + ";" +  str(extendedDisplayProcessing) + ";" +\
               str(doTesting) + ";" + str(simulateFromCSV) + ";" + str(nChannels) + ";" + \
               str(condition) + ";" + str(doSham_str) + ";" + str(doShamObfuscation) + ";" + str(shamObfuscationCode) + ";" + str(subject_condition_encoded_file_path) + ";" + str(ThresholdDownStateDetectionPassBelow) + ";" + str(waitForFurtherDipInThreshold) + ";" + str(ThresholdUpStateDetectionPassAbove) + ";" + str(ThresholdUpStateDetectionPassBelow) + ";" + str(updateThresholdIntervalSec) + ";" + str(updateThresholdTimeWindowSec) + ";" + str(playBackgroundNoise) + ";" + \
               str(doClosedLoopNotOpenLoop) + ";" + str(doClosedLoopRepeatSequence) + ";" + str(isStimulationTurnedOn) + ";" + \
               str(doSpindleHighlight) + ";" + str(filterHP_EEG_spindle_freq) + ";" + str(filterLP_EEG_spindle_freq) + ";" + str(realTimeFilterOrder) + ";" + str(realTimeFilterOrderSpindles) + ";" + str(spindle_amplitude_threshold_detect_microVolts) + ";" + str(spindle_amplitude_threshold_begin_end_microVolts) + ";" + \
               str(doAntiAlias) + ";" + str(doDownSamplingForPlot) + ";" + str(useOpenGL) + ";" + str(useVispyPlot) + ";" + \
               str(stimuliListFilePath) + ";" + str(stimuliPlayListFilePath) + ";" + \
               str(sound_base_level_dB) + ";" + str(soundVolume) + ";" + str(masterVolumePercent) + ";" + \
               str(sound_rise_from_base_level_db) + ";" + \
               str(soundlatency_seconds) + ";" + str(soundlatency_rec_samples) + ";" + \
               str(updateSendOutDelaySeconds) + ";" + str(soundBufferSize) + ";" + \
               str(montage_filepath) + ";" + str(FS) + ";" + str(FS_SD) + ";" + str(FS_ds) + ";" + str(baudrate_serial) + ";" + str(doRealTimeStreaming) + ";" + str(language) + '\n')

    flog.flush()
    flog.close()

    if not simulateFromCSV:
        nTryToConnect = 0
        OBCI_connected = 0
        OBCI_max_connection_attempts = 100
        while (nTryToConnect < OBCI_max_connection_attempts) and not OBCI_connected:
            try:
                nTryToConnect += 1

                board = bci.OpenBCIBoard(port=None, baud=baudrate_serial, filter_data=False, scaled_output=True, daisy=useDaisyModule,
                                         log=True, timeout=None, sendDeviceStopAfterSerialStop=sendDeviceStopAfterSerialStop)
                board.port = board.find_port()
                print("finnaly connected to " + board.port)
                # logging.basicConfig(filename="log/" + subject + "_" + temp_time_stamp + '.connect.output.log' + '.txt', format='%(message)s', level=logging.DEBUG)
                logging.info('---------WRITE TO BOARD-------------')

                initSendBoardByteString = b''

                if nChannels == 16:
                    board.ser.write(b'C')
                    initSendBoardByteString += b'C'
                elif nChannels == 8:
                    board.ser.write(b'c')
                    initSendBoardByteString += b'c'
                print("channel number (8/16) sent to device")

                if board.openBCIFirmwareVersion != "v1":
                    time.sleep(0.500)
                else:
                    time.sleep(1)

                if not doRealTimeStreaming:
                    board.ser.write(FS_SD_char)
                    initSendBoardByteString += FS_SD_char
                    if board.openBCIFirmwareVersion != "v1":
                        time.sleep(0.500)
                    else:
                        time.sleep(1)
                    print("SD card save sent to device")

                # configure pins
                for chNum in range(1,nChannels+1):
                    send = montage.getOpenBCIChannelSetupSendStringByChannelNumber(chNum)
                    if board.openBCIFirmwareVersion != "v1":
                        board.ser.write(send)
                    else:
                        #legacy for firmware version 1
                        for iChar in range(0,send.__len__()):
                            board.ser.write(send[iChar])
                            time.sleep(0.09)
                    initSendBoardByteString += send
                    print("channel " + str(chNum) + " sent to device, response: ...")
                    if board.openBCIFirmwareVersion != "v1":
                        time.sleep(0.2500)
                    else:
                        time.sleep(1.1)
                        temp_line_read = ""
                        while temp_line_read != "No Message":
                            temp_line_read = board.print_incoming_text()

                print("all channel setup was sent to device")

                # board.ser.write(b'x1060000X')  # EMG on the first pins
                # time.sleep(0.2500)
                # initSendBoardByteString += b'x1060000X'
                # board.ser.write(b'x2060000X')  # EOG on the second pins
                # time.sleep(0.2500)
                # initSendBoardByteString += b'x2060000X'
                # board.ser.write(b'x3060110X')  # A1 on the third N pin
                # time.sleep(0.2500)
                # initSendBoardByteString += b'x3060110X'
                # board.ser.write(b'x4060110X')  # A2 on the fourth N pin
                # time.sleep(0.2500)
                # initSendBoardByteString += b'x4060110X'
                # board.ser.write(b'x5060110X')  # C3 on the fifth N pin
                # time.sleep(0.2500)
                # initSendBoardByteString += b'x5060110X'
                # board.ser.write(b'x6060110X')  # C4 on the sixth N pin
                # time.sleep(0.2500)
                # initSendBoardByteString += b'x6060110X'
                # # # if doTesting:
                # board.ser.write(b'x7060000X')  # Trigger cable
                # initSendBoardByteString += b'x7060000X'
                # # # else:
                # # #   board.ser.write(b'x7060110X')  #
                # time.sleep(0.2500)
                # board.ser.write(b'x8060000X')  # ECG/ audio/marker on the eights pins/
                # initSendBoardByteString += b'x8060000X'
                # time.sleep(0.2500)
                #
                # if nChannels == 16:
                #     board.ser.write(b'xQ060110X') # F3 on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xQ060110X'
                #     board.ser.write(b'xW060110X') # Fz on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xW060110X'
                #     board.ser.write(b'xE060110X') # F4 on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xE060110X'
                #     board.ser.write(b'xR060110X') # P3 on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xR060110X'
                #     board.ser.write(b'xT060110X') # Pz on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xT060110X'
                #     board.ser.write(b'xY060110X') # P4 on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xY060110X'
                #     board.ser.write(b'xU060110X') # O1 on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xU060110X'
                #     board.ser.write(b'xI060110X') # O2 on the third N pin
                #     time.sleep(0.2500)
                #     initSendBoardByteString += b'xI060110X'

                if saveSD:
                    board.ser.write(saveSD_sendChar_byte)  # record on SD card
                    initSendBoardByteString += saveSD_sendChar_byte
                    print("SD card saving instruction sent to device")
                    if board.openBCIFirmwareVersion != "v1":
                        time.sleep(0.500)
                    else:
                        time.sleep(1)


                board.initSendBoardByteString = initSendBoardByteString
                #board.ser.write(initSendBoardByteString)

                OBCI_connected = True
            except Exception as e:
                print e.message, e.args
                print "connection to OpenBCI dongle or device failed %d times, try again in 5 seconds" % (nTryToConnect)
                time.sleep(5.0)
            except:
                print "connection to OpenBCI dongle or device failed %d times, try again in 5 seconds" % (nTryToConnect)
                time.sleep(5.0)
                pass
            finally:
                if nTryToConnect % 4 == 0:
                    okpressed = main.showMessageBox("Connect to Device ...", ConnectDeviceText, False, True, True)
                    if not okpressed:
                        sys.exit(0)
                if nTryToConnect >= OBCI_max_connection_attempts:
                    print
                    "given up to connect OpenBCI dongle or device after %d times" % (nTryToConnect)
                    print("Do the following:")
                    print("   1. PLUG OUT the dongle")
                    print("   2. PLUG IN the dongle")
                    print("   wait, if not working after 20 seconds try...")
                    print("   3. TURN OFF the OpenBCI device")
                    print("   4. TURN ON the OpenBCI device")
                    print("   5. RESTART this PROGRAM")
                    print("")

                    ConnectDeviceText = \
                        "<br/>" \
                        "<b>I have given up, sorry.</b>" \
                        "<br/> " \
                        "  1. PLUG OUT the DONGLE<br/>" \
                        "  2. PLUG IN the DONGLE<br/>" \
                        "  wait, if not working after 20 seconds try...<br/>" \
                        "  3. Turn the OpenBCI DEVICE OFF <br/>" \
                        "  4. Turn the OpenBCI DEVICE ON <br/>" \
                        "  5. CHECK THE DEVICE AND RESTART THIS PROGRAM<br/>" \
                        "IF this happened again, restart the PC also!<br/>" \
                        "<br/>" \
                        "Press OK to end the program<br/>"
                    okpressed = main.showMessageBox("Given up to connect to Device ...", ConnectDeviceText, False, True, True)

                    if not okpressed:
                        sys.exit(0)

                    time.sleep(10.0)
                    sys.exit(app.exec_())

    print("Read serial last response of OpenBCI device:")
    temp_line_read = ""
    while temp_line_read != "No Message" and not(simulateFromCSV):
        temp_line_read = board.print_incoming_text()
        if "initialization failed." in temp_line_read:
            print('micro SD card problem')
            okpressed = main.showMessageBox("micro SD card problem", "The OpenBCI device has problems to write on the micro SD card!\nYou chose to write "+saveSD_rep_str+" on the card.\n\nTry the following:\n  1. restart again device and software\n  2. check if card is nearly full (also clear the trash)\n  3. check that the card is formatted correctly\n  4. Assure the card can hold the amount of data required\n  (5. get another (better) micro SD card)\n  (6. Don't use the micro SD card at all)\n\nStill want to try to continue without using the SD card?",
                                            True, False, True, isOKbuttonDefault=False)
            if not okpressed:
                sys.exit(0)
        if ("daisy removed" in temp_line_read) and nChannels > 8:
            print('NO daisy module detected')
            okpressed = main.showMessageBox("Daisy module missing", "The OpenBCI device cannot find the daisy module, though " +str(nChannels)+ " are requested!\nPlease check the module.\n\nTry the following:\n  1. restart again device and software\n  2. check if the daisy module is firmly connected\n  3. check if it is damaged\n (6. Don't use the daisy module choose 8 channels)\n\n Abort? or is it OK to ignore?",
                                            True, False, True, isOKbuttonDefault=False)
            if not okpressed:
                sys.exit(0)

    print("Read serial last response of OpenBCI device done.")




    if not doRealTimeStreaming:
        try:
            csvCollectData.activate()
            time.sleep(0.1)
            print('start streaming')
            board.ser.write(b'b')
            if board.openBCIFirmwareVersion == "v1":
                time.sleep(0.011)
            csvCollectData.fireStreamingStarted()
            csvCollectData.flush()
            messageText = "<br/>" \
                          "<b>Recording successfully started!</b>" \
                          "<br/>" \
                          "Using " + str(FS_SD) + " Hz sampling rate recording offline only on SD card.<br/>" \
                                                  "Please plug out the dongle and keep the device running.<br/>"

            okpressed = main.showMessageBox("Recording started!", messageText, False, True, False)
        except:
            messageText = "<br/>" \
                          "<b>Failed to start recording!</b>" \
                          "<br/>" \
                          "Please restart the program and try again.<br/>"
            okpressed = main.showMessageBox("Recording Failed!", messageText, False, True, False)
        finally:
            sys.exit(0)
    else:
        if isStimulationTurnedOn:
            ca = clsa.CLSalgo1(fs=FS,
                               useDaisy=useDaisyModule,
                               FS_ds=FS_ds,
                               updateSendOutDelaySeconds=updateSendOutDelaySeconds,
                               montage=montage,
                               realTimeFilterOrder=realTimeFilterOrder,
                               realTimeFilterOrderSpindles=realTimeFilterOrderSpindles,
                               isStimulationTurnedOn=isStimulationTurnedOn,
                               stimulusPlayer=stimulusPlayer,
                               soundBufferSize=soundBufferSize,
                               # stimuliSoundFiles=stimuliSoundFiles,
                               isSham=doSham,
                               isClosedLoop=doClosedLoopNotOpenLoop,
                               isClosedLoopRepeatSequence=doClosedLoopRepeatSequence,
                               ThresholdDownStateDetectionPassBelow=ThresholdDownStateDetectionPassBelow,
                               waitForFurtherDipInThreshold=waitForFurtherDipInThreshold,
                               ThresholdUpStateDetectionPassAbove=ThresholdUpStateDetectionPassAbove,
                               ThresholdUpStateDetectionPassBelow=ThresholdUpStateDetectionPassBelow,
                               firstDownToUpstateDelayInSec=firstDownToUpstateDelayInSec,
                               # secondUpToUpstateDelayInSec=secondUpToUpstateDelayInSec,
                               threshold_EMGSignal_from_away_zero_disengage_algo=threshold_EMGSignal_from_away_zero_disengage_algo,  # in microVOlt
                               threshold_EEGSignal_from_away_zero_disengage_algo=threshold_EEGSignal_from_away_zero_disengage_algo,
                               threshold_EOGSignal_from_away_zero_disengage_algo=threshold_EOGSignal_from_away_zero_disengage_algo,
                               doSpindleHighlight=doSpindleHighlight,
                               filterHP_EEG_spindle_freq=filterHP_EEG_spindle_freq,
                               filterLP_EEG_spindle_freq=filterLP_EEG_spindle_freq,
                               spindle_amplitude_threshold_detect_microVolts=spindle_amplitude_threshold_detect_microVolts,
                               spindle_amplitude_threshold_begin_end_microVolts=spindle_amplitude_threshold_begin_end_microVolts,
                               spindle_amplitude_max_microVolts=spindle_amplitude_max_microVolts,
                               spindle_min_duration_seconds=spindle_min_duration_seconds,
                               spindle_max_duration_seconds=spindle_max_duration_seconds,
                               extendedDisplayProcessing=extendedDisplayProcessing,
                               updateThresholdIntervalSec=updateThresholdIntervalSec,
                               updateThresholdTimeWindowSec=updateThresholdTimeWindowSec)
        else:
            ca = clsa.CLSalgo1(fs=FS,
                               useDaisy=useDaisyModule,
                               FS_ds=FS_ds,
                               updateSendOutDelaySeconds=updateSendOutDelaySeconds,
                               montage=montage,
                               realTimeFilterOrder=realTimeFilterOrder,
                               realTimeFilterOrderSpindles=realTimeFilterOrderSpindles,
                               isStimulationTurnedOn=isStimulationTurnedOn,
                               doSpindleHighlight = doSpindleHighlight,
                               filterHP_EEG_spindle_freq=filterHP_EEG_spindle_freq,
                               filterLP_EEG_spindle_freq=filterLP_EEG_spindle_freq,
                               spindle_amplitude_threshold_detect_microVolts=spindle_amplitude_threshold_detect_microVolts,
                               spindle_amplitude_threshold_begin_end_microVolts=spindle_amplitude_threshold_begin_end_microVolts,
                               spindle_amplitude_max_microVolts=spindle_amplitude_max_microVolts,
                               spindle_min_duration_seconds=spindle_min_duration_seconds,
                               spindle_max_duration_seconds=spindle_max_duration_seconds,
                               extendedDisplayProcessing=extendedDisplayProcessing)

        ca.doTracking()
        # ca.doStimulation()
        ca.doTesting(isTestingStatus=doTesting)

        if simulateFromCSV:
            exampleCSVFile = main.getFile("OpenBCI CSV file by SpiSOP", initFolder='data/rec', filterList='CSV and TXT (*.csv *.txt)')
            skipSeconds, okpressed = main.getDouble("CSV, Seconds to Skip", "skip (s)", 0.0, 3600 * 200.0, 3, 0.0)
            if not okpressed:
                skipSeconds = 0.0

            tempFS = FS
            if FS_ds:
                tempFS = tempFS*2.0
            boardCSVSimulator = OBCIsim.OBCI_board_simulator(filepath=exampleCSVFile, FS=tempFS, factorOriginalSpeed=1, skipSeconds=skipSeconds, daisy=useDaisyModule)
            ca.doSimulationFromCSVFile(boardCSVSimulator)

        else:
            ca.setOBCIboard(board)

        ca.setCSVcollect(csvCollectData)
        time.sleep(0.5)
        # csv.activate()

        temp_soundlatency_seconds = 0
        if isStimulationTurnedOn:
            temp_soundlatency_seconds = stimulusPlayer.soundlatency_seconds

        app.connect(ca, QtCore.SIGNAL("updateSignalViewerSendMain"), main.CAtoMain, QtCore.Qt.QueuedConnection)
        print("connected ca algo send to main")

        ## Define a top-level widget to hold everything
        dsvw = DisplaySignalViewWidget([0], [0], [0], [0], ca, montage, None, isStimulationTurnedOn, sound_base_level_dB, sound_rise_from_base_level_db, temp_soundlatency_seconds, (realTimeFilterOrder*0.5)/FS, updateSendOutDelaySeconds, language,
                                       threshold_EEGSignal_from_away_zero_disengage_algo, threshold_EOGSignal_from_away_zero_disengage_algo,
                                       threshold_EMGSignal_from_away_zero_disengage_algo,doSpindleHighlight=doSpindleHighlight,doAntiAlias = doAntiAlias,useOpenGL=useOpenGL,doDownSamplingForPlot = doDownSamplingForPlot)
        app.connect(main, QtCore.SIGNAL("updateSignalViewerSendViewer"), dsvw.updateReceive, QtCore.Qt.QueuedConnection)
        print("connected signal viewer receive from main")

        if extendedDisplayProcessing:
            dsfvw = DisplaySignalFullViewWidget([0], [0], ca, montage, None, updateSendOutDelaySeconds, doAntiAlias=doAntiAlias, useOpenGL=useOpenGL, doDownSamplingForPlot=doDownSamplingForPlot, useVispyPlot=useVispyPlot)
            app.connect(main, QtCore.SIGNAL("updateSignalViewerSendViewer"), dsfvw.updateReceive, QtCore.Qt.QueuedConnection)
            print("connected signal full viewer receive from main")



        app.connect(dsvw, QtCore.SIGNAL("sendMainUpdateIntervalChange"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)



        app.connect(dsvw, QtCore.SIGNAL("sendMainStartStim"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)
        app.connect(dsvw, QtCore.SIGNAL("sendMainPauseStim"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)
        app.connect(dsvw, QtCore.SIGNAL("sendMainTestStim"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)


        app.connect(dsvw, QtCore.SIGNAL("sendMainAutoStim"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)
        app.connect(dsvw, QtCore.SIGNAL("sendMainForcedStim"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)

        app.connect(dsvw, QtCore.SIGNAL("sendMainSoundLevelChange"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)

        app.connect(dsvw, QtCore.SIGNAL("sendMainEEGchannelChange"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)

        app.connect(dsvw, QtCore.SIGNAL("sendMainCheckEEG"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)
        app.connect(dsvw, QtCore.SIGNAL("sendMainLightsOff"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)
        app.connect(dsvw, QtCore.SIGNAL("sendMainLightsOn"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)
        app.connect(dsvw, QtCore.SIGNAL("sendMainReconnect"), main.DSVWtoMain, QtCore.Qt.QueuedConnection)


        print("connected dsvw send to main")

        app.connect(main, QtCore.SIGNAL("sendCAUpdateIntervalChange"), ca.changeUpdateViewInterval, QtCore.Qt.QueuedConnection)

        app.connect(main, QtCore.SIGNAL("sendCAStartStim"), ca.doStimulation, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCAPauseStim"), ca.pauseStimulation, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCATestStim"), ca.fireTestStimulus, QtCore.Qt.QueuedConnection)

        app.connect(main, QtCore.SIGNAL("sendCAAutoStim"), ca.setAutoStimEngaged, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCAForcedStim"), ca.setForcedStimEngaged, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCASoundRiseLevel"), ca.changeSoundRiseFromBaseLeveldB, QtCore.Qt.QueuedConnection)

        app.connect(main, QtCore.SIGNAL("sendCACheckEEG"), ca.handleCheckEEG, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCALightsOff"), ca.handleLightsOff, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCALightsOn"), ca.handleLightsOn, QtCore.Qt.QueuedConnection)
        app.connect(main, QtCore.SIGNAL("sendCAReconnect"), ca.handleReconnect, QtCore.Qt.QueuedConnection)

        app.connect(main, QtCore.SIGNAL("sendCAEEGchannel"), ca.changeEEGchannel, QtCore.Qt.QueuedConnection)


        print("connected ca algo recieve from main")

        if extendedDisplayProcessing:
            dsfvw.start()
            print("started extended signal viewer")

        dsvw.start()
        print("started signal viewer")



        ca.start()
        print("started ca algo")

    ## Start the Qt event loop
    sys.exit(app.exec_())
