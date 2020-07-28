#!/usr/bin/env python3

import can
import kwp
import vwtp
import vw
import struct

#SocketCAN "tracer" similar to candump, but decodes higher-level VW protocols as well.

reqmap = {}
for k,v in kwp.requests.items():
  reqmap[v.num] = k #create a reverse-mapping of request ID to names.

DEBUG = False

bus = can.interface.Bus(channel="can0", bustype="socketcan")

inbound = {} #from car
outbound = {} #to car

buffers = {}

def kwp_decode(buf):
  if buf[0] & 0x40 == 0x40: #response, harder to decode.
    if buf[0] == 0x61:
      print("VW Measuring block #{}:".format(buf[1]))
      for b in vw.parseBlock(buf):
        print(b)
    else:
      print("Unable to decode message type. generic as follows:")
      print("KWP response to {}:".format(reqmap[buf[0] - 0x40]), buf)
  else:
    if kwp.requests[reqmap[buf[0]]].fmt:
      print("Parameters:",kwp.requests[reqmap[buf[0]]].unpack(buf[1:]))
    else:
      print("Parameters unknown, raw message:",buf)

class VWTPConnection:
  def __init__(self, ecu, rx):
    self.ecu = ecu
    self.rx = rx
    self.tx = None
    self.inbuf = None
    self.outbuf = None
    self.outseq = 0
    self.seq = 0
    self.inlen = 0
    self.outlen = 0
    self.blksize = None
    self.params = None

  def recv(self, frame):
    global DEBUG
    #frame is a can data frame.
    buf = frame.data #the raw buffer contents of a CAN frame.
    op = buf[0]
    buf = buf[1:]
    if op == 0xA8: #disconnect
      print("Disconnect from {}, ECU {}".format(frame.arbitration_id, self.ecu))
      self.close()
    elif op == 0xA3: #"ping"
      print("Keepalive Ping from: ", frame.arbitration_id)
    elif op  == 0xA1: #params response

      self.params = buf
      self.blksize = buf[0] + 1 # 0 is "1 frame"
      scale = [ .1, 1, 10, 100]
      acktime = buf[1] >> 6 #scale is 100ms, 10ms, 1ms, .1ms
      self.acktime = (scale[acktime] * (buf[1] & 0x3F)) * 0.001 #go from ms to s.
      self.packival = (scale[buf[3] >> 6] * (buf[3] & 0x3F)) * 0.001
      print("Parameter response received. channel parameters:",
          "\nTimeout in ms:",self.acktime * 1000,"\nMinimum Interval between frames in ms:",self.packival * 1000,"\nBlock Size:",self.blksize)
    elif op & 0xf0 == 0xB0 or op & 0xf0 == 0x90:
      print("Ack recieved from {}, sequence {}".format(frame.arbitration_id,op & 0x0F))
    else: #assume it's a data packet.
      seq = op & 0x0f
      if op & 0x20 == 0 and seq == self.seq: #expecting ACK
        print ("VWTP subframe from {}, sequence {}, expecting ack".format(frame.arbitration_id,seq))
      self.seq += 1
      if self.seq == 0x10:
        self.seq = 0
      if not self.inbuf: #first frame of a transaction
        self.inlen = struct.unpack(">H", buf[0:2])[0]
        print("VWTP transmission start from {}, len {}".format(frame.arbitration_id,self.inlen))
        self.inbuf = bytearray()
        self.inbuf += buf[2:] #because bytearray.
      else:
        print("VWTP subframe from ",frame.arbitration_id)
        self.inbuf += buf
      if op & 0x10 == 0x10:
        if self.inlen != len(self.inbuf):
          print("WARN: frame length mismatch! expected {}, got {}. Attempting to continue...".format(self.inlen, len(self.inbuf)))
        self._recv(bytes(self.inbuf))
        self.inbuf = None
  def xmit(self, frame): #note: this is for the *tester* transmission; this is passive.
    global DEBUG
    #frame is a can data frame.
    buf = frame.data #the raw buffer contents of a CAN frame.
    op = buf[0]
    buf = buf[1:]
    if op == 0xA8: #disconnect
      print("Disconnect from {}, ECU {}".format(frame.arbitration_id, self.ecu))
      self.close()
    elif op == 0xA3: #"ping"
      print("Keepalive Ping from: ", frame.arbitration_id)
    elif op == 0xA0: #params request

      self.params = buf
      self.blksize = buf[0] + 1 # 0 is "1 frame"
      scale = [ .1, 1, 10, 100]
      acktime = buf[1] >> 6 #scale is 100ms, 10ms, 1ms, .1ms
      self.acktime = (scale[acktime] * (buf[1] & 0x3F)) * 0.001 #go from ms to s.
      self.packival = (scale[buf[3] >> 6] * (buf[3] & 0x3F)) * 0.001
      print("Parameter request received. channel parameters:",
          "\nTimeout in ms:",self.acktime * 1000,"\nMinimum Interval between frames in ms:",self.packival * 1000,"\nBlock Size:",self.blksize)
    elif op & 0xf0 == 0xB0 or op & 0xf0 == 0x90:
      print("Ack recieved from {}, sequence {}".format(frame.arbitration_id,op & 0x0F))
    else: #assume it's a data packet.
      seq = op & 0x0f
      if op & 0x20 == 0 and seq == self.outseq: #expecting ACK
        print ("VWTP subframe from {}, sequence {}, expecting ack".format(frame.arbitration_id,seq))
      self.outseq += 1
      if self.outseq == 0x10:
        self.outseq = 0
      if not self.outbuf: #first frame of a transaction
        self.outlen = struct.unpack(">H", buf[0:2])[0]
        print("VWTP transmission start from {}, len {}".format(frame.arbitration_id,self.inlen))
        self.outbuf = bytearray()
        self.outbuf += buf[2:] #because bytearray.
      else:
        print("VWTP subframe from ",frame.arbitration_id)
        self.outbuf += buf
      if op & 0x10 == 0x10:
        print ("VWTP Finalizer from {}, KWP decoding follows:".format(frame.arbitration_id))
        if self.outlen != len(self.outbuf):
          print("WARN: frame length mismatch! expected {}, got {}. Attempting to continue...".format(self.outlen, len(self.outbuf)))
        self._xmit(bytes(self.outbuf))
        self.outbuf = None
  def close(self):
    global inbound, outbound
    del inbound[self.rx]
    del outbound[self.tx]

  def _recv(self, buf):
    global reqmap
    if buf[0] == 0x7f:
      print("Negative KWP response for service {}:".format(buf[1]),kwp.responses[buf[2]])
    elif buf[0] & 0x40 == 0x40:
      if buf[0] - 0x40 in reqmap:
        print("Positive KWP response:", reqmap[buf[0] - 0x40])
        kwp_decode(buf)
      else:
        print("Unknown KWP response '{}' (OEM specific)".format(buf[0]))
        print("KWP block:",buf)
    else:
      if buf[0] in reqmap:
        print("KWP Request:",reqmap[buf[0]])
        kwp_decode(buf)
      else:
        print("Unknown OEM KWP service: '{}'".format(buf[0]))
        print("KWP block:",buf)
  def _xmit(self, buf):
    global reqmap
    if buf[0] == 0x7f:
      print("Negative KWP response for service {}:".format(buf[1]),kwp.resp[buf[2]])
    elif buf[0] & 0x40 == 0x40:
      if buf[0] - 0x40 in reqmap:
        print("Positive KWP response:", reqmap[buf[0] - 0x40])
        kwp_decode(buf)
      else:
        print("Unknown KWP response '{}' (OEM specific)".format(buf[0]))
        print("KWP block:",buf)
    else:
      if buf[0] in reqmap:
        print("KWP Request:",reqmap[buf[0]])
        kwp_decode(buf)
      else:
        print("Unknown OEM KWP service: '{}'".format(buf[0]))
        print("KWP block:",buf)

def recv(frame):
  global connections, buffers
  rx = frame.arbitration_id
  if rx == 0x200:
    buffers[frame.data[0] + 0x200] = []
    conn = VWTPConnection(frame.data[0], (frame.data[5] * 256) + frame.data[4])
    inbound[conn.rx] = conn
    print("Starting VWTP Connection to:",frame.data[0])
    print("Module name:",vw.modules(frame.data[0]))
  elif rx in buffers:
    if rx & 0xf00 == 0x200:
      print("Creating VWTP Connection")
      c = frame.data[2] + (frame.data[3]*256)
      tx = frame.data[4] + (frame.data[5]*256)
      outbound[tx] = inbound[c]
      inbound[c].tx = tx
      del buffers[rx] #connection setup done, so we're good here.
  elif rx in inbound:
    inbound[rx].recv(frame)
  elif rx in outbound:
    outbound[rx].xmit(frame)
  else:
    print("Untracked Frame: ",frame)

print("KWPTracer Started")
while True:
  recv(bus.recv())
