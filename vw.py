import kwp
import can
import vwtp
import queue

class blockMeasure:
  def __init__(self, name, func):
    self.func = func
    self.name = name
    self.label = None
  def unscale(self, a, b):
    ret = blockMeasure(self.name, None)
    ret.value = self.func(a,b)
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


def parseBlock(block):
  blk = []
  buf = block[2:]
  for i in range(0, len(buf), 3):
    if buf[i] in scalers:
      blk.append(scalers[buf[i]].unscale(buf[i+1], buf[i+2]))
    else:
      blk.append(scalers[256].unscale(buf[i+1], buf[i+2]))
  return blk

def labelBlock(ecu, blknum, blk):
  for i in range(len(blk)):
    blk.label = labels[(ecu,blknum)][i]

modules = {
0x1: "Engine",
0x2: "Transmission",
0x3: "ABS",
0x5: "Security Access",
0x6: "Passenger Seat",
0x7: "Front Infotainment",
0x8: "Climate Control",
0x9: "Central Electronics",
0x10: "Parking Aid #2",
0x11: "Engine #2",
0x13: "Distance Regulation",
0x14: "Suspension",
0x15: "Airbags", #no, not *that* kind of airbag. pervert.
0x16: "Steering",
0x17: "Instrument Cluster",
0x18: "Aux Heater", #block heater for diesels?
0x19: "CAN Gateway", #what you're probably talking to with this!
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
0x77: "CarPhone" #yes, some cars do have a built in cellular phone, and yes, they were made post-smartphone.
}

class VWVehicle:
  def __init__(self, stack):
    self.stack = stack;
    self.enabled = []

  def enum(self): #a crude enumeration primitive of all *known* ECUs
    global modules
    for mod in modules.keys():
      try:
        stack.connect(mod).close()
        print("Found module:",modules[mod])
        self.enabled.append(mod)
      except queue.Empty:
        pass #squash the exception; just means "module not detected"

if __name__ == "__main__":
  sock = can.interface.Bus(channel='vcan0', bustype='socketcan')
  stack = vwtp.VWTPStack(sock)

  car = VWVehicle(stack)
  print("Connecting to vehicle and enumerating modules, please wait a moment.")
  car.enum()
  print("Modules present:")
  for k in car.enabled:
    print(" ",modules[k])

  conn = stack.connect(0x01)
  kw = kwp.KWPSession(conn)
  with conn:
    assert kw.request("startDiagnosticSession", 0x89) == b'\x50\x89' #positive response, same value.
    print(parseBlock(kw.request("readDataByLocalIdentifier", 2)))
  kw.close()
  import sys; sys.exit(0) #need to do this because of threads.
