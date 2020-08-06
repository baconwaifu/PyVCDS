import kwp
import can
import vwtp
import queue
import vcds_label #VCDS label file parsing is split off.
import util
import label

labels = LazyLabel(

try:
  workshop = util.config["vw"]["workshop"] #workshop code. assigned by VW to licensed workshops.
except KeyError:
  workshop = None

def saveLabelsToJSON(fname):
  global labels
  import json, io
  fd = open(fname, "w")
  fd.write(json.dumps(labels, indent=4))
  fd.close()

def loadLabelsFromJSON(js): #we store our labels in JSON. larger, but easier to load than VCDS.
  global labels
  import json
  labels = json.loads(js)

class blockMeasure:
  def __init__(self, name, func):
    self.func = func
    self.name = name
    self.label = None
  def unscale(self, a, b):
    ret = blockMeasure(self.name, None)
    try:
      ret.value = self.func(a,b)
    except DivideByZeroError:
      ret.value = None #scaler fucked up, but we don't want to crash...
    return ret
  def __str__(self):
    if self.label:
      return "{} {} {}".format(self.value, self.name, self.label)
    else:
      return "{} {}".format(self.value, self.name)
  def __repr__(self):
    return self.__str__()

scalers = {
0x1: blockMeasure("/min", lambda a,b: (a*b)/5),
0x4: blockMeasure("°ATDC", lambda a,b: (b-127)*.01*a), #BTDC is expressed as a negative number.
0x7: blockMeasure("km/h", lambda a,b: .01*a*b),
0x8: blockMeasure("binary", lambda a,b: (a << 8) | b),
0x10: blockMeasure("binary", lambda a,b: (a << 8) | b),
0x11: blockMeasure("ASCII", lambda a,b: bytes([a,b]).decode("ascii")),
0x12: blockMeasure("mbar", lambda a,b: (a*b)*25),
0x14: blockMeasure("%", lambda a,b: ((a*b)/128)-1),
0x15: blockMeasure("V", lambda a,b: (a*b)/1000),
0x16: blockMeasure("ms", lambda a,b: .001*a*b),
0x17: blockMeasure("%", lambda a,b: (b*a)/256),
0x19: blockMeasure("g/s (air)", lambda a,b: (100/a)*b),
0x1A: blockMeasure("°C", lambda a,b: b-a),
0x21: blockMeasure("%", lambda a,b: b*100 if a == 0 else (b*100)/a), #same unit, different scaling.
0x22: blockMeasure("kW", lambda a,b: (b - 128)*.01*a),
0x23: blockMeasure("/h", lambda a,b: (a*b)/100),
0x25: blockMeasure("binary", lambda a,b: (a << 8) | b),
0x27: blockMeasure("mg/stroke (fuel)", lambda a,b: (a*b)/256),
0x31: blockMeasure("mg/stroke (air)", lambda a,b: (a*b)/40),
0x33: blockMeasure("mg/stroke (Δ)", lambda a,b: ((b-128)/255)*a),
0x36: blockMeasure("Count", lambda a,b: (a*256)+b),
0x37: blockMeasure("seconds", lambda a,b: (a*b)/200),
0x51: blockMeasure("°CF", lambda a,b: ((a*11200)+(b*436))/1000), #torsion; check formula.
0x5E: blockMeasure("Nm", lambda a,b: a*((b/50)-1)), #torque; check formula.
0x100: blockMeasure("[Unknown Unit]", lambda a,b: (a << 8) | b)
}


def parseBlock(block, mod=None): #takes a raw KWP response.
  blk = []
  buf = block[2:]
  for i in range(0, 3*4, 3):
    if buf[i] in scalers:
      blk.append(scalers[buf[i]].unscale(buf[i+1], buf[i+2]))
    else:
      blk.append(scalers[256].unscale(buf[i+1], buf[i+2]))
  if mod:
    try:
      for i in range(4)
      blk[i].label = labels[mod.pn][i]
    except KeyError:
      pass
  return blk

def labelBlock(ecu, blknum, blk):
  for i in range(len(blk)):
    blk.label = labels[(ecu,blknum)][i]

modules = {
0x1: "Engine",
0x2: "Automatic Transmission",
0x3: "ABS",
0x4: "Steering",
0x5: "Security Access",
0x6: "Passenger Seat",
0x7: "Front Infotainment",
0x8: "Climate Control",
0x9: "Central Electronics",
0xE: "Media Player 1",
0xF: "Satillite Radio",
0x10: "Parking Aid #2",
0x11: "Engine #2",
0x13: "Distance Regulation",
0x14: "Suspension",
0x15: "Airbags", #no, not *that* kind of airbag. pervert.
0x16: "Steering",
0x17: "Instrument Cluster",
0x18: "Aux Heater", #block heater for diesels?
0x19: "CAN Gateway", #what you're probably talking to with this!
0x1B: "Active Steering",
0x1F: "Identity Controller (?)", #no clue what this is, but the simulator emulates it.
0x20: "High Beam Assist",
0x22: "AWD",
0x25: "Immobilizer", #for the car. not you.
0x26: "Convertible Top", #again, *for the car*.
0x29: "Left Headlight",
0x31: "Diagnostic Interface", #again, what you're probably talking to.
0x34: "Level Control",
0x35: "Central Locking", #fun fact: the car knows if a lock is missing!
0x36: "Driver Seat",
0x37: "Radio/SatNav",
0x39: "Right Headlight", #this only has a hamming distance of 1 from the left headlight; probably AND-based CAN bus masking and code re-use...
0x42: "Driver Door",
0x44: "Steering Assist",
0x45: "Interior Monitoring", #what the hell is this?
0x46: "Comfort System", #no, not *that* kind of "comfort" ya pervert.
0x47: "Sound System", #what idiots/assholes modifiy to illegally loud levels!
0x52: "Passenger Door", #again, hamming distance of 1 from driver door.
0x53: "Parking Brake", #oh hey, that thing that makes it impossible to change the rear pads without a diag tool!
0x55: "Headlights", #why is this separate from the individual headlights?
0x56: "Radio",
0x57: "TV Tuner", #what. why does a car need an OTA TV tuner?
0x61: "Battery",
0x68: "Rear Left Door",
0x65: "TPMS",
0x67: "Voice Control", #so they have jarvis now?
0x68: "Wipers",
0x69: "Trailer Recognition",
0x72: "Rear Right Door",
0x75: "Telematics", #"hey, where'd my car go?"
0x76: "Parking Aid", #Better than a tennis ball on a string!
0x77: "CarPhone", #yes, some cars do have a built in cellular phone, and yes, they were made post-smartphone.
}

class VWModule:
  def __init__(self, kwp, mod):
    self.idx = mod
    self.name = modules[mod]
    self.pn = None
    self.kwp = kwp

  def readID(self):
    ret = {}
    blk = self.readBlock(81)
    util.log(4,"ID structure parsing not implemented yet; raw message:",blk)
    return NotImplemented

  def readManufactureInfo(self):
    ret = {}
    blk = self.readBlock(80)
    util.log(4,"Manufacture info structure parsing not implemented yet; raw message:",blk)
    return NotImplemented

  def readFWVersion(self):
    ret = {}
    blk = self.readBlock(82)
    util.log(4,"FW version structure parsing not implemented yet; raw message:",blk)
    return NotImplemented

  def getDTC(self): #note: this returns a *different format* to the one below.
    dtcs = {}
    for i in range(256):
      req = None #hoist the scope...
      try:
        req = self.kwp.request("readDiagnosticTroubleCodes", bytes([i]))
        count = req[1]
        dtcs[i] = []
        if count > 0:
          for ii in range(0,count*2,2):
            dtc = req[ii+2:ii+4]
            dtcs[i].append(dtc)
      except kwp.EPERM:
        util.log(3,"Got permission denied reading DTC group '{}'?".format(hex(i)))
      except kwp.KWPException:
        pass #just means invalid group or something
    return dtcs

  def readDTC(self):
    #TODO: VWs appear to use 1-byte group numbers, so it should only take a few minutes to enumerate all groups for a given module
    #unfortunately, a stock car's module outfit is extremely limited without being able to re-code the gateway.
    try: #this mimics the zurich's request pattern for DTCs by "tripped" status.
      req = self.kwp.request("readDiagnosticTroubleCodesByStatus", b"\x02\xff\x00") #status 02FF, group 00; seems to work on transmission
    except kwp.KWPException:
      req = self.kwp.request("readDiagnosticTroubleCodesByStatus", b"\x00\xff\x00") #status 00FF, group 00; works on engine, may work on others?
    dtcs = []
    count = req[1]
    if count > 0:
      for i in range(0,count*2,2):
        dtc = req[i+2:i+4]
        dtcs.append(dtc)
    return dtcs

  def readBlock(self, blk):
    if not self.pn:
      self.readID()
    return parseBlock(self.kwp.request("getDataByLocalIdentifier", blk), self)
  
  def readLongCode(self,code):
    raise NotImplementedError("Need VCDS Trace to figure out KWP commands")

  def setLongCode(self,code, buf):
    raise NotImplementedError("Need VCDS Trace to figure out KWP commands")
    #note: this should *never* be moved to the log function; this is a user safety interface.
    print("WARNING: This function presents a *VERY REAL CHANCE* of PERMANENTLY BRICKING the selected module. Continue?")
    resp = input("(y/N)> ")
    if resp == "y" or resp == "Y":
      print("Are you *REALLY* sure? there's no going back after this point.")
      resp = input("(y/N)> ")
      if resp == "y" or resp == "Y":
        print("Uploading... Do not turn the vehicle off or remove the adapter")
        kwp.request("InvalidRequestQWERTYU", code, buf) #FIXME: what's the right request?
        print("Done.")
      else:
        print("Aborted.")   
        return
    else:
      print("Aborted.")
      return


  def __enter__(self): #nothing to do outside of __init__, but we need it here anyways.
    return self
  def __exit__(self,a,b,c):
    self.kwp.__exit__(a,b,c)

class VWVehicle:
  def __init__(self, stack):
    self.stack = stack;
    self.enabled = []
    self.scanned = False

  def enum(self): #a crude enumeration primitive of all *known* ECUs
    global modules
    if self.scanned:
      return
    self.scanned = True
    util.log(5,"Enumerating Modules...")
    for mod in modules.keys():
      try:
        self.stack.connect(mod).close()
        util.log(5,"Found module:",modules[mod])
        self.enabled.append(mod)
      except (queue.Empty,ValueError):
        pass #squash the exception; just means "module not detected"

  def module(self, mod):
    return VWModule(kwp.KWPSession(self.stack.connect(mod)), mod)

  def __enter__(self):
    return self
  def __exit__(self,a,b,c):
    pass #we don't do any direct cleanup

if __name__ == "__main__":
  import json,jsonpickle
  sock = can.interface.Bus(channel='can0', bustype='socketcan')
  stack = vwtp.VWTPStack(sock)

  car = VWVehicle(stack)
  print("Connecting to vehicle and enumerating modules, please wait a moment.")
#  car.enum()
  print("Modules present:")
  for k in car.enabled:
    print(" ",modules[k])

  conn = stack.connect(0x01)
  kw = kwp.KWPSession(conn)
  with conn:
    kw.begin(0x89)
    blks = {"open": {}, "locked":[]}
    codes = {"open": {}, "locked": []}
    for i in range(1,256):
     print(i)
     try:
#      blk = parseBlock(kw.request("readDataByLocalIdentifier", i))
#      blks["open"][i] = blk
      pass
     except kwp.EPERM:
      blks["locked"].append(hex(i))
     except (ValueError, kwp.ETIME, kwp.KWPException):
      pass
     try:
      blk = kw.request("readDataByCommonIdentifier", i)
      codes["open"][i] = blk
     except kwp.EPERM:
      codes["locked"].append(hex(i))
     except ValueError:
      conn = stack.connect(0x01)
      kw = kwp.KWPSession(conn)
      kw.begin(0x89)
     except kwp.KWPException as e:
      print(e)
    fd = open("blks.json", "w")
    fd.write(json.dumps(json.loads(jsonpickle.dumps({"blocks": blks, "codes": codes})), indent=4))
    fd.close()
  kw.close()
  import sys; sys.exit(0) #need to do this because of threads.
