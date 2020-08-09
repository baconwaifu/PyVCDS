#!/usr/bin/env python3

import can
import queue
import threading
import struct
import util

services = {

1: { #Current Data
0x1: "Monitor Status",
0x2: "Freeze DTC",
0x3: "Fuel System Status", #enum
0x4: "Calculated Engine Load", #N/2.55 == %
0x5: "Engine Coolant temp", # N-40 == C
0x6: "Short term fuel trim (Bank 1)", #(N/1.28) - 100
0x7: "Long term fuel trim (Bank 1)",
0x8: "Short term fuel trim (Bank 2)",
0x9: "Long term fuel trim (Bank 2)",
0xA: "Fuel Pressure", #3N
0xB: "Intake manifold abs. pressure", #N
0xC: "Engine RPM", # (256A + B)/4
0xD: "Vehicle Speed", # N == km/h
0xE: "Timing Advance",
0xF: "Intake air temp.",
0x10: "MAF flow rate", # (256A + B)/100 == grams/sec
0x11: "Throttle Position", #N/2.55 == %
0x12: "Commanded Secondary air status",
0x13: "Oxygen sensors present (2 banks)",
0x14: "Oxygen Sensor 1",
0x15: "Oxygen Sensor 2",
0x16: "Oxygen Sensor 3",
0x17: "Oxygen Sensor 4",
0x18: "Oxygen Sensor 5",
0x19: "Oxygen Sensor 6",
0x1A: "Oxygen Sensor 7",
0x1B: "Oxygen Sensor 8",
0x1C: "OBD Standards", #enum
0x1D: "Oxygen Sensors present (4 banks)",
0x1E: "Aux. input status (hybrids?)",
0x1F: "Run-time since engine start",
0x20: "Extended PIDs supported", #bitmask, much like 0.
0x21: "Distance with Check Engine", #256A + B
0x22: "Fuel Rail pressure (Manifold vac. relative)", #.079(256A+B)
0x23: "Fuel Rail Guage Pressure (diesel/gas direct injection)", #10(256A+B)
0x2C: "Commanded EGR", #Exhaust gas recycle, A/2.55 == %
0x2D: "EGR error", #1.28A - 100 == %
0x2E: "Commanded Evap Purge",
0x2F: "Fuel Tank Level Input",
0x30: "Warm-ups since codes cleared",
0x31: "Distance Traveled since codes cleared",
0x33: "Absolute Barometric Pressure",
0x40: "Extended PIDs Supported (0x40)", #bitmask
0x41: "Monitor status this start",
0x42: "Control Module Voltage",
0x43: "Absolute Load Value",
0x45: "Relative Throttle Position",
0x46: "Ambient Air Temperature",
0x4D: "Time run with MIL on",
0x4E: "Time since DTCs cleared",
0x51: "Fuel Type", #enum
0x52: "Ethanol Fuel %", #standard % scaling
0x5B: "Hybrid Battery Remaining Life",
0x5C: "Engine Oil Temperature",
0x5E: "Engine Fuel Rate", #(256A + B)/20 == L/h
0x5F: "Design Emissions Requirements",
0x60: "Extended PIDs supported (0x60)", #bitmask
0x74: "Turbocharger RPM",
0xA6: "Odometer", #big-endian u32/10 == km
},
2: { #Freeze Frame data, same PIDs as above, but results are from freeze-frame.
0x2: "Frozen DTC" #BCD.
},
3: { #Stored DTCs, no PID required. returns N*6 bytes, and (N+2//3) frames.
},
4: { #Clear DTCs, no PID. just *does*.
},
5: { #Test results; non-CAN o2 sensors. (We can't use this, since this is CAN-only)
},
6: { #Test results; CAN o2 sensors
},
7: { #Pending DTCs (same as 3)
},
8: { #Control systems (manufacturer specific?)
},
9: { #Vehicle information; VIN, etc.
0x00: "Supported PIDs", #bitmask
0x01: "VIN frame count", #only for K-line and J1850, usually 5
0x02: "Read VIN", #ascii-encoded, left-padded with nulls.
0x03: "Calibration ID frame count", #same as VIN, non-CAN only, multiple of 4.
0x04: "Calibration IDs", #up to 16 bytes each, unused bytes are null, multiple IDs may be returned.
0x06: "Calibration Verification Numbers", #same as above, but 4 bytes each, and count must match.
0x08: "Live performance tracking", #for spark vehicles, 4/5 frames, each one 4 bytes (two values)
0x0A: "ECU Name", #20 ASCII bytes, right-padded with NULLs
0x0B: "Live performance tracking", #same as other, but for compression-ignition
},
0x0A: { #Permanent DTCs
}
}

def recvthread(socket, stack):
  while stack.open:
    msg = socket.recv(.05)
    if msg:
      stack._recv(msg)

class OBD2Message:
  def __init__(self, l):
    self._len = l
    self.buf = bytearray()

  def __iadd__(self, buf):
    self.buf += buf
    return self

  def __bytes__(self):
    return bytes(self.buf)

  def done(self):
    return self._len == len(self.buf)

class OBD2ECU:
  def __init__(self, interface, pids):
    self.interface = interface
    self.pids = pids
  def readPID(self, pid):
    self.pids[pid] #just a KeyError check.

class OBD2Interface:
  def __init__(self, socket):
    self.open = True
    self.recvthread = threading.Thread(target=recvthread, args=(socket,self))
    self.ecus = {}
    self.buffers = {
      0x7E8: queue.Queue(),
      0x7E9: queue.Queue(),
      0x7EA: queue.Queue(),
      0x7EB: queue.Queue(),
      0x7EC: queue.Queue(),
      0x7ED: queue.Queue(),
      0x7EE: queue.Queue()
    }
    self.framebufs = { #used for multi-frame message reception
      0x7E8: None,
      0x7E9: None,
      0x7EA: None,
      0x7EB: None,
      0x7EC: None,
      0x7ED: None,
      0x7EE: None
    }
    self.socket = socket
    self.recvthread.start()
    resp = self.readPID(1, 0) #Supported PIDs
    for k,v in resp.items():
      pids = {}
      pack = struct.unpack(">I", v[3:8])[0]
      for i in range(0x20, 0, -1): #oddly, the highest PID is the lowest bit.
        if (pack & 1) == 1:
          pids[i] = True
        pack = pack >> 1
      if 0x20 in pids:
        ext = self.readPID(0x20, k) #*assuming* that this is the "read extented PID" messages?
        pack = struct.unpack(">I", ext[3:8])[0]
        for i in range(0x40, 0x20, -1): #oddly, the highest PID is the lowest bit.
          if (pack & 1) == 1:
            pids[i] = True
          pack = pack >> 1
      ecu = OBD2ECU(self, pids)
      self.ecus[k] = ecu

  def _recv(self, msg):
    global DEBUG
    util.log(6,"Recieved Frame:",msg)
    rx = msg.arbitration_id
    if rx in self.framebufs:
      util.log(5,"Frame is one we want")
      util.log(6,self.framebufs[rx])
      if not (self.framebufs[rx] is None):
        util.log(6,"Frame is multi-part component")
        assert 0xF0 & msg.data[0] == 0x20 #drop the sequence numbers...
        self.framebufs[rx] += msg.data[1:]
        if self.framebufs[rx].done():
          self.buffers[rx].put(bytes(self.framebufs[rx]))
          self.framebufs[rx] = None
      else:
        buf = msg.data
        if buf[0] == 0x10: #long multi-frame message, >7 bytes.
          util.log(5,"Frame is multi-part start")
          l = buf[1]
          req = buf[2] - 0x40
          pid = buf[3]
          dat = OBD2Message(l)
          util.log(6,dat)
          dat += buf[2:]
          self.framebufs[rx] = dat #prep to recieve more frames.
          util.log(6,dat)
          flow = can.Message(arbitration_id=(rx - 8),data=[0x30,0,0,0x55,0x55,0x55,0x55,0x55],extended_id=False)
          util.log(5,"sending flow control frame...")
          self.socket.send(flow) #kick out the flow control frame to tell the ECU that.
        else: #short frame, <8 bytes.
          util.log(5,"Frame is short frame")
          l = buf[0]
          req = buf[1]
          pid = buf[2]
          self.buffers[msg.arbitration_id].put(buf[1:l+2])

  def readPID(self, svc, pid, ecu=0x7DF):
    global DEBUG
    dat = [ svc, pid]
    self.send(ecu,dat)
    ret = {}
    for k,b in self.buffers.items():
      util.log(5,"Checking ECU {}...".format(k))
      resp = self._get(b)
      util.log(5,"Checked")
      if resp:
        ret[k] = resp
    if len(ret) == 0:
      return None
    return ret

  def readVIN(self):
    resp = self.readPID(9,2) #Service 9, PID 2 "Read VIN"
    assert resp[0] == 0x49, "wrong response?"
    assert resp[1] == 0x2, "not the VIN."
    return resp[3:].decode("ASCII") #trust that the first one is correct...

  def send(self, tx, data):
    assert len(data) < 8, "Trying to send more than 8 bytes in a request (does OBD2 allow that?)"
    dat = [0x99]*8
    dat[0] = len(data)
    for i in range(len(data)):
      dat[i+1] = data[i]
    msg = can.Message(arbitration_id=tx, extended_id=False, data=dat)
    self.socket.send(msg)

  def _get(self, q, timeout=.1):
    try:
      return q.get(timeout=timeout)
    except queue.Empty:
      return None

  def __enter__(self):
    return self
  def __exit__(self, a, b, c):
    self.open = False
    self.recvthread.join() #and wait for thread to die.
