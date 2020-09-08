#!/usr/bin/env python3

import can
import kwp
import vwtp
import vw
import struct
import util
import json

#SocketCAN "tracer" similar to candump, but decodes higher-level VW protocols as well.

reqmap = {}
for k,v in kwp.requests.items():
  reqmap[v.num] = k #create a reverse-mapping of request ID to names.

try:
  with open("config.json", "r") as fd:
    opts = json.loads(fd.read())
except FileNotFound: #write default config.
  opts = { "channel":"can0", "bustype":"socketcan"}
  with open("config.json", 'w') as fd:
    fd.write(json.dumps(opts))

bus = can.interface.Bus(**opts) #we get the CAN bus information from a local file.

inbound = {} #from car
outbound = {} #to car

buffers = {}

def kwp_decode(buf):
  if buf[0] & 0x40 == 0x40: #response, harder to decode.
    if buf[0] == 0x58:
      print("Response to Module DTCs by status:")
      count = buf[1]
      print("NOTE: proper OBD notation is not yet implemented. raw hex codes are displayed.")
      print("NOTE: leading character is (usually) implied by the module being read")
      if not count == 0:
        for i in range(0, count*2, 2):
          print("DTC hexcode:", buf[i+2:i+4])
    elif buf[0] == 0x53:
      print("Response to Module DTCs:") #NOTE: the response format is identical, but the actual *response* is different.
      count = buf[1]
      print("NOTE: proper OBD notation is not yet implemented. raw hex codes are displayed.")
      print("NOTE: leading character is (usually) implied by the module being read")
      if not count == 0:
        for i in range(0, count*2, 2):
          print("DTC hexcode:", buf[i+2:i+4])
    elif buf[0] == 0x61:
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
      util.log(4,"Disconnect from {}, ECU {}".format(frame.arbitration_id, self.ecu))
      self.close()
    elif op == 0xA3: #"ping"
      util.log(5,"Keepalive Ping from: ", frame.arbitration_id)
    elif op  == 0xA1: #params response

      self.params = buf
      self.blksize = buf[0] + 1 # 0 is "1 frame"
      scale = [ .1, 1, 10, 100]
      acktime = buf[1] >> 6 #scale is 100ms, 10ms, 1ms, .1ms
      self.acktime = (scale[acktime] * (buf[1] & 0x3F)) * 0.001 #go from ms to s.
      self.packival = (scale[buf[3] >> 6] * (buf[3] & 0x3F)) * 0.001
      util.log(4,"Parameter response received.")
      util.log(5,"channel parameters:",
          "\nTimeout in ms:",self.acktime * 1000,"\nMinimum Interval between frames in ms:",self.packival * 1000,"\nBlock Size:",self.blksize)
    elif op & 0xf0 == 0xB0 or op & 0xf0 == 0x90:
      util.log(5,"Ack recieved from {}, sequence {}".format(frame.arbitration_id,op & 0x0F))
    else: #assume it's a data packet.
      seq = op & 0x0f
      if op & 0x20 == 0 and seq == self.seq: #expecting ACK
        util.log(6,"VWTP subframe from {}, sequence {}, expecting ack".format(frame.arbitration_id,seq))
      self.seq += 1
      if self.seq == 0x10:
        self.seq = 0
      if not self.inbuf: #first frame of a transaction
        try:
          self.inlen = struct.unpack(">H", buf[0:2])[0]
        except struct.error:
          util.log(3,"Short frame recieved:",frame)
          self.inlen = -1
        util.log(6,"VWTP transmission start from {}, len {}".format(frame.arbitration_id,self.inlen))
        self.inbuf = bytearray()
        if self.inlen > 0:
          self.inbuf += buf[2:] #because bytearray.
        else:
          self.inbuf += buf
      else:
        util.log(6,"VWTP subframe from ",frame.arbitration_id)
        self.inbuf += buf
      if op & 0x10 == 0x10:
        if self.inlen != len(self.inbuf):
          util.log(3,"WARN: frame length mismatch! expected {}, got {}. Attempting to continue...".format(self.inlen, len(self.inbuf)))
        self._recv(bytes(self.inbuf))
        self.inbuf = None
  def xmit(self, frame): #note: this is for the *tester* transmission; this is passive.
    global DEBUG
    #frame is a can data frame.
    buf = frame.data #the raw buffer contents of a CAN frame.
    op = buf[0]
    buf = buf[1:]
    if op == 0xA8: #disconnect
      util.log(4,"Disconnect from {}, ECU {}".format(frame.arbitration_id, self.ecu))
      self.close()
    elif op == 0xA3: #"ping"
      util.log(5,"Keepalive Ping from: ", frame.arbitration_id)
    elif op == 0xA0: #params request

      self.params = buf
      self.blksize = buf[0] + 1 # 0 is "1 frame"
      scale = [ .1, 1, 10, 100]
      acktime = buf[1] >> 6 #scale is 100ms, 10ms, 1ms, .1ms
      self.acktime = (scale[acktime] * (buf[1] & 0x3F)) * 0.001 #go from ms to s.
      self.packival = (scale[buf[3] >> 6] * (buf[3] & 0x3F)) * 0.001
      util.log(4,"Parameter request received.")
      util.log(5, "channel parameters:",
          "\nTimeout in ms:",self.acktime * 1000,"\nMinimum Interval between frames in ms:",self.packival * 1000,"\nBlock Size:",self.blksize)
    elif op & 0xf0 == 0xB0 or op & 0xf0 == 0x90:
      util.log(6,"Ack recieved from {}, sequence {}".format(frame.arbitration_id,op & 0x0F))
    else: #assume it's a data packet.
      seq = op & 0x0f
      if op & 0x20 == 0 and seq == self.outseq: #expecting ACK
        util.log(6,"VWTP subframe from {}, sequence {}, expecting ack".format(frame.arbitration_id,seq))
      self.outseq += 1
      if self.outseq == 0x10:
        self.outseq = 0
      if not self.outbuf: #first frame of a transaction
        if len(buf) < 2:
          self.outlen = -1
        else:
          self.outlen = struct.unpack(">H", buf[0:2])[0]
        util.log(6,"VWTP transmission start from {}, len {}".format(frame.arbitration_id,self.inlen))
        self.outbuf = bytearray()
        self.outbuf += buf[2:] #because bytearray.
      else:
        util.log(6,"VWTP subframe from ",frame.arbitration_id)
        self.outbuf += buf
      if op & 0x10 == 0x10:
        util.log(5,"VWTP 'Message Complete' from {}, KWP decoding follows:".format(frame.arbitration_id))
        if self.outlen != len(self.outbuf):
          util.log(3,"WARN: frame length mismatch! expected {}, got {}. Attempting to continue...".format(self.outlen, len(self.outbuf)))
        try:
          self._xmit(bytes(self.outbuf))
        except Exception as e:
          util.log(3,"Error parsing buffer: {}",e)
          util.log(3,"Problem Frame:",self.outbuf)
          if type(e) not in (struct.Error,): #add context, but only warn about struct errors.
            raise e
        self.outbuf = None
  def close(self):
    global inbound, outbound
    del inbound[self.rx]
    del outbound[self.tx]

  def _recv(self, buf):
    global reqmap
    if buf[0] == 0x7f: #negative response
      util.log(5,"Negative KWP response for service {}:".format(buf[1]),kwp.responses[buf[2]])
    elif buf[0] & 0x40 == 0x40: #positive response; always.
      if buf[0] - 0x40 in reqmap:
        util.log(5,"Positive KWP response to service:", reqmap[buf[0] - 0x40])
        kwp_decode(buf)
      else:
        util.log(3,"Positive KWP response to Unknown service '{}' (OEM specific)\nReport trace to maintainer with VIN.".format(buf[0]-0x40))
        util.log(3,"KWP block:",buf)
    else:
      if buf[0] in reqmap:
        util.log(4,"KWP Request:",reqmap[buf[0]])
        kwp_decode(buf)
      else:
        util.log(3,"Unknown OEM KWP service: '{}'\nReport trace to maintainer with VIN".format(buf[0]))
        util.log(3,"KWP block:",buf)
  def _xmit(self, buf):
    global reqmap
    if buf[0] == 0x7f:
      util.log(5,"Negative KWP response for service {}:".format(buf[1]),kwp.resp[buf[2]])
    elif buf[0] & 0x40 == 0x40:
      if buf[0] - 0x40 in reqmap:
        util.log(5,"Positive KWP response:", reqmap[buf[0] - 0x40])
        kwp_decode(buf)
      else:
        util.log(3,"Unknown KWP response '{}' (OEM specific)\nReport trace to maintainer with VIN.".format(buf[0]))
        util.log(3,"KWP block:",buf)
    else:
      if buf[0] in reqmap:
        util.log(4,"KWP Request:",reqmap[buf[0]])
        kwp_decode(buf)
      else:
        util.log(3,"Unknown OEM KWP service: '{}'\nReport trace to maintainer with VIN".format(buf[0]))
        util.log(3,"KWP block:",buf)

def recv(frame):
  global connections, buffers
  rx = frame.arbitration_id
  if rx == 0x200:
    buffers[frame.data[0] + 0x200] = []
    conn = VWTPConnection(frame.data[0], (frame.data[5] * 256) + frame.data[4])
    inbound[conn.rx] = conn
    util.log(4,"Starting VWTP Connection to:",frame.data[0])
    util.log(4,"Module name:",vw.modules[frame.data[0]])
  elif rx in buffers:
    if rx & 0xf00 == 0x200:
      util.log(5,"Creating VWTP Connection")
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
    util.log(4,"Untracked Frame: ",frame)

if __name__ == "__main__":
  util.log(4,"KWPTracer Started")
  while True:
    recv(bus.recv())
