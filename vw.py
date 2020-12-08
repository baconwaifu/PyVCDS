import queue
import time

import can

import kwp
import label
# import vcds_label #VCDS label file parsing is split off.
import util
import vwtp


# Going off of vag-diag-sim, startRoutineByLocalIdentifier has something relating to measuring blocks with argument 0xb8.
# it's set to return b'q\xb8\x01\x01\x01\x03\x01\x02\x01\x06\x01\x07\x01\x08\x01\r\x01\x18' when called.

class LabelStorage:
    def __init__(self, path, tree):
        self.backing = tree

    def flush(self):
        with open(self.path, "w") as fd:
            fd.write(json.dumps(self.backing))

    def __getitem__(self, idx):
        self.backing.__getitem__(idx)

    def __setitem__(self, idx, val):
        self.backing.__setitem(idx, val)

    def __contains__(self, idx):
        return self.backing.__contains__(idx)

    def setpath(self, path):
        label.BASEDIR = path  # set the base search directory.


# the LabelStorage object we use for looking up VW labels; functions as a cache for
# reading ross-tech labels as well. if the label path is initialized, it will attempt
# to find and load the appropriate label file from the ross-tech label directory.
labels = LabelStorage("~/.pyvcds/labels/labels.json", label.LazyLabel())

try:
    workshop = util.config["vw"]["workshop"]  # workshop code. assigned by VW to licensed workshops.
except KeyError:
    workshop = None


def saveLabelsToJSON(fname):
    global labels
    import json
    fd = open(fname, "w")
    fd.write(json.dumps(labels, indent=4))
    fd.close()


def loadLabelsFromJSON(js):  # we store our labels in JSON. larger, but easier to load than VCDS.
    global labels
    import json
    labels = json.loads(js)


class blockMeasure:
    def __init__(self, name, func, sz=3):
        self.func = func
        self.name = name
        self.label = None
        self.size = sz  # just a flag for "variably sized result"

    def unscale(self, a, b):
        ret = blockMeasure(self.name, None)
        try:
            ret.value = self.func(a, b)
        except ZeroDivisionError:
            ret.value = None  # scaler fucked up, but we don't want to crash...
        return ret

    def __str__(self):
        if self.label:
            return "{} {} {}".format(self.value, self.name, self.label)
        else:
            return "{} {}".format(self.value, self.name)

    def __repr__(self):
        return self.__str__()


scalers = {
    0x1: blockMeasure("/min", lambda a, b: (a * b) / 5),
    0x2: blockMeasure("%", lambda a, b: (a * 0.002) * b),
    0x4: blockMeasure("°ATDC", lambda a, b: (b - 127) * .01 * a),  # BTDC is expressed as a negative number.
    0x7: blockMeasure("km/h", lambda a, b: .01 * a * b),
    0x8: blockMeasure("binary (0x8)", lambda a, b: hex((a << 8) | b)[2:]),
    # flag bits? has been correllated with cruse control for 1218
    0x10: blockMeasure("binary (0x10)", lambda a, b: hex((a << 8) | b)[2:]),
    # KWP1218 has this as a bool for "engine cold" (0 == cold)
    0x11: blockMeasure("ASCII", lambda a, b: bytes([a, b]).decode("ascii")),
    0x12: blockMeasure("mbar", lambda a, b: (a * b) * 25),
    0x14: blockMeasure("%", lambda a, b: ((a * b) / 128) - 1),
    0x15: blockMeasure("V", lambda a, b: (a * b) / 1000),
    0x16: blockMeasure("ms", lambda a, b: .001 * a * b),
    0x17: blockMeasure("%", lambda a, b: (b * a) / 256),
    0x18: blockMeasure("Amps", lambda a, b: (0.001 * a) * b),  # KWP1218; may be incorrect for 2k
    0x19: blockMeasure("g/s (air)", lambda a, b: (100 / a) * b),
    # 1218 has this as '(b*1.421)+(a/182)' which *approximately* evaluates to a standard little endian short
    0x1A: blockMeasure("°C", lambda a, b: b - a),
    0x21: blockMeasure("%", lambda a, b: b * 100 if a == 0 else (b * 100) / a),  # same unit, different scaling.
    0x22: blockMeasure("kW", lambda a, b: (b - 128) * .01 * a),
    0x23: blockMeasure("/h", lambda a, b: (a * b) / 100),
    0x24: blockMeasure("km", lambda a, b: (a * 2560) + (b * 10)),  # from KWP 1218
    0x25: blockMeasure("binary (0x25)", lambda a, b: hex((a << 8) | b)[2:]),  # coding?
    0x27: blockMeasure("mg/stroke (fuel)", lambda a, b: (a * b) / 256),
    0x31: blockMeasure("mg/stroke (air)", lambda a, b: (a * b) / 40),
    0x33: blockMeasure("mg/stroke (Δ)", lambda a, b: ((b - 128) / 255) * a),
    0x36: blockMeasure("Count", lambda a, b: (a * 256) + b),
    0x37: blockMeasure("seconds", lambda a, b: (a * b) / 200),
    0x51: blockMeasure("°CF", lambda a, b: ((a * 11200) + (b * 436)) / 1000),  # torsion; check formula.
    0x5E: blockMeasure("Nm", lambda a, b: a * ((b / 50) - 1)),  # torque; check formula.
    0x5F: blockMeasure("", lambda a, b: a[1:a[0] + 1].decode("ascii"), 4),
    # ASCII String, variable length, so A is a bytes() of the whole thing.
    0x100: blockMeasure("[Unknown Unit]", lambda a, b: (a << 8) | b)
}


def parseBlock(block, mod=None):  # takes a raw KWP response.
    blk = []
    buf = block[2:]  # drop the KWP op and param
    idx = 0
    try:
        for i in range(4):
            if buf[idx] in scalers:
                if scalers[buf[idx]].size <= 3:
                    blk.append(scalers[buf[idx]].unscale(buf[idx + 1], buf[idx + 2]))
                    idx += 3
                else:
                    # print(repr(buf))
                    var = scalers[buf[idx]].unscale(buf[idx + 1:], None)
                    # print(var)
                    blk.append(var)
                    idx += len(blk[-1].value)
            else:
                blk.append(scalers[256].unscale(buf[i + 1], buf[i + 2]))
    except IndexError:
        pass  # stomp on indexerrors, measuring blocks can be *up to* 4 fields long; some are "8" (need a firmware dump to investigate that...)
    if mod:  # don't look up block labels if we just want a basic parse.
        try:
            for i in range(4):
                blk[i].label = labels[mod.pn][i]
        except KeyError:
            pass
    return blk


def labelBlock(ecu, blknum, blk):
    for i in range(len(blk)):
        blk.label = labels[(ecu, blknum)][i]


# Note: ross-tech IDs seem to diverge from components on CAN-bus vehicles.
# all commented-out components are potentially divergent ross-tech IDs.
modules = {
    0x1: "Engine",
    0x2: "Automatic Transmission",
    0x3: "ABS",
    # 0x4: "Steering",
    # 0x5: "Security Access",
    0x5: "Airbags",
    # 0x6: "Passenger Seat",
    # 0x7: "Front Infotainment",
    # 0x8: "Climate Control",
    # 0x9: "Central Electronics",
    0x9: "Power Steering",
    # 0xE: "Media Player 1",
    # 0xF: "Satillite Radio",
    # 0x10: "Parking Aid #2",
    # 0x11: "Engine #2",
    # 0x13: "Distance Regulation",
    # 0x14: "Suspension",
    # 0x15: "Airbags", #no, not *that* kind of airbag. pervert.
    # 0x16: "Steering",
    # 0x17: "Instrument Cluster",
    # 0x18: "Aux Heater", #block heater for diesels?
    # 0x19: "CAN Gateway", #what you're probably talking to with this!
    0x19: "Parking Brake",
    # 0x1B: "Active Steering",
    # 0x1F: "Identity Controller (?)", #no clue what this is, but the simulator emulates it.
    0x1f: "CAN Gateway",
    # 0x20: "High Beam Assist",
    # 0x22: "AWD",
    # 0x25: "Immobilizer", #for the car. not you.
    # 0x26: "Convertible Top", #again, *for the car*.
    # 0x29: "Left Headlight",
    # 0x31: "Diagnostic Interface", #again, what you're probably talking to.
    # 0x34: "Level Control",
    # 0x35: "Central Locking", #fun fact: the car knows if a lock is missing!
    # 0x36: "Driver Seat",
    # 0x37: "Radio/SatNav",
    # 0x39: "Right Headlight", #this only has a hamming distance of 1 from the left headlight; probably AND-based CAN bus masking and code re-use...
    # 0x42: "Driver Door",
    # 0x44: "Steering Assist",
    # 0x45: "Interior Monitoring", #what the hell is this?
    # 0x46: "Comfort System", #no, not *that* kind of "comfort" ya pervert.
    # 0x47: "Sound System", #what idiots/assholes modifiy to illegally loud levels!
    0x4f: "Sirius Satellite Radio",
    # 0x52: "Passenger Door", #again, hamming distance of 1 from driver door.
    0x52: "Radio Head Unit"
    # 0x53: "Parking Brake", #oh hey, that thing that makes it impossible to change the rear pads without a diag tool!
    # 0x55: "Headlights", #why is this separate from the individual headlights?
    # 0x56: "Radio",
    # 0x57: "TV Tuner", #what. why does a car need an OTA TV tuner?
    # 0x61: "Battery",
    # 0x68: "Rear Left Door",
    # 0x65: "TPMS",
    # 0x67: "Voice Control", #so they have jarvis now?
    # 0x68: "Wipers",
    # 0x69: "Trailer Recognition",
    # 0x72: "Rear Right Door",
    # 0x75: "Telematics", #"hey, where'd my car go?"
    # 0x76: "Parking Aid", #Better than a tennis ball on a string!
    # 0x77: "CarPhone", #yes, some cars do have a built in cellular phone, and yes, they were made post-smartphone.
}


class VWModule:
    def __init__(self, kwp, mod, exc=False):
        self.idx = mod
        if mod in modules:
            self.name = modules[mod]
        else:
            self.name = None
        self.pn = None
        self._name = None
        self.kwp = kwp
        self.exclusive = exc  # is our KWP session exclusive to us?

    def __str__(self):
        if not self.pn:
            self.readPN()
        return "{}: \"{}\"".format(self.pn, self._name)

    def readID(self):
        self.pn = True
        ret = {}
        blk = self.readBlock(81)
        util.log(4, "ID structure parsing not implemented yet; raw message:", blk)
        util.log(4, "ParseBlock output:", parseBlock(blk))
        return NotImplemented

    def readPN(self):
        # DaimlerChrysler uses 0x86 or 0x87 to get ECU ID, 0x88 to get the (manufactured) VIN (0x90 to get the "current" VIN)
        # VW uses the latter two for that as well. but on VWs, 0x86 is manufacture info, and 0x87 is firmware version (I think?)
        # We first try to retrieve the full identification
        try:
            util.log(6, "Reading ECU identification...")
            req = self.kwp.request("readEcuIdentification", 0x9B)  # Read Part Identification
            pn = req[2:14]
            self._name = req[0x1c:].decode("ascii").rstrip()
        except kwp.KWPException:
            util.log(5, "Fault retrieving full ID block, falling back to plain part number!")
            req = self.kwp.request("readEcuIdentification", 0x91)  # Read raw VAG number (ECU ID)
            l = req[2]
            pn = req[3:2 + l]  # length byte includes itself...
            self._name = "<Unknown, could not retreive name>"

        buf = bytearray()  # expanding the part number is the same for both paths.
        buf += pn[0:3]
        buf += b'-'
        buf += pn[3:6]
        buf += b'-'
        buf += pn[6:9]
        if len(buf) > 9:  # suffix is optional
            buf += b'-'
            buf += pn[9:]
        self.pn = bytes(buf).decode("ascii").strip()  # full ID block's PN has trailing spaces, so drop those.

    def readManufactureInfo(self):
        ret = {}
        blk = self.readBlock(80)
        util.log(4, "Manufacture info structure parsing not implemented yet; raw message:", blk)
        return NotImplemented

    def readFWVersion(self):
        ret = {}
        blk = self.readBlock(82)
        util.log(4, "FW version structure parsing not implemented yet; raw message:", blk)
        return NotImplemented

    def readFW(self):
        import _vw.flash as flash
        with flash.VWECUFlashInterface(self.kwp, 'r') as flsh:
            with open('fw.bin', 'wb') as ofd:
                ofd.write(flsh.read(0x200000))  # 2MB.

    def getDTC(self):  # note: this returns a *different format* to the one below.
        dtcs = {}
        for i in range(256):
            req = None  # hoist the scope...
            try:
                req = self.kwp.request("readDiagnosticTroubleCodes", bytes([i]))
                count = req[1]
                dtcs[i] = []
                if count > 0:
                    for ii in range(0, count * 2, 2):
                        dtc = req[ii + 2:ii + 4]
                        dtcs[i].append(dtc)
            except kwp.EPERM:
                util.log(3, "Got permission denied reading DTC group '{}'?".format(hex(i)))
            except kwp.KWPException:
                pass  # just means invalid group or something
        return dtcs

    def readDTC(self):
        # Groups are based on bitmask. 0xFF00 is "all groups" 0x00-3F is powertrain, 0x40-7F is chassis, 0x80-BF is body, and 0xC0-FE is network.
        # those are for DaimlerChrysler, but are likely standardized.
        # Status 1 and 3 are "supported DTCs", 4 is "most recent" and 0xE0 is "256+ supported DTCs" (for DaimlerChysler); returns a 2-byte count in response (big-endian)
        # the usual "get by status" is repeated N/256 times to get all DTCs.
        # actual status is the highest 3 bits of the status byte, being "indicated" "active" and "stored" in that order. the next bit is "readiness"
        try:
            try:  # this mimics the zurich scanner's request pattern for DTCs by "tripped" status.
                req = self.kwp.request("readDiagnosticTroubleCodesByStatus",
                                       b"\x02\xff\x00")  # status 02, group FF00; "All Tripped Hex DTCs"
            except kwp.EINVAL:
                req = self.kwp.request("readDiagnosticTroubleCodesByStatus",
                                       b"\x00\xff\x00")  # status 00, group FF00; "All Tripped J2012 format DTCs"
        except (kwp.serviceNotSupportedException, kwp.ENOENT):
            return []  # no DTCs to report...
        dtcs = []
        count = req[1]
        if count > 0:
            for i in range(0, count * 2, 2):
                dtc = req[i + 2:i + 4]
                dtcs.append(dtc)
        return dtcs

    def measureBlock(self, blk):
        if not self.pn:
            self.readPN()
        return parseBlock(self.readBlock(blk), self)

    def readBlock(self, blk):
        return self.kwp.request("readDataByLocalIdentifier", blk)

    def readLongCode(self, code):
        raise NotImplementedError("Need VCDS Trace to figure out KWP commands")

    def setLongCode(self, code, buf):
        raise NotImplementedError("Need VCDS Trace to figure out KWP commands")
        # note: this should *never* be moved to the log function; this is a user safety interface.
        print("WARNING: This function presents a *VERY REAL CHANCE* of "
              "PERMANENTLY BRICKING the selected module. Continue?")
        resp = input("(y/N)> ")
        if resp == "y" or resp == "Y":
            print("Are you *REALLY* sure? there's no going back after this point.")
            resp = input("(y/N)> ")
            if resp == "y" or resp == "Y":
                print("Uploading... Do not turn the vehicle off or remove the adapter")
                kwp.request("InvalidRequestQWERTYU", code, buf)  # FIXME: what's the right request?
                print("Done.")
            else:
                print("Aborted.")
                return
        else:
            print("Aborted.")
            return

    def close(self):
        if self.exclusive:  # if we have the only reference to the KWP session, close it.
            self.kwp.close()

    def __enter__(self):  # nothing to do outside of __init__, but we need it here anyways.
        return self

    def __exit__(self, a, b, c):
        self.close()


class VWVehicle:
    def __init__(self, stack):
        self.stack = stack;
        self.enabled = []
        self.parts = {}
        self.scanned = False

    # note: everything that calls this *must* check if already scanned.
    # this doesn't, to allow for manual rescan.
    def enum(self):  # a crude enumeration primitive of all *known* ECUs
        global modules
        self.scanned = True
        util.log(5, "Enumerating Modules...")
        for mod in modules.keys():
            for i in range(3):  # try 3 times for each module
                try:
                    util.log(5, "Trying Module '{}', Try {}".format(modules[mod], i))
                    m = self.module(mod)
                    m.readPN()
                    util.log(5, "Found module:", modules[mod], "Part Number:", m.pn)
                    m.close()
                    self.enabled.append(mod)
                    self.parts[mod] = modules[mod] + " -> " + m.pn
                    break
                except (vwtp.ETIME) as e:
                    if i == 3:  # if it's the last go-round, *then* we log it as "not found"
                        util.log(5, "Module not found:",
                                 repr(e))  # squash the exception; just means "module not detected"
                except (kwp.KWPException) as e:  # we connected, but something fucked up.
                    util.log(3, "Communication Fault reading from module, but assuming it's present:", modules[mod])
                    util.log(3, "Exception:", e)
                    self.enabled.append(mod)
                    break
                time.sleep(.2)

    def module(self, mod):
        # note: the "exc" flag in the KWP session means "exclusively owned transport socket, close it when you're closed"
        k = kwp.KWPSession(self.stack.connect(mod), exc=True)
        k.begin(0x89)  # 0x89 is diag, 0x85 is PROG.
        return VWModule(k, mod)

    def __enter__(self):
        return self

    def __exit__(self, a, b, c):
        pass  # we don't do any direct cleanup


def brutemap(stack, ecu, req, r):
    while True:  # simply spinlock waiting for ECU to connect
        try:
            conn = stack.connect(ecu)
            break
        except (queue.Empty, ValueError):
            pass
    conn.reopen = False  # we do that ourselves.
    kw = kwp.KWPSession(conn)
    with conn, kw:
        kw.begin(0x89)
        blks = {"open": {}, "locked": []}
        for i in r:
            print(i)
            if not conn._open:  # re-open dropped connections.
                while True:
                    try:
                        conn = stack.connect(ecu)
                        conn.reopen = False
                        kw = kwp.KWPSession(conn)
                        kw.begin(0x89)
                        break
                    except queue.Empty:
                        pass
            try:
                blk = kw.request(req, i)
                blks["open"][i] = blk
                pass
            except kwp.EPERM:
                blks["locked"].append(hex(i))
            except (ValueError, kwp.ETIME, kwp.KWPException) as e:
                util.log(4, e)
                if type(
                        e) == kwp.serviceNotSupportedException:  # if the service isn't supported, don't bother mapping it. because it won't work.
                    return "serviceNotSupported"  # because we just punt the output into JSON, this works fine.
            time.sleep(.1)
        return blks


def modmap(car):
    mods = {}
    for i in range(1, 256):
        for ii in range(3):
            try:
                mod = car.module(i)
                with mod:
                    m = str(mod)
                    a = hex(i)[2:]
                    util.log(5, "Found module '{}' at address '{}'".format(m, a))
                    mods[a] = m  # get the part number and name.
                    break  # break the retry loop.
            except kwp.KWPException as e:  # fault reading part number; means module is there but fucked up.
                util.log(3, "Module Read Error: {}: {}".format(hex(i)[2:], e))
                break
            except (ValueError, queue.Empty):  # fault connecting to module
                util.log(5, "Module connect timeout:", hex(i)[2:])
            time.sleep(.5)  # give the gateway time to reset between timeouts
    return mods


if __name__ == "__main__":
    import json, jsonpickle

    sock = can.interface.Bus(channel='can0', bustype='socketcan')
    stack = vwtp.VWTPStack(sock)

    with VWVehicle(stack) as car:
        print("Connecting to vehicle and enumerating modules, please wait a moment.")
        car.enum()
        print("Modules present:")
        for k in car.enabled:
            print(" ", modules[k])

        util.log(4, "Enumerating Identifiers for all Modules...")
        mods = modmap(car)
        with open("mods.json", "w") as fd:
            fd.write(json.dumps(mods, indent=4))  # is all primitives, so jsonpickle is not needed here.

        for mod in car.enabled:
            util.log(4, "Probing Module Identifiers for '{}'".format(modules[mod]))
            m = {"readDataByLocalIdentifier": range(1, 256), "readEcuIdentification": range(1, 256),
                 "readDataByCommonIdentifier": range(1, 65535)}
            fault = None
            try:
                for k in m.keys():
                    m[k] = brutemap(stack, mod, k, m[k])
            except BaseException as e:  # simply used for cleanup.
                fault = e
            if not fault:
                with car.module(
                        mod) as m:  # TODO: add a "risky" mode that enumerates OEM-specific services (which may potentially set off airbags and such)
                    srv = {}
                    util.log(4, "Supported Services...")
                    for s, n in kwp.services.items():
                        if s <= 0x11:  # OBD-2, StartSession, and EcuReset. we don't want to poke those.
                            continue
                        try:
                            res = m.kwp.request(s)
                            srv[n] = res
                        except kwp.KWPException as e:
                            if type(e) == kwp.KWPServiceNotSupportedException:  # "expected" fault
                                continue
                            srv[n] = str(e)  # something's there, but something went to fuck.
            fd = open("map-{}.json".format(hex(3)[2:]), "w")
            fd.write(json.dumps(json.loads(jsonpickle.dumps(m)),
                                indent=4))  # jsonpickle allows serializing every type, but no pretty-printing. so we re-load it and re-dump it.
            fd.close()
    print("Done.")
    if fault:
        raise fault
    # import sys; sys.exit(0) #need to do this because of threads.
