#!/usr/bin/env python3

import can
import queue
import threading
import struct

DEBUG = True

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

recv = True
def recvthread(socket, stack):
  global recv
  while recv:
    stack._recv(socket.recv())

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
    recv = True
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
    recv = True
    self.recvthread.start()
    resp = self.readPID(0) #Supported PIDs
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
    if DEBUG:
      print("Recieved Frame:",msg)
    rx = msg.arbitration_id
    if rx in self.framebufs:
      if DEBUG:
        print("Frame is one we want")
        print(self.framebufs[rx])
      if not (self.framebufs[rx] is None):
        if DEBUG:
          print("Frame is multi-part component")
        assert 0xF0 & msg.data[0] == 0x20 #drop the sequence numbers...
        self.framebufs[rx] += msg.data[1:]
        if self.framebufs[rx].done():
          self.buffers[rx].put(bytes(self.framebufs[rx]))
          self.framebufs[rx] = None
      else:
        buf = msg.data
        if buf[0] == 0x10: #long multi-frame message, >7 bytes.
          if DEBUG:
            print("Frame is multi-part start")
          l = buf[1]
          req = buf[2] - 0x40
          pid = buf[3]
          dat = OBD2Message(l)
          if DEBUG:
            print(dat)
          dat += buf[2:]
          self.framebufs[rx] = dat #prep to recieve more frames.
          if DEBUG:
            print(dat)
          flow = can.Message(arbitration_id=(rx - 8),data=[0x30,0,0,0x55,0x55,0x55,0x55,0x55],extended_id=False)
          print("sending flow control frame...")
          self.socket.send(flow) #kick out the flow control frame to tell the ECU that.
        else: #short frame, <8 bytes.
          if DEBUG:
            print("Frame is short frame")
          l = buf[0]
          req = buf[1]
          pid = buf[2]
          self.buffers[msg.arbitration_id].put(buf[1:l+2])

  def readVIN(self):
    self.send(0x7DF, [0x9, 0x2])
    for k,b in self.buffers.items():
      buf = bytearray()
      resp = self._get(b,timeout=.5)
      assert resp[0] == 0x49, "wrong response?"
      assert resp[1] == 0x2, "not the VIN."
      return resp[3:].decode("ASCII") #trust that the first one is correct...

  def readPID(self, pid, ecu=0x7DF):
    global DEBUG
    dat = [ 0x01, pid]
    self.send(ecu,dat)
    ret = {}
    for k,b in self.buffers.items():
      if DEBUG:
        print("Checking ECU {}...".format(k))
      resp = self._get(b)
      if DEBUG:
        print("Checked")
      if resp:
        ret[k] = resp
    if len(ret) == 0:
      return None
    return ret

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
    recv = False
