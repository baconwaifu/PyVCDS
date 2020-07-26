import kwp
import can
import vag-block

modules = {
0x1: "Engine",
0x2: "Transmission",
0x3: "ABS",
0x5: "Security Access",
0x6: "Passenger Seat",
0x7: "Front Infotainment"
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
    for mod in modules.keys:
      try:
        stack.connect(mod).close()
        self.enabled.append(mod)
      except queue.Empty:
        pass #squash the exception; just means "module not detected"

if __name__ == "__main__":
  sock = can.interface.Bus(channel='vcan0', bustype='socketcan')
  stack = vwtp.VWTPStack(sock)

  conn = stack.connect(modules["ECU"])
  kw = kwp.KWPSession(conn)
  with conn:
    assert kw.request("startDiagnosticSession", 0x89) == b'\x50\x89' #positive response, same value.
    print(vag-block.parseBlock(kw.request("readDataByLocalIdentifier", 0x14)))
  kw.close()
  import sys; sys.exit(0) #need to do this because of threads.
