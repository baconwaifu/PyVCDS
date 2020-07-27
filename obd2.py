#!/usr/bin/env python3

import can
import queue

pids = {
0x1: "Monitor Status",
0x2: "Freeze DTC",
0x3: "Fuel System Status",
0x4: "Calculated Engine Load",
0x5: "Engine Coolant temp",
0x6: "Short term fuel trim (Bank 1)",
0x7: "Long term fuel trim (Bank 1)",
0x8: "Short term fuel trim (Bank 2)",
0x9: "Long term fuel trim (Bank 2)",
0xA: "Fuel Pressure",
0xB: "Intake manifold abs. pressure",
0xC: "Engine RPM",
0xD: "Vehicle Speed",
0xE: "Timing Advance",
0xF: "Intake air temp.",
0x10: "MAF flow rate",
0x11: "Throttle Position",
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
0x1C: "OBD Standards",
0x1D: "Oxygen Sensors present (4 banks)",
0x1E: "Aux. input status (hybrids?)",
0x1F: "Run-time since engine start",
0x20: "Extended PIDs"
}

class OBD2Message:
  def __init__(self, l):
    self._len = l
    self.buf = bytearray()

  def __iadd__(self, buf):
    self.buf += buf

  def __bytes__(self, buf):
    return bytes(buf)

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
    self.ecus = {}
    self.buffers = {
      0x7D8: queue.Queue(),
      0x7D9: queue.Queue(),
      0x7DA: queue.Queue(),
      0x7DB: queue.Queue(),
      0x7DC: queue.Queue(),
      0x7DD: queue.Queue(),
      0x7DE: queue.Queue()
    }
    self.framebufs = { #used for multi-frame message reception
      0x7D8: None,
      0x7D9: None,
      0x7DA: None,
      0x7DB: None,
      0x7DC: None,
      0x7DD: None,
      0x7DE: None
    }
    self.socket = socket
    resp = self.readPID(0) #Supported PIDs
    for k,v in resp:
      pids = {}
      pack = struct.unpack(">I", resp[3:8])[0]
      for i in range(0x20, 0, -1): #oddly, the highest PID is the lowest bit.
        if (pack & 1) == 1:
          pids[i] = True
        pack = pack >> 1
      if 0x20 in pids:
        ext = self.readPID(0x20, k)
        pack = struct.unpack(">I", ext[3:8])[0]
        for i in range(0x40, 0x20, -1): #oddly, the highest PID is the lowest bit.
          if (pack & 1) == 1:
            pids[i] = True
          pack = pack >> 1
      ecu = OBD2ECU(self, pids)
      self.ecus[k] = ecu

  def _recv(self, msg):
    rx = msg.arbitration_id
    if rx in self.framebufs:
      if self.framebufs[rx]:
        assert 0xF0 & msg.data[0] == 0x20 #drop the sequence numbers...
        self.framebufs[rx] += msg.data[1:]
        if self.framebufs[rx].done():
          self.buffers[rx].put(bytes(self.framebufs[rx]))
          self.framebufs[rx] = None
      else:
        buf = msg.data
        if buf[0] == 0x10: #long multi-frame message, >7 bytes.
          l = buf[1]
          req = buf[2] - 0x40
          pid = buf[3]
          dat = OBD2Message(l)
          dat += buf[2:]
          self.framebufs[msg.arbitration_id] = dat #prep to recieve more frames.
          flow = can.Message(arbitration_id=(msg.arbitration_id - 8),data=[0x3],extended_id=False)
          self.socket.send(flow) #kick out the flow control frame to tell the ECU that.
        else: #short frame, <8 bytes.
          l = buf[0]
          req = buf[1]
          pid = buf[2]
          self.buffers[msg.arbitration_id].put(buf[1:l+2])

  def getVIN(self):
    send(0x7DF, [0x9, 0x2])
    for k,b in buffers.items():
      buf = bytearray()
      resp = self._get(b)
      assert resp[0] == 0x49, "wrong response?"
      assert resp[1] == 0x2, "not the VIN."
      return resp[2:].decode("ASCII")

  def readPID(self, pid, ecu=0x7DF):
    dat = [ 0x01, pid]
    self.send(ecu,dat)
    ret = {}
    for k,b in self.buffers.items():
      resp = self._get(b)
      if resp:
        ret[k] = resp
    return ret if not len(ret) == 0 else None

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
      return q.get(timeout=.1)
    except queue.Empty:
      return None
