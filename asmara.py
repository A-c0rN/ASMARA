"""
Note: Please do absolute imports, it allows me to clean up shit we don't use, and doesn't import extra code. It should be more efficient anyways.
"""
# Standard Library
from datetime import datetime as DT
from datetime import timezone as TZ
from datetime import timedelta as timedelta
from json import dump, load
from multiprocessing import Process, active_children
from os import getcwd, path, remove, walk
from random import choice, shuffle
from subprocess import PIPE, Popen
from sys import exit
from threading import Thread, Barrier, enumerate, current_thread
from time import mktime, sleep
from warnings import filterwarnings
from argparse import ArgumentParser

# Third-Party
from EAS2Text.EAS2Text import EAS2Text
from EASGen.EASGen import EASGen
from numpy import (
    append,
    blackman,
    empty,
    fft,
    frombuffer,
    int16,
    log,
    log10,
)
from pydub import AudioSegment
from pydub.effects import normalize
from pydub.generators import Sine
from pydub.utils import make_chunks, mediainfo
from requests import get, exceptions
from calendar import isleap

# First-Party
from utilities import utilities, severity

filterwarnings("ignore")

currentAlert = []
liveAlert = {}


class AS_MON(Process):
    global currentAlert
    global liveAlert
    __monitors__ = {}
    __receivedAlerts__ = {}
    __receivedAlertsIndex__ = []
    __pendingAlerts__ = {}
    __run__ = True
    __liveAlertLock__ = False
    __useATTNDT__ = True

    def __init__(self, URL: str = "") -> None:
        self.__monitorName__ = None
        self.__monitor__ = {
            "Type": "Stream",
            "URL": URL,
            "State": True,
            "Online": True,
            "Alert": False,
            "AttentionTone": False,
            "Live": False,
        }
        if isinstance(URL, dict):
            if "AUD" in URL:
                self.__monitor__["Type"] = "Audio"
                self.__monitor__["URL"] = URL["AUD"]
            elif "SDR" in URL:
                self.__monitor__["Type"] = "Radio"
                self.__monitor__["URL"] = URL["SDR"]
        num = 1
        while self.__monitorName__ == None:
            if str(num) in self.__monitors__:
                num = num + 1
            else:
                self.__monitorName__ = str(num)
                self.__updateMon__(self.__monitorName__, self.__monitor__)
        self.__decode__ = None
        self.__stream__ = None
        self.__alertData__ = {}
        self.__decThread__ = Thread(
            target=self.__decoder__,
            name=f"DECODER-{self.__monitorName__}",
            daemon=True,
        )
        self.__monThread__ = Thread(
            target=self.__recorder__,
            name=f"MONITOR-{self.__monitorName__}",
            daemon=True,
        )
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Created.",
            classType="MAIN",
            sev=severity.debug,
        )
        self.__decodeLock__ = Barrier(2)
        self.__monThread__.start()
        self.__decThread__.start()

    def killMon(self):
        self.__monitor__["State"] = False
        while self.__decode__.poll() == None:
            self.__decode__.terminate()
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Decoder Terminated.",
            classType="DECODER",
            sev=severity.trace,
        )
        while self.__stream__.poll() == None:
            self.__stream__.terminate()
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Recorder Terminated.",
            classType="MONITOR",
            sev=severity.trace,
        )
        try:
            del self.__monitors__[self.__monitorName__]
        except ValueError:
            pass
        return

    @classmethod
    def __updateMon__(cls, monName, mon):
        cls.__monitors__[monName] = mon

    @classmethod
    def __liveLock__(cls):
        cls.__liveAlertLock__ = True

    @classmethod
    def __LiveUnlock__(cls):
        cls.__liveAlertLock__ = False

    @classmethod
    def __liveStatus__(cls):
        return cls.__liveAlertLock__

    def __MonState__(self, update: bool = False):
        if update:
            self.__updateMon__(self.__monitorName__, self.__monitor__)
        else:
            return (
                "Online"
                if self.__monitor__["Online"]
                else "Offline"
                if self.__monitor__["State"]
                else "Disabled"
            )

    def __ATTNDetection__(self, pkt, bufferSize, sampleRate, window):
        dBDect = 10
        fin = []
        bandPasses = [
            (
                float((800 / (sampleRate / bufferSize)) + 1),
                float((900 / (sampleRate / bufferSize)) - 1),
                [851, 852, 853, 854, 855],
            ),
            (
                float((900 / (sampleRate / bufferSize)) + 1),
                float((1000 / (sampleRate / bufferSize)) - 1),
                [958, 959, 960, 961, 962],
            ),
            (
                float((1000 / (sampleRate / bufferSize)) + 1),
                float((2000 / (sampleRate / bufferSize)) - 1),
                [1048, 1049, 1050, 1051, 1052],
            ),
        ]
        try:
            for bandPass in bandPasses:
                if len(pkt) == bufferSize:
                    indata = pkt * window
                    bp = fft.rfft(indata)
                    minFilterBin = bandPass[0]
                    maxFilterBin = bandPass[1]
                    for i in range(len(bp)):
                        if i < minFilterBin:
                            bp[i] = 0
                        if i > maxFilterBin:
                            bp[i] = 0
                    fftData = abs(bp) ** 2
                    which = fftData[1:].argmax() + 1
                    dB = 10 * log10(1e-20 + abs(bp[which]))
                    if round(dB) >= dBDect:
                        if which != len(fftData) - 1:
                            y0, y1, y2 = log(fftData[which - 1 : which + 2 :])
                            x1 = (y2 - y0) * 0.5 / (2 * y1 - y2 - y0)
                            thefreq = (which + x1) * sampleRate / bufferSize
                        else:
                            thefreq = which * sampleRate / bufferSize
                        if round(thefreq) in bandPass[2]:
                            fin.append(True)
                        else:
                            fin.append(False)
                    else:
                        fin.append(False)
                else:
                    fin.append(False)
            if (fin[0] and fin[1]) or fin[2] or (fin[0] and fin[1] and fin[2]):
                return True
            else:
                return False
        except:
            return False

    @classmethod
    def __alertToOld__(cls, ZCZC, alert):
        if ZCZC in cls.__receivedAlertsIndex__:
            cls.__receivedAlerts__[ZCZC] = alert
        else:
            cls.__receivedAlerts__[ZCZC] = alert
            cls.__receivedAlertsIndex__.append(ZCZC)

    @classmethod
    def __alertFromOld__(cls, index: int = 0) -> dict:
        try:
            alert = cls.__receivedAlertsIndex__.pop(index)
            prevAlert = cls.__receivedAlerts__.pop(alert)
        except Exception as E:
            utilities.autoPrint(
                text=f"{type(E).__name__}, {E}",
                classType="MAIN",
                sev=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                utilities.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="MAIN",
                    sev=severity.error,
                )
                tb = tb.tb_next
        return {alert: prevAlert}

    def __decoder__(self):
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Opening Decoder Thread.",
            classType="DECODER",
            sev=severity.trace,
        )
        try:
            samedec_version = Popen(["samedec", "-V"], stdout=PIPE).communicate()[0].decode("UTF-8").strip()
            if not samedec_version.startswith("samedec 0.1."):
                self.__decode__ = Popen(
                    ["samedec", "-r", "24000"],
                    stdout=PIPE,
                    stdin=PIPE,
                    stderr=PIPE,
                    bufsize=1,
                )
            else:
                utilities.autoPrint(
                    text=f"SAMEDEC is not version 0.2 or higher! Recommended version is 0.2.3.",
                    classType="DECODER",
                    sev=severity.fatal,
                )
                AS_MAN.killAsmara()
                exit(1)
        except FileNotFoundError:
            utilities.autoPrint(
                text=f"Samedec is not installed on the computer. Please install SAMEDEC 0.2.3 or higher.",
                classType="DECODER",
                sev=severity.fatal,
            )
            AS_MAN.killAsmara()
            exit(1)
        utilities.autoPrint(
            text=f"{self.__monitorName__}: Ready.",
            classType="DECODER",
            sev=severity.trace,
        )
        self.__decodeLock__.wait()
        utilities.autoPrint(
            text=f"{self.__monitorName__}: Running.",
            classType="DECODER",
            sev=severity.trace,
        )
        while self.__run__:
            if not self.__monitor__["State"]:
                sleep(1)
            else:
                try:
                    decode = (
                        self.__decode__.stdout.readline()
                        .decode("utf-8")
                        .strip("\n")
                    )
                    if "ZCZC" in decode:
                        noCall = "-".join(decode.split("-")[:-2]) + "-"
                        headerTranslation = EAS2Text(decode)
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: Receiving Alert:\n{headerTranslation.EASText}\n{decode}",
                            classType="DECODER",
                            sev=severity.alert,
                        )
                        if headerTranslation.evnt == "EAN":
                            utilities.autoPrint(
                                text=f"EAN RECIEVED ON MONITOR {self.__monitorName__}.",
                                classType="DECODER",
                                sev=severity.warning,
                            )
                        elif headerTranslation.evnt == "EAT":
                            utilities.autoPrint(
                                text=f"EAT RECIEVED ON MONITOR {self.__monitorName__}.",
                                classType="DECODER",
                                sev=severity.warning,
                            )
                        try:
                            if noCall in self.__receivedAlerts__:
                                utilities.autoPrint(
                                    text=f"Monitor {self.__monitorName__}: Alert already processed.",
                                    classType="DECODER",
                                    sev=severity.alert,
                                )
                                self.__monitor__["Alert"] = False
                            else:
                                x = DT.strptime(
                                    decode.split("-")[-3], "%j%H%M"
                                )
                                expiryOffset = 0
                                timeStamp = decode.split("-")[-4].split("+")[1]
                                currDate = DT.now(TZ.utc)
                                currYear = currDate.today().year
                                leapDate = f"2/29/{currYear}"
                                if isleap(currYear):
                                    if DT.now(TZ.utc).strftime('%Y-%m-%d') > DT.strptime(leapDate,"%m/%d/%Y").strftime('%Y-%m-%d'):
                                        expiryOffset = 86400
                                    elif DT.now(TZ.utc).strftime('%Y-%m-%d') == DT.strptime(leapDate,"%m/%d/%Y").strftime('%Y-%m-%d'):
                                        midnight = (DT.now(TZ.utc) + timedelta(days=1)).replace(hour=0, minute=0, microsecond=0, second=0)
                                        expiryOffset = 86400 - (DT.now(TZ.utc) - midnight).seconds
                                        print(expiryOffset)
                                    else: 
                                        expiryOffset = 0
                                startTime = mktime(
                                    DT(
                                        DT.utcnow().year,
                                        x.month,
                                        x.day,
                                        x.hour,
                                        x.minute,
                                    ).timetuple()
                                )
                                endTime = startTime + (
                                    (int(timeStamp[:2]) * 60) * 60
                                    + int(timeStamp[2:]) * 60
                                )
                                now = mktime(DT.utcnow().timetuple()) + expiryOffset
                                filt = self.__FilterManager__(
                                    headerTranslation.org,
                                    headerTranslation.evnt,
                                    headerTranslation.FIPS,
                                    headerTranslation.callsign,
                                )
                                utilities.autoPrint(
                                    text=f"now: {now}\nstartTime: {startTime}\n  endTime: {endTime}\nnow - S.T: {now - startTime}\nnow - E.T: {now - endTime}",
                                    classType="DECODER",
                                    sev=severity.trace,
                                )
                                if now >= endTime:
                                    utilities.autoPrint(
                                        text=f"Monitor {self.__monitorName__}: Alert is Expired.",
                                        classType="DECODER",
                                        sev=severity.alert,
                                    )
                                    self.__monitor__["Alert"] = False
                                elif (now - startTime) < 0 and int(
                                    now - startTime
                                ) < -300:
                                    utilities.autoPrint(
                                        text=f"Monitor {self.__monitorName__}: Alert is *Very* Expired.",
                                        classType="DECODER",
                                        sev=severity.alert,
                                    )
                                    self.__monitor__["Alert"] = False
                                else:
                                    if filt["Matched"]:
                                        utilities.autoPrint(
                                            text=f"Monitor {self.__monitorName__}: Alert is New and Valid.",
                                            classType="DECODER",
                                            sev=severity.alert,
                                        )
                                        if (now - startTime) < 0 and int(
                                            now - startTime
                                        ) < -300:
                                            wait_time = int(
                                                round(
                                                    (
                                                        int(
                                                            0
                                                            - (now - startTime)
                                                        )
                                                        / 60
                                                    ),
                                                    0,
                                                )
                                            )
                                            utilities.autoPrint(
                                                text=f"Monitor {self.__monitorName__}: Alert is approx {wait_time} minutes early, waiting for effect...",
                                                classType="DECODER",
                                                sev=severity.debug,
                                            )
                                            filt[
                                                "Actions"
                                            ] = f"Relay:{wait_time}"
                                        self.__alertData__ = {
                                            "Monitor": f"Monitor {self.__monitorName__}",
                                            "Time": now,
                                            "Event": " ".join(
                                                headerTranslation.evntText.split(
                                                    " "
                                                )[
                                                    1:
                                                ]
                                            ),
                                            "Protocol": noCall,
                                            "From": headerTranslation.callsign,
                                            "Filter": filt,
                                            "Length": 0,
                                        }
                                        if (
                                            "Live" in filt["Actions"]
                                            and not self.__liveStatus__()
                                        ):
                                            utilities.autoPrint(
                                                text=f"Monitor {self.__monitorName__}: Alert will relay Live.",
                                                classType="DECODER",
                                                sev=severity.alert,
                                            )
                                            self.__monitor__["Alert"] = True
                                            self.__monitor__["Live"] = True
                                            self.__liveLock__()
                                            self.__alertToOld__(
                                                noCall, self.__alertData__
                                            )
                                            if AS_MAN.__logger__:
                                                self.__log__ = utilities.log(
                                                    AS_MAN.__callsign__,
                                                    AS_MAN.__webhooks__,
                                                    "Patching Alert Live",
                                                    decode,
                                                    filt["Name"],
                                                    self.__monitorName__,
                                                    False,
                                                    "",
                                                    self.__monitor__["URL"],
                                                    AS_MAN.version,
                                                    email=AS_MAN.__email__,
                                                )
                                        elif (
                                            "Live" in filt["Actions"]
                                            and self.__liveStatus__()
                                        ):
                                            utilities.autoPrint(
                                                text=f"Monitor {self.__monitorName__}: Live alert active, recording new alert in background.",
                                                classType="DECODER",
                                                sev=severity.alert,
                                            )
                                            self.__alertToOld__(
                                                noCall, self.__alertData__
                                            )
                                            if AS_MAN.__logger__:
                                                self.__log__ = utilities.log(
                                                    AS_MAN.__callsign__,
                                                    AS_MAN.__webhooks__,
                                                    "Recieving alert",
                                                    decode,
                                                    filt["Name"],
                                                    self.__monitorName__,
                                                    False,
                                                    "",
                                                    self.__monitor__["URL"],
                                                    AS_MAN.version,
                                                    email=AS_MAN.__email__,
                                                )
                                            self.__monitor__["Alert"] = True
                                        elif "Relay" in filt["Actions"]:
                                            utilities.autoPrint(
                                                text=f"Monitor {self.__monitorName__}: Alert will be relayed ASAP.",
                                                classType="DECODER",
                                                sev=severity.alert,
                                            )
                                            self.__alertToOld__(
                                                noCall, self.__alertData__
                                            )
                                            if AS_MAN.__logger__:
                                                self.__log__ = utilities.log(
                                                    AS_MAN.__callsign__,
                                                    AS_MAN.__webhooks__,
                                                    "Recieving alert",
                                                    decode,
                                                    filt["Name"],
                                                    self.__monitorName__,
                                                    False,
                                                    "",
                                                    self.__monitor__["URL"],
                                                    AS_MAN.version,
                                                    email=AS_MAN.__email__,
                                                )
                                            self.__monitor__["Alert"] = True
                                        else:
                                            if not "Now" in filt["Actions"]:
                                                self.__alertToOld__(
                                                    noCall, self.__alertData__
                                                )
                                                if AS_MAN.__logger__:
                                                    self.__log__ = utilities.log(
                                                        AS_MAN.__callsign__,
                                                        AS_MAN.__webhooks__,
                                                        "Recieving alert",
                                                        decode,
                                                        filt["Name"],
                                                        self.__monitorName__,
                                                        False,
                                                        "",
                                                        self.__monitor__[
                                                            "URL"
                                                        ],
                                                        AS_MAN.version,
                                                        email=AS_MAN.__email__,
                                                    )
                                                self.__monitor__[
                                                    "Alert"
                                                ] = True
                                            else:
                                                self.__monitor__[
                                                    "Alert"
                                                ] = False
                                                utilities.autoPrint(
                                                    text=f"Monitor {self.__monitorName__}: Alert Filter is Ignore.",
                                                    classType="DECODER",
                                                    sev=severity.alert,
                                                )
                                                self.__alertToOld__(
                                                    noCall, self.__alertData__
                                                )
                                                if AS_MAN.__logger__:
                                                    utilities.log(
                                                        AS_MAN.__callsign__,
                                                        AS_MAN.__webhooks__,
                                                        "Alert Ignored",
                                                        decode,
                                                        filt["Name"],
                                                        self.__monitorName__,
                                                        False,
                                                        "",
                                                        self.__monitor__[
                                                            "URL"
                                                        ],
                                                        AS_MAN.version,
                                                        email=AS_MAN.__email__,
                                                    )
                                    else:
                                        utilities.autoPrint(
                                            text=f"Monitor {self.__monitorName__}: Alert is Not in Filter.",
                                            classType="DECODER",
                                            sev=severity.alert,
                                        )
                                        self.__monitor__["Alert"] = False
                        except ValueError:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: EAS Data is INVALID: {decode}",
                                classType="DECODER",
                                sev=severity.debug,
                            )
                            self.__monitor__["Alert"] = False
                    elif "NNNN" and self.__monitor__["Alert"]:
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: EOMs Recieved.",
                            classType="DECODER",
                            sev=severity.info,
                        )
                        self.__monitor__["Alert"] = False
                except Exception as E:
                    sleep(0.1)
                    if self.__run__:
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: {type(E).__name__}, {E}",
                            classType="DECODER",
                            sev=severity.error,
                        )
                        tb = E.__traceback__
                        while tb is not None:
                            utilities.autoPrint(
                                text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                                classType="DECODER",
                                sev=severity.error,
                            )
                            tb = tb.tb_next
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Closing Decoder Thread.",
            classType="DECODER",
            sev=severity.trace,
        )
        self.__decode__.kill()
        self.__decode__.poll()
        return

    def __FilterManager__(self, ORG: str, EVNT: str, FIPS: str, CALL: str):
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Checking Filters...",
            classType="FILTER",
            sev=severity.debug,
        )
        nat = {
            "Name": "National Alert",
            "Originators": ["PEP"],
            "EventCodes": ["EAN", "EAT"],
            "SameCodes": ["*"],
            "CallSigns": ["*"],
            "Action": "Live:Now",
        }
        try:
            filters = AS_MAN.__filters__
            if filters[0] != nat:
                filters.insert(
                    0,
                    nat,
                )
            for filter in filters:
                OOO, EEE, SSS, CCC = False, False, False, False
                name, originators, eventCodes, sameCodes, callsigns, action = (
                    filter["Name"],
                    filter["Originators"],
                    filter["EventCodes"],
                    filter["SameCodes"],
                    filter["CallSigns"],
                    filter["Action"],
                )
                if ("*" in originators) or (ORG in originators):
                    OOO = True
                if ("*" in eventCodes) or (EVNT in eventCodes):
                    EEE = True
                if ("*" in callsigns) or (CALL.strip() in callsigns):
                    CCC = True
                if "LOCAL" in sameCodes or "LOC" in sameCodes:
                    sameCodes[:] = (
                        same
                        for same in sameCodes
                        if same.upper() != "LOCAL" or same.upper() != "LOC"
                    )
                    sameCodes += AS_MAN.__localFIPS__
                for sameCode in sameCodes:
                    if sameCode == "*":
                        SSS = True
                        break
                    elif (
                        len(sameCode) == 6
                        and sameCode.startswith("*")
                        and sameCode.endswith("***")
                    ):
                        for FIP in FIPS:
                            if FIP[1:3] == sameCode[1:3]:
                                SSS = True
                                break
                    elif len(sameCode) == 6 and sameCode.startswith("*"):
                        for FIP in FIPS:
                            if FIP[-5:] == sameCode[-5:]:
                                SSS = True
                                break
                    elif len(sameCode) == 6 and sameCode.endswith("***"):
                        for FIP in FIPS:
                            if FIP[:3] == sameCode[:3]:
                                SSS = True
                                break
                    elif len(sameCode) == 6:
                        for FIP in FIPS:
                            if FIP == sameCode:
                                SSS = True
                                break
                if OOO and EEE and SSS and CCC:
                    utilities.autoPrint(
                        text=f"Monitor {self.__monitorName__}: Matched Filter {name}: {action}",
                        classType="FILTER",
                        sev=severity.debug,
                    )
                    return {"Matched": True, "Name": name, "Actions": action}
            utilities.autoPrint(
                text=f"Monitor {self.__monitorName__}: No Matching Filters.",
                classType="FILTER",
                sev=severity.debug,
            )
            return {"Matched": False}
        except Exception as E:
            sleep(0.1)
            if self.__run__:
                utilities.autoPrint(
                    text=f"Monitor {self.__monitorName__}: {type(E).__name__}, {E}",
                    classType="FILTER",
                    sev=severity.error,
                )
                tb = E.__traceback__
                while tb is not None:
                    utilities.autoPrint(
                        text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                        classType="FILTER",
                        sev=severity.error,
                    )
                    tb = tb.tb_next

    def __recorder__(self):
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Opening Monitor Thread.",
            classType="MONITOR",
            sev=severity.trace,
        )
        if self.__monitor__["Type"] == "Audio":
            ## URI STYLE:
            ## <TYPE>|<DEV>|<SAMP>|<CHAN>
            ## alsa|hw:0|44.1k|2 (Alsa Device hw:0, 44.1k Samplerate, 2 Channels)
            ## pulse|alsa_input.pci-0000_00_1f.3.3.analog-stereo|24k|1 (Pulse Device alsa_input.pci-0000_00_1f.3.3.analog-stereo, 24k Samplerate, 1 Channels)
            ## jack|mon1|32k|2 (Jack Device mon1, 2 Channels (SR Controlled by Jack))
            ## Config style: {"AUD": "<URI>"}
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "quiet",
                "-nostats",
                "-sample_rate",
                self.__monitor__["URL"].split("|")[2],
                "-channels",
                self.__monitor__["URL"].split("|")[3],
                "-f",
                self.__monitor__["URL"].split("|")[0],
                "-i",
                self.__monitor__["URL"].split("|")[1],
                "-f",
                "s16le",
                "-c:a",
                "pcm_s16le",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-af",
                "alimiter=level=true:attack=1,volume=-6dB",
                "-",
            ]
        elif self.__monitor__["Type"] == "Radio":
            ## URI STYLE:
            ## <DEV>|<FREQ>|<TYPE>
            ## 0|162.4M|fm (NWR on SDR 0)
            ## 1|93.3M|wfm (93.3 FM on SDR 1)
            ## 2|710k|am (710 AM on SDR 2)
            ## Config style: {"SDR": "<URI>"}
            cmd = [
                "rtl_fm",
                "-d",
                self.__monitor__["URL"].split("|")[0],
                "-f",
                self.__monitor__["URL"].split("|")[1],
                "-M",
                self.__monitor__["URL"].split("|")[2],
                "-A",
                "fast",
                "-r",
                "24k",
            ]
            if self.__monitor__["URL"].split("|")[2] == "wfm":
                cmd.insert(len(cmd) - 4, "-s")
                cmd.insert(len(cmd) - 4, "170k")
                cmd.insert(len(cmd) - 2, "-E")
                cmd.insert(len(cmd) - 2, "deemp")
        else:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "quiet",
                "-nostats",
                "-reconnect",
                "1",
                "-reconnect_at_eof",
                "1",
                "-reconnect_streamed",
                "1",
                "-reconnect_on_network_error",
                "1",
                "-reconnect_delay_max",
                "5",
                "-i",
                self.__monitor__["URL"],
                "-f",
                "s16le",
                "-c:a",
                "pcm_s16le",
                "-map",
                "0",
                "-map",
                "-0:v",
                "-map",
                "-0:s",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-af",
                "alimiter=level=true:attack=1,volume=-6dB",
                "-",
            ]
        self.__stream__ = Popen(
            cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=1
        )
        alertAudio = empty(0, dtype=int16)
        testStatus = False
        ## TODO: Make this a config option
        setLevel = 5  # Number of decodes before we count it.
        ## TODO: Make this a config option
        hold = 3  # Number of samples to hold for
        threshLevelATTN = setLevel
        threshLenATTN = hold
        detectedATTN = False
        activeATTN = False
        window = blackman(4800)
        audioBork = 0
        removedATTN = False
        buffTemp = 0
        alertGenerated = False
        liveBuff = AudioSegment.empty()
        alertSegment = {
            "headers": AudioSegment.empty(),
            "attnTone": AudioSegment.empty(),
            "message": AudioSegment.empty(),
            "eoms": AudioSegment.empty(),
        }
        utilities.autoPrint(
            text=f"{self.__monitorName__}: Ready.",
            classType="MONITOR",
            sev=severity.trace,
        )
        self.__decodeLock__.wait()
        utilities.autoPrint(
            text=f"{self.__monitorName__}: Running.",
            classType="MONITOR",
            sev=severity.trace,
        )
        while self.__run__:
            try:
                if not self.__monitor__["State"]:
                    sleep(1)
                elif not self.__monitor__["Online"]:
                    self.__stream__ = Popen(
                        cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, bufsize=1
                    )
                    ## TODO: Replace Subprocess with ASYNC, allow for kill if too long.
                    ## See: https://stackoverflow.com/questions/10756383/timeout-on-subprocess-readline-in-python
                    data = self.__stream__.stdout.read(
                        24000
                    )  # Try to read 1 second of audio from the stream
                    audioSamples = frombuffer(data, dtype=int16)
                    if len(audioSamples) > 0:
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: has been restored (Down for {(audioBork-24000)*10} seconds).",
                            classType="MONITOR",
                            sev=severity.info,
                        )
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: {self.__monitor__['URL']} Restored.",
                            classType="MONITOR",
                            sev=severity.trace,
                        )
                        audioBork = 0
                        self.__monitor__["Online"] = True
                    else:
                        self.__stream__.kill()
                        self.__stream__.poll()
                        audioBork += 1
                        for i in range(10):
                            if self.__run__:
                                sleep(1)
                            else:
                                break
                else:
                    data = self.__stream__.stdout.read(2400 * 4)
                    audioSamples = frombuffer(data, dtype=int16)
                    self.__decode__.stdin.write(audioSamples)
                    if (
                        self.__monitor__["Live"] == True
                        and self.__monitor__["Alert"] == True
                    ):
                        if not alertGenerated:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Generating Live Alert Headers.",
                                classType="MONITOR",
                                sev=severity.debug,
                            )
                            header = f"{self.__alertData__['Protocol']}{AS_MAN.__callsign__}-"
                            headerTranslation = EAS2Text(header)
                            alertName = f"EAS_LIVE_{headerTranslation.org}-{headerTranslation.evnt}-{headerTranslation.timeStamp}-{headerTranslation.callsign.replace('/', '-').strip().replace(' ', '-')}"
                            alert = EASGen.genHeader(
                                header_data=header,
                                mode=AS_MAN.__config__["Emulation"],
                            )
                            tone = EASGen.genATTN(
                                mode=AS_MAN.__config__["Emulation"]
                            )
                            buffTemp = (
                                round((len(alert) + len(tone)) / 1000, 0)
                                * 3.125
                            )
                            self.__alertData__["Length"] = 0.00
                            event = self.__alertData__["Event"]
                            call = self.__alertData__["From"]
                            data = {
                                "Audio": alertName,
                                "Type": "Live",
                                "Event": event,
                                "Callsign": call,
                                "Protocol": header,
                            }
                            self.__alertToOld__(
                                self.__alertData__["Protocol"],
                                self.__alertData__,
                            )
                            liveAlert[alertName] = ["HEADER_HEADER_HEADER"]
                            liveAlert[alertName].append(alert)
                            liveAlert[alertName].append("TONE_TONE_TONE")
                            liveAlert[alertName].append(tone)
                            liveBuff += alert + tone
                            currentAlert.append(data)
                            alertGenerated = True
                            oof = True
                        if oof:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Alert Audio LIVE in {buffTemp/3.125} Seconds.",
                                classType="MONITOR",
                                sev=severity.debug,
                            )
                            liveAlert[alertName].append("AUDIO_AUDIO_AUDIO")
                            oof = False
                        liveAudio = AudioSegment(
                            audioSamples.tobytes(),
                            frame_rate=24000,
                            sample_width=2,
                            channels=1,
                        )
                        if buffTemp > 0:
                            buffTemp -= 1
                        else:
                            liveBuff += liveAudio
                            liveAlert[alertName].append(liveAudio)
                    elif self.__monitor__["Live"] == True:
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: Generating Live Alert EOMs.",
                            classType="MONITOR",
                            sev=severity.debug,
                        )
                        EOM = EASGen.genEOM(
                            mode=AS_MAN.__config__["Emulation"],
                        ) + AudioSegment.silent(500)
                        liveAlert[alertName].append("EOM_EOM_EOM")
                        liveAlert[alertName].append(EOM)
                        liveBuff += EOM
                        self.__monitor__["Live"] = False
                        alertGenerated = False
                        self.__LiveUnlock__()
                        alertName = (
                            f"{AS_MAN.__exportFolder__}/{alertName}.wav"
                        )
                        if AS_MAN.__logger__ and AS_MAN.__export__:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Logging Alert.",
                                classType="MONITOR",
                                sev=severity.trace,
                            )
                            liveBuff.export(
                                out_f=alertName,
                                format="wav",
                                codec="pcm_s16le",
                            )
                            self.__log__ = utilities.log(
                                AS_MAN.__callsign__,
                                AS_MAN.__webhooks__,
                                "Live Alert Patched",
                                f"{self.__alertData__['Protocol']}{self.__alertData__['From']}-",
                                self.__alertData__["Filter"]["Name"],
                                self.__monitorName__,
                                True,
                                alertName,
                                self.__monitor__["URL"],
                                AS_MAN.version,
                                self.__log__,
                                email=AS_MAN.__email__,
                            )
                        elif AS_MAN.__logger__:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Logging Alert.",
                                classType="MONITOR",
                                sev=severity.trace,
                            )
                            audFlag = False
                            aud = ""
                            if AS_MAN.__loggerAud__:
                                audFlag = True
                                aud = [alertName, liveBuff]
                            self.__log__ = utilities.log(
                                AS_MAN.__callsign__,
                                AS_MAN.__webhooks__,
                                "Live Alert Patched",
                                f"{self.__alertData__['Protocol']}{self.__alertData__['From']}-",
                                self.__alertData__["Filter"]["Name"],
                                self.__monitorName__,
                                audFlag,
                                aud,
                                self.__monitor__["URL"],
                                AS_MAN.version,
                                self.__log__,
                                email=AS_MAN.__email__,
                            )
                        elif not AS_MAN.__logger__ and AS_MAN.__export__:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Logging Alert.",
                                classType="MONITOR",
                                sev=severity.trace,
                            )
                            liveBuff.export(
                                out_f=alertName,
                                format="wav",
                                codec="pcm_s16le",
                            )
                        liveBuff = AudioSegment.empty()
                    elif self.__monitor__["Alert"] == True:
                        testStatus = True
                        if self.__useATTNDT__:
                            frequencies = self.__ATTNDetection__(
                                pkt=audioSamples,
                                bufferSize=4800,
                                sampleRate=24000,
                                window=window,
                            )
                            if frequencies:
                                if not detectedATTN:
                                    if threshLevelATTN <= 0:
                                        detectedATTN = True
                                    else:
                                        threshLevelATTN -= 1
                            else:
                                if detectedATTN:
                                    if threshLenATTN <= 0:
                                        detectedATTN = False
                                        threshLevelATTN = setLevel
                                        threshLenATTN = hold
                                    else:
                                        threshLenATTN -= 1
                        if detectedATTN:
                            if not activeATTN:
                                utilities.autoPrint(
                                    text=f"Monitor {self.__monitorName__}: Attention Tone Detected. Stopping Recording.",
                                    classType="MONITOR",
                                    sev=severity.debug,
                                )
                                alertAudio = alertAudio[: -(4800 * 6)]
                                self.__monitor__["AttentionTone"] = True
                                activeATTN = True
                                removedATTN = True
                        else:
                            if activeATTN:
                                utilities.autoPrint(
                                    text=f"Monitor {self.__monitorName__}: Attention Tone Ended.",
                                    classType="MONITOR",
                                    sev=severity.debug,
                                )
                                self.__monitor__["AttentionTone"] = False
                                activeATTN = False
                            if not len(alertAudio) / 24000 > 120:
                                alertAudio = append(
                                    alertAudio,
                                    audioSamples,
                                )
                            else:
                                utilities.autoPrint(
                                    text=f"Monitor {self.__monitorName__}: 120 Seconds reached, forcing End of Recording.",
                                    classType="MONITOR",
                                    sev=severity.debug,
                                )
                                self.__monitor__["Alert"] = False
                    elif testStatus == True:
                        testStatus = False
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: Ending alert Recording.",
                            classType="MONITOR",
                            sev=severity.info,
                        )
                        header = f"{self.__alertData__['Protocol']}{AS_MAN.__callsign__}-"
                        headerTranslation = EAS2Text(header)
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: Normalizing/Syncing Alert Audio.",
                            classType="MONITOR",
                            sev=severity.trace,
                        )
                        alertAudio = normalize(
                            AudioSegment(
                                alertAudio.tobytes(),
                                frame_rate=24000,
                                sample_width=2,
                                channels=1,
                            )[:-685],
                            headroom=0.1,
                        )
                        utilities.autoPrint(
                            text=f"Monitor {self.__monitorName__}: Generating Alert with Audio...",
                            classType="MONITOR",
                            sev=severity.trace,
                        )
                        alertSegment["headers"] = EASGen.genHeader(
                            header_data=header,
                            mode=AS_MAN.__config__["Emulation"],
                        )
                        if headerTranslation.evnt != "RWT":
                            if removedATTN:
                                alertSegment["attnTone"] = EASGen.genATTN(
                                    mode=AS_MAN.__config__["Emulation"]
                                )
                        alertSegment["message"] = alertAudio
                        alertSegment["eoms"] = EASGen.genEOM(
                            mode=AS_MAN.__config__["Emulation"]
                        )
                        alert = (
                            AudioSegment.silent(500)
                            + alertSegment["headers"]
                            + alertSegment["attnTone"]
                            + alertSegment["message"]
                            + alertSegment["eoms"]
                            + AudioSegment.silent(500)
                        )
                        utilities.autoPrint(
                            text=f"Audio Message Length: {round(len(alertAudio)/1000, 2)} Seconds.",
                            classType="MONITOR",
                            sev=severity.trace,
                        )
                        utilities.autoPrint(
                            text=f"Alert Total Length: {round(len(alert)/1000, 2)} Seconds.",
                            classType="MONITOR",
                            sev=severity.trace,
                        )
                        self.__alertData__["Length"] = round(
                            len(alert) / 24000, 2
                        )
                        self.__alertToOld__(
                            self.__alertData__["Protocol"], self.__alertData__
                        )
                        self.__relayManager__(
                            self.__alertData__, alertSegment, header
                        )
                        alertName = f"{AS_MAN.__exportFolder__}/EAS_{headerTranslation.org}-{headerTranslation.evnt}-{headerTranslation.timeStamp}-{headerTranslation.callsign.replace('/', '-').strip().replace(' ', '-')}.wav"
                        if AS_MAN.__logger__ and AS_MAN.__export__:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Logging Alert.",
                                classType="MONITOR",
                                sev=severity.trace,
                            )
                            alert.export(
                                out_f=alertName,
                                format="wav",
                                codec="pcm_s16le",
                            )
                            self.__log__ = utilities.log(
                                AS_MAN.__callsign__,
                                AS_MAN.__webhooks__,
                                "Alert Recieved",
                                f"{self.__alertData__['Protocol']}{self.__alertData__['From']}-",
                                self.__alertData__["Filter"]["Name"],
                                self.__monitorName__,
                                True,
                                alertName,
                                self.__monitor__["URL"],
                                AS_MAN.version,
                                self.__log__,
                                email=AS_MAN.__email__,
                            )
                        elif AS_MAN.__logger__:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Logging Alert.",
                                classType="MONITOR",
                                sev=severity.trace,
                            )
                            audFlag = False
                            aud = ""
                            if AS_MAN.__loggerAud__:
                                audFlag = True
                                aud = [alertName, alert]
                            self.__log__ = utilities.log(
                                AS_MAN.__callsign__,
                                AS_MAN.__webhooks__,
                                "Alert Recieved",
                                f"{self.__alertData__['Protocol']}{self.__alertData__['From']}-",
                                self.__alertData__["Filter"]["Name"],
                                self.__monitorName__,
                                audFlag,
                                aud,
                                self.__monitor__["URL"],
                                AS_MAN.version,
                                self.__log__,
                                email=AS_MAN.__email__,
                            )
                        elif not AS_MAN.__logger__ and AS_MAN.__export__:
                            utilities.autoPrint(
                                text=f"Monitor {self.__monitorName__}: Logging Alert.",
                                classType="MONITOR",
                                sev=severity.trace,
                            )
                            alert.export(
                                out_f=alertName,
                                format="wav",
                                codec="pcm_s16le",
                            )
                        alertAudio = empty(0, dtype=int16)
                    else:
                        if len(audioSamples) == 0:
                            audioBork += 1
                            if audioBork > 24000:
                                self.__stream__.kill()
                                self.__stream__.poll()
                                utilities.autoPrint(
                                    text=f"Monitor {self.__monitorName__}: Going Offline due to stream error.",
                                    classType="MONITOR",
                                    sev=severity.warning,
                                )
                                utilities.autoPrint(
                                    text=f"Monitor {self.__monitorName__}: {self.__monitor__['URL']} Lost.",
                                    classType="MONITOR",
                                    sev=severity.trace,
                                )
                                self.__monitor__["Online"] = False
                                self.__MonState__(update=True)
                        else:
                            audioBork = 0
            except Exception as E:
                sleep(0.1)
                if self.__run__:
                    utilities.autoPrint(
                        text=f"Monitor {self.__monitorName__}: {type(E).__name__}, {E}",
                        classType="MONITOR",
                        sev=severity.error,
                    )
                    tb = E.__traceback__
                    while tb is not None:
                        utilities.autoPrint(
                            text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                            classType="MONITOR",
                            sev=severity.error,
                        )
                        tb = tb.tb_next
        utilities.autoPrint(
            text=f"Monitor {self.__monitorName__}: Closing Monitor Thread.",
            classType="MONITOR",
            sev=severity.trace,
        )
        self.__stream__.kill()
        self.__stream__.poll()
        return

    # @classmethod
    # def PendAlert(cls, Alert, Add: bool):
    #     if Add:
    #         cls.__pendingAlerts__.append(Alert)
    #     else:
    #         cls.__pendingAlerts__.remove(Alert)

    def __relayManager__(self, alertData, alert, header):
        def alertWait(Data, filter):
            timeout = int(filter.split(":")[1])
            for i in range(timeout * 60):
                sleep(1)
            if filter.split(":")[0] == "Ignore":
                utilities.autoPrint(
                    text=f"Ignoring Alert {event} from {call}",
                    classType="RELAY",
                    sev=severity.info,
                )
                exit()
            else:
                utilities.autoPrint(
                    text=f"Sending Alert {event} from {call}",
                    classType="RELAY",
                    sev=severity.info,
                )
                currentAlert.append(Data)
                exit()

        action = alertData["Filter"]["Actions"]
        event = alertData["Event"]
        call = alertData["From"]
        data = {
            "Audio": alert,
            "Type": "Alert",
            "Event": event,
            "Callsign": call,
            "Protocol": header,
        }
        if "Now" in action:
            utilities.autoPrint(
                text=f"Sending Alert {event} from {call}",
                classType="RELAY",
                sev=severity.info,
            )
            currentAlert.append(data)
        else:
            utilities.autoPrint(
                text=f"Waiting for {action.split(':')[1]} minutes > Alert {event} from {call}",
                classType="RELAY",
                sev=severity.info,
            )
            t = Thread(
                target=alertWait,
                name=f"RELAY-{self.__monitorName__}",
                args=(
                    data,
                    action,
                ),
                daemon=True,
            )
            t.start()
        return


class AS_MAN:
    global currentAlert
    global liveAlert
    version = "0.1.69"
    __monitors__ = []
    __run__ = True
    __playback__ = False
    __config__ = None
    __configFile__ = ".config"
    __logFile__ = ".log"
    __localFIPS__ = []
    __callsign__ = "ASMARA/1"
    __icecastPlayout__ = False
    __icePlayer__ = None
    __leadIn__ = AudioSegment.empty()
    __leadOut__ = AudioSegment.empty()
    __samplerate__ = 24000
    __channels__ = 1
    __logger__ = False
    __webhooks__ = []
    __loggerAud__ = False
    __email__ = False
    __export__ = False
    __exportFolder__ = ""
    __filters__ = []
    __tone__ = AudioSegment.empty()
    __liveCount__ = 0
    __alertCount__ = 0
    __overrideCount__ = 0
    __capCount__ = 0
    __messageCount__ = 0
    __killDJ__ = False
    __alertSent__ = False

    @classmethod
    def __addCount__(cls, type):
        if type == "Override":
            cls.__overrideCount__ += 1
        elif type == "Live":
            cls.__liveCount__ += 1
            cls.__alertCount__ += 1
        elif type == "CAP":
            cls.__capCount__ += 1
        elif type == "Alert":
            cls.__alertCount__ += 1
        cls.__messageCount__ += 1

    @classmethod
    def __setConfig__(cls, config, configFile):
        cls.__config__ = config
        cls.__configFile__ = configFile

    @classmethod
    def __setLog__(cls):
        cls.__logFile__ = cls.__config__["LogFile"]

    @classmethod
    def __setCallsign__(cls):
        if len(cls.__config__["Callsign"]) <= 8:
            cls.__callsign__ = cls.__config__["Callsign"].ljust(8, " ")
        else:
            utilities.autoPrint(
                text="Callsign too long. Trimming...",
                classType="MAIN",
                sev=severity.debug,
            )
            cls.__callsign__ = cls.__config__["Callsign"][:8]

    @classmethod
    def __setLocalFIPS__(
        cls,
    ):
        locFips = cls.__config__["LocalFIPS"]
        for i in locFips:
            if i.upper() not in ["LOC", "LOCAL"]:
                cls.__localFIPS__.append(i)

    @classmethod
    def __setSamplerate__(cls):
        cls.__samplerate__ = cls.__config__["PlayoutManager"]["SampleRate"]

    @classmethod
    def __setChannels__(cls):
        cls.__channels__ = cls.__config__["PlayoutManager"]["Channels"]

    @classmethod
    def __setLogger__(cls):
        cls.__logger__ = cls.__config__["Logger"]["Enabled"]
        cls.__webhooks__ = cls.__config__["Logger"]["Webhooks"]
        cls.__loggerAud__ = cls.__config__["Logger"]["Audio"]

    @classmethod
    def __setEmail__(cls):
        if cls.__config__["Logger"]["Email"]["Enabled"]:
            cls.__email__ = cls.__config__["Logger"]["Email"]
        else:
            cls.__email__ = False

    @classmethod
    def __setExport__(cls):
        cls.__export__ = cls.__config__["PlayoutManager"]["Export"]["Enabled"]
        cls.__exportFolder__ = cls.__config__["PlayoutManager"]["Export"][
            "Folder"
        ]

    @classmethod
    def __setFilters__(cls):
        cls.__filters__ = cls.__config__["Filters"]

    @classmethod
    def __setIcePlayout__(cls):
        cls.__icecastPlayout__ = cls.__config__["PlayoutManager"]["Icecast"][
            "Enabled"
        ]
        cls.__IcecastServer__ = cls.__config__["PlayoutManager"]["Icecast"]

    @classmethod
    def __killIcePlayer__(cls):
        if cls.__icePlayer__ != None:
            cls.__icePlayer__.kill()
            sleep(1)
            cls.__icePlayer__ = None

    @classmethod
    def __setIcePlayer__(cls):
        utilities.autoPrint(
            text="Creating Playout (Icecast)",
            classType="PLAYOUT",
            sev=severity.debug,
        )
        codecs = {
            "mp3": ("libmp3lame", "audio/mpeg", "mp3"),
            "ogg": ("libvorbis", "audio/ogg", "ogg"),
            "flac": ("flac", "audio/flac", "flac"),
            "opus": ("libopus", "audio/ogg", "opus"),
        }
        codec, content, format = codecs["mp3"]
        cls.__icePlayer__ = Popen(
            [
                "ffmpeg",
                "-re",
                "-hide_banner",
                "-loglevel",
                "quiet",
                "-nostats",
                "-f",
                "s16le",
                "-ac",
                f"{cls.__config__['PlayoutManager']['Channels']}",
                "-ar",
                f"{cls.__config__['PlayoutManager']['SampleRate']}",
                "-i",
                "-",
                "-ab",
                cls.__IcecastServer__["Bitrate"],
                "-c:a",
                codec,
                "-content_type",
                content,
                "-f",
                format,
                "-ice_name",
                f'"{cls.__callsign__} - ASMARA"',
                f"icecast://{cls.__IcecastServer__['Source']}:{cls.__IcecastServer__['Pass']}@{cls.__IcecastServer__['Address']}:{cls.__IcecastServer__['Port']}/{cls.__IcecastServer__['Mountpoint']}",
            ],
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )

    @classmethod
    def __setLeadIn__(cls):
        if cls.__config__["PlayoutManager"]["LeadIn"]["Enabled"]:
            file = cls.__config__["PlayoutManager"]["LeadIn"]["File"]
            type = cls.__config__["PlayoutManager"]["LeadIn"]["Type"]
            cls.__leadIn__ = AudioSegment.silent(500) + AudioSegment.from_file(
                file=file, format=type
            ).set_frame_rate(cls.__samplerate__).set_sample_width(
                2
            ).set_channels(
                1
            )

    @classmethod
    def __setLeadOut__(cls):
        if cls.__config__["PlayoutManager"]["LeadOut"]["Enabled"]:
            file = cls.__config__["PlayoutManager"]["LeadOut"]["File"]
            type = cls.__config__["PlayoutManager"]["LeadOut"]["Type"]
            cls.__leadOut__ = AudioSegment.from_file(
                file=file, format=type
            ).set_frame_rate(cls.__samplerate__).set_sample_width(
                2
            ).set_channels(
                1
            ) + AudioSegment.silent(
                500
            )

    def __loadLogs__(self):
        try:
            with open(self.__logFile__, "r") as f:
                utilities.autoPrint(
                    text=f"Loading '{self.__logFile__}' to Alert Database",
                    classType="MAIN",
                    sev=severity.debug,
                )
                logFile = load(f)
            try:
                key = list(logFile[self.__callsign__]["Alerts"].keys())
                for index in range(len(key[-10:])):
                    k = key[index]
                    v = logFile[self.__callsign__]["Alerts"][k]
                    AS_MON.__alertToOld__(k, v)
                utilities.autoPrint(
                    text="Done loading alert database",
                    classType="MAIN",
                    sev=severity.debug,
                )
            except KeyError:
                utilities.autoPrint(
                    text="Failed to load alert database",
                    classType="MAIN",
                    sev=severity.debugErr,
                )
                logFile[self.__callsign__] = {}
                logFile[self.__callsign__]["Alerts"] = {}
                logFile[self.__callsign__]["Weekly"] = {"Timestamp": 0}
                with open(self.__logFile__, "w") as f:
                    dump(logFile, f, indent=4)
        except FileNotFoundError:
            utilities.autoPrint(
                text=f"Creating Log File to '{self.__logFile__}'",
                classType="MAIN",
                sev=severity.debug,
            )
            with open(self.__logFile__, "w") as f:
                var = {self.__callsign__: {"Alerts": {}}}
                dump(var, f, indent=4)

    def __makeConfig__(self):
        utilities.autoPrint(
            text="New Config Made, please configure it properly before use.",
            classType="MAIN",
            sev=severity.info,
        )
        ## TODO: Simple Initial Config Setup Script

    @classmethod
    def __setTone__(cls):
        cls.__tone__ = cls.__config__["PlayoutManager"]["AutoDJ"]["Tone"]

    def __loadConfig__(self):
        self.__setLog__()
        self.__setIcePlayout__()
        self.__setCallsign__()
        self.__setLocalFIPS__()
        self.__setLeadIn__()
        self.__setLeadOut__()
        self.__setSamplerate__()
        self.__setChannels__()
        self.__setLogger__()
        self.__setEmail__()
        self.__setExport__()
        self.__setFilters__()
        self.__loadLogs__()
        self.__setTone__()

    @classmethod
    def __changeState__(cls):
        cls.__run__ = True

    def __init__(self, configFile) -> None:
        self.__configFile__ = configFile
        if self.__run__ != True:
            self.__changeState__()
        try:
            with open(self.__configFile__, "r") as f:
                self.__setConfig__(load(f), self.__configFile__)
        except FileNotFoundError:
            utilities.autoPrint(
                text=f"Config file has been removed, or does not exist.\nWriting the default config file to '{self.__configFile__}'",
                classType="MAIN",
                sev=severity.warning,
            )
            try:
                utilities.writeDefConfig(self.__configFile__)
                with open(self.__configFile__, "r") as f:
                    self.__setConfig__(load(f), self.__configFile__)
                self.__makeConfig__()
            except FileNotFoundError or PermissionError:
                utilities.autoPrint(
                    text="FATAL ERROR, CANNOT READ OR WRITE CONFIG FILE. CLOSING...",
                    classType="MAIN",
                    sev=severity.fatal,
                )
                exit(1)
        self.__loadConfig__()
        self.__log__ = ""
        self.__alertAvailable__ = False
        self.__alertLive__ = False
        self.__nowPlaying__ = self.__config__["PlayoutManager"]["Icecast"][
            "WaitingStatus"
        ]
        self.__nowPlayingData__ = AudioSegment.empty()
        self.__nowPlayingTS__ = 0
        AS_MON.__run__ = True
        self.__alertManager__ = Thread(
            target=self.__AlertCountManager__, name="MANAGER", daemon=True
        )
        self.__playoutManager__ = Thread(
            target=self.__playout__, name="PLAYOUT", daemon=True
        )
        self.__dataPumpThread__ = Thread(
            target=self.__dataPump__, name="DATAPUMP", daemon=True
        )
        self.__DJ__ = Thread(
            target=self.__autoDJ__, name="AUTODJ", daemon=True
        )
        self.__overrideManager__ = Thread(
            target=self.__overrideManager__,
            name="OVERRIDE",
            daemon=True,
        )
        utilities.autoPrint(
            text="Creating AlertManager.",
            classType="MAIN",
            sev=severity.debug,
        )
        self.__alertManager__.start()
        utilities.autoPrint(
            text="Creating PlayoutManager.",
            classType="MAIN",
            sev=severity.debug,
        )
        self.__playoutManager__.start()
        self.__dataPumpThread__.start()
        if self.__config__["PlayoutManager"]["AutoDJ"]["Enabled"]:
            utilities.autoPrint(
                text="Creating AutoDJ.",
                classType="MAIN",
                sev=severity.debug,
            )
            self.__DJ__.start()
        if self.__config__["PlayoutManager"]["Override"]["Enabled"]:
            utilities.autoPrint(
                text="Creating OverrideManager.",
                classType="MAIN",
                sev=severity.debug,
            )
            self.__overrideManager__.start()
        for monitor in self.__config__["Monitors"]:
            self.__monitors__.append(AS_MON(monitor))

    @classmethod
    def __killMonitors__(cls):
        utilities.autoPrint(
            text=f"Killing Monitors...",
            classType="MANAGER",
            sev=severity.debug,
        )
        AS_MON.__run__ = False
        for (
            monitor
        ) in cls.__monitors__:  ## TODO: Simple Initial Config Setup Script
            monitor.killMon()
        AS_MON.__monitors__.clear()
        cls.__monitors__.clear()

    @classmethod
    def killAsmara(cls):
        if AS_MON.__run__:
            cls.__killMonitors__()
        cls.__icecastPlayout__ = False
        utilities.autoPrint(
            text=f"Killing Playout Services...",
            classType="MANAGER",
            sev=severity.debug,
        )
        cls.__run__ = False
        cls.__killIcePlayer__()
        utilities.autoPrint(
            "ASMARA Killed. Waiting for all services to end...",
            sev=severity.boot,
        )
        wait = 0
        while len(enumerate()) > 1:
            if wait < 4:
                sleep(1)
            elif wait == 4:
                for child in active_children():
                    child.kill()
                sleep(1)
            else:
                ## Force kill remaining processes.
                break
        utilities.autoPrint(
            "====================================\n\n", sev=severity.boot
        )
        return

    def __alertFileDump__(self, alerts: list = []):
        if len(alerts) == 0:
            pass
        else:
            with open(self.__logFile__, "r+") as f:
                log = load(f)
                for alert in alerts:
                    log[self.__callsign__]["Alerts"].update(alert)
                f.seek(0)
                dump(log, f, indent=4)
        return

    def __AlertCountManager__(self):
        alerts = []
        while self.__run__:
            if len(AS_MON.__receivedAlertsIndex__) > 50:
                utilities.autoPrint(
                    text=f"Clearing old alerts...",
                    classType="MANAGER",
                    sev=severity.trace,
                )
                while len(AS_MON.__receivedAlertsIndex__) > 40:
                    alerts.append(AS_MON.__alertFromOld__(0))
                self.__alertFileDump__(alerts=alerts)
                alerts = []
                utilities.autoPrint(
                    text=f"Done clearing old alerts.",
                    classType="MANAGER",
                    sev=severity.trace,
                )
            else:
                pass
            i = 60
            while self.__run__ and i != 0:
                sleep(1)
                i -= 1
        utilities.autoPrint(
            text="Dumping Old Alerts...",
            classType="MANAGER",
            sev=severity.trace,
        )
        alerts = []
        for alert in AS_MON.__receivedAlertsIndex__:
            alerts.append(AS_MON.__alertFromOld__(0))
        self.__alertFileDump__(alerts=alerts)

    def __overrideManager__(self):
        while self.__run__:
            sleep(0.5)  # High number because Low Prio
            overrideFolder = self.__config__["PlayoutManager"]["Override"][
                "Folder"
            ]
            if not overrideFolder.startswith(
                "/"
            ) or not overrideFolder.startswith("C:/"):
                overrideFolder = (
                    getcwd()
                    + "/"
                    + self.__config__["PlayoutManager"]["Override"]["Folder"]
                )
            for r, d, files in walk(overrideFolder):
                for file in files:
                    if file.lower() == "holdplacer":
                        pass
                    elif file.lower().endswith(".wav"):
                        sleep(1)  # High number because Low Prio
                        utilities.autoPrint(
                            text=f"Adding file {str(file)} to Playout System.",
                            classType="OVERRIDE",
                            sev=severity.debug,
                        )
                        ALERT = {
                            "Audio": AudioSegment.silent(500)
                            + AudioSegment.from_wav(path.join(r, file))
                            .set_frame_rate(self.__samplerate__)
                            .set_sample_width(2)
                            .set_channels(1)
                            + AudioSegment.silent(500),
                            "Type": "Override",
                            "Protocol": file,
                        }
                        if self.__export__:
                            ALERT["Audio"].export(
                                f"{self.__exportFolder__}/OVERRIDE_{file.split('.')[0]}.wav",
                                format="wav",
                            )
                        currentAlert.append(ALERT)
                        remove(path.join(r, file))
                    elif file.lower().endswith(".mp3"):
                        art = ""
                        com = ""
                        sleep(1)  # High number because Low Prio
                        try:
                            test = mediainfo(path.join(r, file))
                            try:
                                art = test["TAG"]["artist"]
                                com = test["TAG"]["comments"]
                            except KeyError:
                                sleep(5)
                                try:
                                    test = mediainfo(path.join(r, file))
                                    art = test["TAG"]["artist"]
                                    com = test["TAG"]["comments"]
                                except KeyError:
                                    pass
                            if art == "capdec":
                                headerTranslation = EAS2Text(com)
                                ALERT = {
                                    "Audio": AudioSegment.silent(500)
                                    + AudioSegment.from_mp3(path.join(r, file))
                                    .set_frame_rate(self.__samplerate__)
                                    .set_sample_width(2)
                                    .set_channels(1)
                                    + AudioSegment.silent(500),
                                    "Event": " ".join(
                                        headerTranslation.evntText.split(" ")[
                                            1:
                                        ]
                                    ),
                                    "Callsign": "CAPDEC",
                                    "Type": "CAP",
                                    "Protocol": com,
                                }
                                noCall = "-".join(com.split("-")[:-2]) + "-"
                                if not noCall in AS_MON.__receivedAlerts__:
                                    utilities.autoPrint(
                                        text="Adding CAP Alert to Playout System.",
                                        classType="OVERRIDE",
                                        sev=severity.debug,
                                    )
                                    if self.__export__:
                                        ALERT["Audio"].export(
                                            f"{self.__exportFolder__}/EAS_CAP-{headerTranslation.org}-{headerTranslation.evnt}-{headerTranslation.timeStamp}-CAPDEC.wav"
                                        )
                                    alertData = {
                                        "Monitor": "CAP",
                                        "Time": mktime(
                                            DT.utcnow().timetuple()
                                        ),
                                        "Event": " ".join(
                                            headerTranslation.evntText.split(
                                                " "
                                            )[1:]
                                        ),
                                        "Protocol": noCall,
                                        "From": headerTranslation.callsign,
                                        "Filter": {
                                            "Matched": True,
                                            "Name": "CAPDEC",
                                            "Actions": "Relay:Now",
                                        },
                                        "Length": (len(ALERT["Audio"]) / 1000),
                                    }
                                    AS_MON.__alertToOld__(com, alertData)
                                    if self.__logger__ and self.__export__:
                                        self.__log__ = utilities.log(
                                            self.__callsign__,
                                            self.__webhooks__,
                                            "CAP Alert Sent",
                                            com,
                                            "",
                                            "",
                                            True,
                                            f"{self.__exportFolder__}/EAS_CAP-{headerTranslation.org}-{headerTranslation.evnt}-{headerTranslation.timeStamp}-CAPDEC.wav",
                                            "",
                                            self.version,
                                            email=self.__email__,
                                        )
                                    elif self.__logger__:
                                        self.__log__ = utilities.log(
                                            self.__callsign__,
                                            self.__webhooks__,
                                            "CAP Alert Sent",
                                            com,
                                            "",
                                            "",
                                            False,
                                            "",
                                            "",
                                            self.version,
                                            email=self.__email__,
                                        )
                                    currentAlert.append(ALERT)
                                else:
                                    utilities.autoPrint(
                                        text="CAP Alert already sent.",
                                        classType="OVERRIDE",
                                        sev=severity.debug,
                                    )
                            else:
                                utilities.autoPrint(
                                    text=f"Adding file {str(file)} to Playout System.",
                                    classType="OVERRIDE",
                                    sev=severity.debug,
                                )
                                ALERT = {
                                    "Audio": AudioSegment.silent(500)
                                    + AudioSegment.from_mp3(path.join(r, file))
                                    .set_frame_rate(self.__samplerate__)
                                    .set_sample_width(2)
                                    .set_channels(1)
                                    + AudioSegment.silent(500),
                                    "Type": "Override",
                                    "Protocol": file,
                                }
                                if self.__export__:
                                    ALERT["Audio"].export(
                                        f"{self.__exportFolder__}/OVERRIDE_{file.split('.')[0]}.wav",
                                        format="wav",
                                    )
                                currentAlert.append(ALERT)
                        except Exception as E:
                            utilities.autoPrint(
                                text=f"{type(E).__name__}, {E}",
                                classType="OVERRIDE",
                                sev=severity.error,
                            )
                            tb = E.__traceback__
                            while tb is not None:
                                utilities.autoPrint(
                                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                                    classType="OVERRIDE",
                                    sev=severity.error,
                                )
                                tb = tb.tb_next
                        remove(path.join(r, file))
                    else:
                        utilities.autoPrint(
                            text=f"[OVERRIDE] File {file} is not a WAV, MP3, FLV, or OGG file.",
                            classType="OVERRIDE",
                            sev=severity.debugErr,
                        )
                        remove(path.join(r, file))

    def __dataPump__(self):
        global liveAlert
        global currentAlert
        while self.__run__:
            if len(currentAlert) != 0:
                self.__addCount__(currentAlert[0]["Type"])
                if self.__icecastPlayout__ or self.__Playout__:
                    if currentAlert[0]["Type"] == "Live":
                        self.__alertLive__ = True
                    self.__alertAvailable__ = True
                else:
                    liveAlert.clear()
                    currentAlert.pop(0)
                    utilities.autoPrint(
                        text="Disposing Alert Audio",
                        classType="PLAYOUT",
                        sev=severity.trace,
                    )
            else:
                pass
            sleep(0.25)

    def __autoDJ__(self):
        utilities.autoPrint(
            text="Started.",
            classType="AUTODJ",
            sev=severity.trace,
        )
        self.__nowPlayingTS__ = 0
        self.__nowPlaying__ = ""
        self.__nowPlayingData__ = AudioSegment.empty()
        while self.__run__:
            musicList = []
            idList = []
            songsPlayed = 0
            utilities.autoPrint(
                text="Loading Music Libraries.",
                classType="AUTODJ",
                sev=severity.trace,
            )
            for r, d, files in walk(
                getcwd()
                + "/"
                + self.__config__["PlayoutManager"]["AutoDJ"]["Folder"]
            ):
                for file in files:
                    if not self.__run__:
                        return
                    if file.endswith("mp3") or file.endswith("wav"):
                        musicList.append(r + "/" + file)
            utilities.autoPrint(
                text="Loading ID Libraries.",
                classType="AUTODJ",
                sev=severity.trace,
            )
            for r, d, files in walk(
                getcwd()
                + "/"
                + self.__config__["PlayoutManager"]["AutoDJ"]["IDFolder"]
            ):
                for file in files:
                    if not self.__run__:
                        return
                    if file.endswith("mp3") or file.endswith("wav"):
                        idList.append(r + "/" + file)
            utilities.autoPrint(
                text="Starting Playback Interface System.",
                classType="AUTODJ",
                sev=severity.trace,
            )
            if len(musicList) == 0:
                utilities.autoPrint(
                    text="No Music Detected. Running Silence or Tone.",
                    classType="AUTODJ",
                    sev=severity.trace,
                )
                self.__nowPlayingTS__ = 0
                self.__nowPlaying__ = self.__config__["PlayoutManager"][
                    "Icecast"
                ]["WaitingStatus"]
                if self.__tone__:
                    self.__nowPlayingData__ = (
                        Sine(freq=1000, sample_rate=24000, bit_depth=16)
                        .to_audio_segment(duration=10000, volume=0)
                        .set_frame_rate(self.__samplerate__)
                        .set_channels(2)
                    )
                else:
                    self.__nowPlayingData__ = AudioSegment.silent(10000)
                if self.__alertSent__ or self.__killDJ__:
                    sleep(0.25)
                for sec in range(int(len(self.__nowPlayingData__) / 1000) * 4):
                    if not self.__run__:
                        return
                    self.__nowPlayingTS__ = sec
                    sleep(0.25)
                    if self.__killDJ__:
                        utilities.autoPrint(
                            text="Kill Signal ACK.",
                            classType="AUTODJ",
                            sev=severity.trace,
                        )
                        break
            else:
                shuffle(musicList)
                while len(musicList) > 0:
                    if songsPlayed == 0:
                        if len(idList) != 0:
                            try:
                                self.__nowPlayingTS__ = 0
                                song = choice(idList)
                                utilities.autoPrint(
                                    text="Loaded ID Data.",
                                    classType="AUTODJ",
                                    sev=severity.trace,
                                )
                                if song.endswith("mp3"):
                                    songData = (
                                        AudioSegment.from_mp3(song)
                                        .set_frame_rate(
                                            frame_rate=self.__samplerate__
                                        )
                                        .set_channels(self.__channels__)
                                        .set_sample_width(2)
                                    )
                                elif song.endswith("wav"):
                                    songData = (
                                        AudioSegment.from_wav(song)
                                        .set_frame_rate(
                                            frame_rate=self.__samplerate__
                                        )
                                        .set_channels(self.__channels__)
                                        .set_sample_width(2)
                                    )
                                self.__nowPlaying__ = (
                                    f"{self.__callsign__.strip()} IP Radio"
                                )
                                utilities.autoPrint(
                                    text="Created ID Data; Patching to Playout.",
                                    classType="AUTODJ",
                                    sev=severity.trace,
                                )
                                self.__nowPlayingData__ = (
                                    AudioSegment.silent(250)
                                    + songData
                                    + AudioSegment.silent(250)
                                )
                                if self.__alertSent__ or self.__killDJ__:
                                    sleep(0.25)
                                for sec in range(
                                    int(len(songData) / 1000) * 4
                                ):
                                    if not self.__run__:
                                        return
                                    self.__nowPlayingTS__ = sec
                                    sleep(0.25)
                                    if self.__killDJ__:
                                        utilities.autoPrint(
                                            text="Kill Signal ACK.",
                                            classType="AUTODJ",
                                            sev=severity.trace,
                                        )
                                        break
                                utilities.autoPrint(
                                    text="Finished sending ID Data.",
                                    classType="AUTODJ",
                                    sev=severity.trace,
                                )
                                songsPlayed = self.__config__[
                                    "PlayoutManager"
                                ]["AutoDJ"]["IDSongs"]
                            except FileNotFoundError:
                                idList.remove(song)
                                continue
                    try:
                        self.__nowPlayingTS__ = 0
                        song = choice(musicList)
                        musicList.remove(song)
                        utilities.autoPrint(
                            text="Loaded Audio Data.",
                            classType="AUTODJ",
                            sev=severity.trace,
                        )
                        if song.endswith("mp3"):
                            songData = (
                                AudioSegment.from_mp3(song)
                                .set_frame_rate(frame_rate=self.__samplerate__)
                                .set_channels(self.__channels__)
                                .set_sample_width(2)
                            )
                        elif song.endswith("wav"):
                            songData = (
                                AudioSegment.from_wav(song)
                                .set_frame_rate(frame_rate=self.__samplerate__)
                                .set_channels(self.__channels__)
                                .set_sample_width(2)
                            )
                        try:
                            test = mediainfo(song)
                            title = test["TAG"]["title"]
                            artist = test["TAG"]["artist"]
                            self.__nowPlaying__ = f"{title} - {artist}"
                        except:
                            self.__nowPlaying__ = ".".join(
                                song.split("/")[-1].split(".")[:-1]
                            )
                        utilities.autoPrint(
                            text="Created Audio Data; Patching to Playout.",
                            classType="AUTODJ",
                            sev=severity.trace,
                        )
                        self.__nowPlayingData__ = songData
                        if self.__alertSent__ or self.__killDJ__:
                            sleep(0.25)
                        for sec in range(int(len(songData) / 1000) * 4):
                            if not self.__run__:
                                return
                            self.__nowPlayingTS__ = sec
                            sleep(0.25)
                            if self.__killDJ__:
                                utilities.autoPrint(
                                    text="Kill Signal ACK.",
                                    classType="AUTODJ",
                                    sev=severity.trace,
                                )
                                break
                        utilities.autoPrint(
                            text="Finished sending Audio Data.",
                            classType="AUTODJ",
                            sev=severity.trace,
                        )
                        songsPlayed -= 1
                    except FileNotFoundError:
                        musicList.remove(song)
                        continue

    @classmethod
    def __makeURLReady__(cls, data):
        return (
            data.replace("%", "%25")
            .replace("$", "%24")
            .replace("&", "%26")
            .replace("+", "%2B")
            .replace(",", "%2C")
            .replace("/", "%2F")
            .replace(":", "%eA")
            .replace(";", "%3B")
            .replace("=", "%3D")
            .replace("?", "%3F")
            .replace("@", "%40")
            .replace(" ", "%20")
            .replace('"', "%22")
            .replace("<", "%3C")
            .replace(">", "%3E")
            .replace("#", "%23")
            .replace("{", "%7B")
            .replace("}", "%7D")
            .replace("|", "%7C")
            .replace("\\", "%5C")
            .replace("^", "%5E")
            .replace("~", "%7E")
            .replace("[", "%5B")
            .replace("]", "%5D")
            .replace("`", "%60")
        )

    @classmethod
    def __UpdateIcecastNP__(cls, server, data):
        try:
            get(
                f"http://{server['Address']}:{server['Port']}/admin/metadata?mount=/{server['Mountpoint']}&mode=updinfo&song={cls.__makeURLReady__(data)}",
                auth=(server["Source"], server["Pass"]),
            )
        except ConnectionResetError:
            utilities.autoPrint(
                text="Failed to update Icecast Info, Connection Reset.",
                classType="PLAYOUT",
                sev=severity.debugErr,
            )
        except exceptions.ChunkedEncodingError:
            utilities.autoPrint(
                text="Failed to update Icecast Info, Connection Reset.",
                classType="PLAYOUT",
                sev=severity.debugErr,
            )
        except Exception as E:
            utilities.autoPrint(
                text=f"{type(E).__name__}, {E}",
                classType="PLAYOUT",
                sev=severity.error,
            )
            tb = E.__traceback__
            while tb is not None:
                utilities.autoPrint(
                    text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                    classType="PLAYOUT",
                    sev=severity.error,
                )
                tb = tb.tb_next

    def __playout__(self):
        global currentAlert
        iceWorking = False
        if self.__icecastPlayout__:
            self.__setIcePlayer__()
            iceWorking = True
        NP = ""
        sleep(1)
        dataBuffer = AudioSegment.empty()
        while self.__run__:
            if not self.__alertAvailable__:
                try:
                    if not self.__nowPlaying__:
                        ## We don't have any data.
                        self.__killDJ__ = True
                        if self.__icecastPlayout__ and iceWorking:
                            self.__icePlayer__.stdin.write(
                                AudioSegment.silent(
                                    duration=250,
                                    frame_rate=self.__samplerate__,
                                ).raw_data
                            )
                            sleep(0.125)
                    else:
                        data = [AudioSegment.silent(250)]
                        if (
                            self.__nowPlayingData__ != dataBuffer
                            and self.__killDJ__
                        ):
                            utilities.autoPrint(
                                text=f"NEW DATA",
                                classType="PLAYOUT",
                                sev=severity.trace,
                            )
                            dataBuffer = self.__nowPlayingData__
                            ## We are done playing, New data is ready.
                            ## LOAD DATA, SET PLAY FLAG FALSE
                            self.__killDJ__ = False
                            if self.__nowPlaying__ != NP:
                                utilities.autoPrint(
                                    text=f"Now Playing: {self.__nowPlaying__}",
                                    classType="PLAYOUT",
                                    sev=severity.playoutStats,
                                )
                                NP = self.__nowPlaying__
                                if self.__icecastPlayout__ and iceWorking:
                                    self.__UpdateIcecastNP__(
                                        self.__IcecastServer__,
                                        self.__nowPlaying__,
                                    )
                            data = make_chunks(self.__nowPlayingData__, 250)
                        elif (
                            self.__nowPlayingData__ == dataBuffer
                            and self.__killDJ__
                        ):
                            ## We are done playing, No new data.
                            ## FORCE KILL DJ, PATCH SILENCE
                            self.__killDJ__ = True
                        elif self.__alertSent__:
                            ## We just sent an alert, and need to get back to the audio channel.
                            self.__alertSent__ = False
                            data = make_chunks(self.__nowPlayingData__, 250)[
                                self.__nowPlayingTS__ :
                            ]
                        else:
                            utilities.autoPrint(
                                text=f"UNKNOWN STATE: This is a bug!\nKilling current patch.",
                                classType="PLAYOUT",
                                sev=severity.debugWarn,
                            )
                            ## We are in an unknown state
                            ## SIGNAL DONE PLAY, KILL DJ, PATCH SILENCE
                            self.__killDJ__ = True
                        for chunkyBoi in data:
                            if not self.__alertAvailable__:
                                if self.__icecastPlayout__:
                                    try:
                                        if iceWorking:
                                            self.__icePlayer__.stdin.write(
                                                chunkyBoi.raw_data
                                            )
                                            if (
                                                chunkyBoi == data[-1]
                                                and len(data) > 1
                                            ):
                                                utilities.autoPrint(
                                                    text=f"DONE PLAYBACK",
                                                    classType="PLAYOUT",
                                                    sev=severity.trace,
                                                )
                                                ## Data is finished playing.
                                                self.__killDJ__ = True
                                        else:
                                            utilities.autoPrint(
                                                text=f"Trying to restore Icecast...",
                                                classType="PLAYOUT",
                                                sev=severity.debug,
                                            )
                                            self.__killIcePlayer__()
                                            self.__setIcePlayer__()
                                            sleep(1)
                                            iceWorking = True
                                    except BrokenPipeError as E:
                                        if self.__run__:
                                            utilities.autoPrint(
                                                text=f"Icecast Playout Crashed.",
                                                classType="PLAYOUT",
                                                sev=severity.error,
                                            )
                                            iceWorking = False
                                    except Exception as E:
                                        utilities.autoPrint(
                                            text=f"IC {type(E).__name__}, {E}",
                                            classType="PLAYOUT",
                                            sev=severity.error,
                                        )
                                        tb = E.__traceback__
                                        while tb is not None:
                                            utilities.autoPrint(
                                                text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                                                classType="PLAYOUT",
                                                sev=severity.error,
                                            )
                                            tb = tb.tb_next
                                        iceWorking = False
                except BrokenPipeError as E:
                    if self.__run__:
                        utilities.autoPrint(
                            text=f"Icecast Playout Crashed.",
                            classType="PLAYOUT",
                            sev=severity.error,
                        )
                        iceWorking = False
                except Exception as E:
                    utilities.autoPrint(
                        text=f"PL {type(E).__name__}, {E}",
                        classType="PLAYOUT",
                        sev=severity.error,
                    )
                    tb = E.__traceback__
                    while tb is not None:
                        utilities.autoPrint(
                            text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                            classType="PLAYOUT",
                            sev=severity.error,
                        )
                        tb = tb.tb_next
            else:
                try:
                    if self.__alertLive__:
                        alertData = currentAlert.pop(0)
                        liveIndex = alertData["Audio"]
                        event = alertData["Event"]
                        Call = alertData["Callsign"]
                        if self.__logger__:
                            self.__log__ = utilities.log(
                                self.__callsign__,
                                self.__webhooks__,
                                "Alert Sent",
                                alertData["Protocol"],
                                "",
                                "",
                                False,
                                "",
                                "",
                                self.version,
                                email=AS_MAN.__email__,
                            )
                        if self.__icecastPlayout__ and iceWorking:
                            self.__UpdateIcecastNP__(
                                self.__IcecastServer__,
                                f"LIVE ALERT: {event} from {Call}.",
                            )
                        self.__playback__ = True
                        utilities.autoPrint(
                            text=f"LIVE ALERT: {event} from {Call}.",
                            classType="PLAYOUT",
                            sev=severity.info,
                        )
                        while len(liveAlert[liveIndex]) != 0:
                            segment = liveAlert[liveIndex].pop(0)
                            if type(segment) == str:
                                if segment == "HEADER_HEADER_HEADER":
                                    utilities.autoPrint(
                                        text=f"SENDING HEADERS.",
                                        classType="PLAYOUT",
                                        sev=severity.playoutStats,
                                    )
                                elif segment == "TONE_TONE_TONE":
                                    utilities.autoPrint(
                                        text=f"SENDING ATTENTION TONE.",
                                        classType="PLAYOUT",
                                        sev=severity.playoutStats,
                                    )
                                elif segment == "AUDIO_AUDIO_AUDIO":
                                    utilities.autoPrint(
                                        text=f"SENDING AUDIO MESSAGE.",
                                        classType="PLAYOUT",
                                        sev=severity.playoutStats,
                                    )
                                elif segment == "EOM_EOM_EOM":
                                    utilities.autoPrint(
                                        text=f"SENDING EOMS.",
                                        classType="PLAYOUT",
                                        sev=severity.playoutStats,
                                    )
                            else:
                                alertAudio = segment.set_frame_rate(
                                    self.__samplerate__
                                ).set_channels(
                                    self.__config__["PlayoutManager"][
                                        "Channels"
                                    ]
                                )
                                data = make_chunks(alertAudio, 50)
                                for chunk in data:
                                    if self.__icecastPlayout__ and iceWorking:
                                        self.__icePlayer__.stdin.write(
                                            chunk.raw_data
                                        )
                        self.__playback__ = False
                        utilities.autoPrint(
                            text="Finished Playout.",
                            classType="PLAYOUT",
                            sev=severity.debug,
                        )
                        if self.__icecastPlayout__ and iceWorking:
                            self.__UpdateIcecastNP__(
                                self.__IcecastServer__, self.__nowPlaying__
                            )
                        self.__alertAvailable__ = False
                        self.__alertLive__ = False
                    else:
                        alertData = currentAlert.pop(0)
                        overrideFile = False
                        if alertData["Type"] == "Override":
                            overrideFile = True
                            oof = f"Playing Override File {alertData['Protocol']}."
                            segments = [
                                ("LEAD-IN", self.__leadIn__),
                                (
                                    f"OVERRIDE AUDIO FILE {alertData['Protocol']}",
                                    AudioSegment.silent(500)
                                    + alertData["Audio"]
                                    + AudioSegment.silent(500),
                                ),
                                ("LEAD-OUT", self.__leadOut__),
                            ]
                        elif alertData["Type"] == "Alert":
                            event = alertData["Event"]
                            Call = alertData["Callsign"]
                            if self.__logger__:
                                self.__log__ = utilities.log(
                                    self.__callsign__,
                                    self.__webhooks__,
                                    "Alert Sent",
                                    alertData["Protocol"],
                                    "",
                                    "",
                                    False,
                                    "",
                                    "",
                                    self.version,
                                    email=AS_MAN.__email__,
                                )
                            alertAudio = alertData["Audio"]
                            oof = f"Relaying {event} from {Call}."
                            segments = [
                                ("LEAD-IN", self.__leadIn__),
                                (
                                    "HEADERS",
                                    AudioSegment.silent(500)
                                    + alertAudio["headers"],
                                ),
                                ("ATTENTION TONE", alertAudio["attnTone"]),
                                ("AUDIO MESSAGE", alertAudio["message"]),
                                (
                                    "EOMS",
                                    alertAudio["eoms"]
                                    + AudioSegment.silent(500),
                                ),
                                ("LEAD-OUT", self.__leadOut__),
                            ]
                        utilities.autoPrint(
                            text=f"{oof}",
                            classType="PLAYOUT",
                            sev=severity.info,
                        )
                        if self.__icecastPlayout__ and iceWorking:
                            self.__UpdateIcecastNP__(
                                self.__IcecastServer__, oof
                            )
                        self.__playback__ = True
                        segIndex = 0
                        for segment in segments:
                            currentSegment = (
                                segment[1]
                                .set_frame_rate(self.__samplerate__)
                                .set_channels(
                                    self.__config__["PlayoutManager"][
                                        "Channels"
                                    ]
                                )
                            )
                            if not currentSegment == AudioSegment.empty():
                                utilities.autoPrint(
                                    text=f"SENDING: {segment[0]}",
                                    classType="PLAYOUT",
                                    sev=severity.playoutStats,
                                )
                                data = make_chunks(currentSegment, 500)
                                for chunk in data:
                                    if self.__icecastPlayout__ and iceWorking:
                                        self.__icePlayer__.stdin.write(
                                            chunk.raw_data
                                        )
                                    if not self.__playback__:
                                        if not overrideFile:
                                            utilities.autoPrint(
                                                text="Aborting EAS Alert...",
                                                classType="PLAYOUT",
                                                sev=severity.info,
                                            )
                                            EOM = (
                                                EASGen.genEOM(
                                                    mode=self.__config__[
                                                        "Emulation"
                                                    ]
                                                )
                                                .set_frame_rate(
                                                    self.__samplerate__
                                                )
                                                .set_channels(
                                                    self.__config__[
                                                        "PlayoutManager"
                                                    ]["Channels"]
                                                )
                                                .raw_data
                                            )
                                            if (
                                                self.__icecastPlayout__
                                                and iceWorking
                                            ):
                                                self.__icePlayer__.stdin.write(
                                                    EOM
                                                )
                                        else:
                                            utilities.autoPrint(
                                                text="Aborting Override File Playback...",
                                                classType="PLAYOUT",
                                                sev=severity.info,
                                            )
                                        break
                            segIndex += 1
                        self.__playback__ = False
                        utilities.autoPrint(
                            text="Finished Playout.",
                            classType="PLAYOUT",
                            sev=severity.debug,
                        )
                        if self.__icecastPlayout__ and iceWorking:
                            self.__UpdateIcecastNP__(
                                self.__IcecastServer__, self.__nowPlaying__
                            )
                        self.__alertAvailable__ = False
                except Exception as E:
                    utilities.autoPrint(
                        text=f"AL {type(E).__name__}, {E}",
                        classType="PLAYOUT",
                        sev=severity.error,
                    )
                    tb = E.__traceback__
                    while tb is not None:
                        utilities.autoPrint(
                            text=f"File: {tb.tb_frame.f_code.co_filename}\nFunc: {tb.tb_frame.f_code.co_name}\nLine: {tb.tb_lineno}",
                            classType="PLAYOUT",
                            sev=severity.error,
                        )
                        tb = tb.tb_next
                    self.__alertAvailable__ = False
                    if self.__icecastPlayout__ and iceWorking:
                        self.__UpdateIcecastNP__(
                            self.__IcecastServer__, self.__nowPlaying__
                        )
                self.__alertSent__ = True


def main(configFile):
    utilities.autoPrint("Begin BOOT Sequence...")
    try:
        Endec = AS_MAN(configFile=configFile)
        utilities.autoPrint(
            f"Station {AS_MAN.__callsign__.strip()} Started.",
            sev=severity.menu,
        )
        utilities.autoPrint(
            "====================================\n",
            sev=severity.boot,
        )
        while True:
            sleep(3600)
    except KeyboardInterrupt:
        AS_MAN.killAsmara()
        exit(0)


def boot():
    parser = ArgumentParser(description="MissingTextures Software ASMARA)")
    parser.add_argument(
        "configFile",
        nargs="?",
        default=".config",
        type=str,
        help="ASMARA Config File",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {AS_MAN.version}",
        help="Print version info and exit",
    )
    parser.add_argument(
        "-A",
        "--about",
        action="store_true",
        help="Print version info and exit",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-v",
        "--verbose",
        dest="log_level",
        action="count",
        help="Set verbosity (more 'v's mean higher verbosity, highest `-vvvvv`, default `-vv`)",
    )
    group.add_argument(
        "-d",
        "--debug",
        dest="log_level",
        action="store_const",
        const=10,
        help="Debug Mode (Prints everything)",
    )
    group.add_argument(
        "-q",
        "--quiet",
        dest="log_level",
        action="store_const",
        const=-1,
        help="Silent, Do not print anything except Menus.",
    )
    args = parser.parse_args()
    if args.about:
        utilities.cls()
        title = """    __  ___                ______     __               _____       ______                         
   /  |/  /________  ____ /_  __/  __/ /___________   / ___/____  / __/ /__      ______ _________ 
  / /|_/ / ___/ __ \/ __ `// / | |/_/ __/ ___/ ___/   \__ \/ __ \/ /_/ __/ | /| / / __ `/ ___/ _ \
 / /  / (__  ) / / / /_/ // / _>  </ /_/ /  (__  )   ___/ / /_/ / __/ /_ | |/ |/ / /_/ / /  /  __/
/_/  /_/____/_/ /_/\__, //_/ /_/|_|\__/_/  /____/   /____/\____/_/  \__/ |__/|__/\__,_/_/   \___/ 
    ___     _____ /____/___  ___      ____    ___                                                 
   /   |   / ___/  /  |/  / /   |    / __ \  /   |                                                
  / /| |   \__ \  / /|_/ / / /| |   / /_/ / / /| |                                                
 / ___ |_ ___/ / / /  / / / ___ |_ / _, _/ / ___ |                                                
/_/  |_(_)____(_)_/  /_(_)_/  |_(_)_/ |_(_)_/  |_|                                                
                                                                                                  """
        print(
            f"{title}\nMissingTextures Software AS_MAN.version {AS_MAN.version}\nAutomated System for Monitoring and Automatically Relaying Alerts\n\nCopyright (c) 2024 MissingTextures Software\n\nDeveloped by Anastasia M and Skylar G.\n\nThanks to FFMPEG and SAMEDEC for making good products!\n\n\nIn loving memory of Ash.\nWe never met, but I hope you would have at least liked the crazy in here. - Ana"
        )
        exit(0)
    if not args.log_level:
        args.log_level = 2
    utilities.setVerbosity(args.log_level)
    try:
        while True:
            utilities.cls()
            utilities.autoPrint(
                f"MISSINGTEXTURES SOFTWARE ASMARA {AS_MAN.version}\n====================================",
                sev=severity.boot,
            )
            utilities.autoPrint(f"OS: {utilities.getOS()}", sev=severity.debug)
            utilities.autoPrint("*** STARTING UP ***", sev=severity.boot)
            main(args.configFile)
            utilities.autoPrint("Restarting ASMARA...", sev=severity.boot)
    except KeyboardInterrupt:
        AS_MAN.killAsmara()
        return None


if __name__ == "__main__":
    current_thread().name = "MAIN"
    boot()
