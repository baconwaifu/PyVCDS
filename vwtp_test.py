#!/usr/bin/env python3
import vwtp
import can
#NOTE: this "replays" the transactions seen in jazdw's article on VWTP
#to verify that the VWTP stack is at least *mostly* working.

sent = None

def _send(self,frame):
  global sent
  sent = frame
  if frame[0] & 0x20 == 0: #if it wants an ACK, give it one now to avoid a deadlock.
    seq = (frame[0] + 1) & 0xf
    self._recv(can.Message(arbitration_id=0x300, data=[0xB0 + seq]))

class FakeBus:
  def __init__(self, stack):
    self.stack = stack
  def send(self, msg):
    dest = msg.data[0]
    frame = [None] * 7
    frame[0] = 0
    frame[1] = 0xD0 #setup response
    frame[2] = 0
    frame[3] = 0x03 #we echo the
    frame[4] = 0x40
    frame[5] = 0x07 #0x300-310 are the usually seen ones
    frame[6] = 1 #default is KWP transport
    self.stack._recv(can.Message(arbitration_id=0x200 + dest, data=frame, is_extended_id=False)) #use recursion to avoid a deadlock

vwtp.VWTPConnection._send = _send #hook the relevant methods to avoid needing a CAN driver.

stack = vwtp.VWTPStack(None)
stack.socket = FakeBus(stack)

conn = stack.connect(1) #"ECU"
conn.open()
conn._recv(can.Message(arbitration_id=0x300, data=[0xA1,0x0F,0x8A,0xFF,0x32,0xFF])) #"respond" with the ECU parameters
conn.send(b'\x10\x89') #startDiagnosticSession service with manufacturer-defined mode parameter.
assert bytes(sent) == b'\x10\x00\x02\x10\x89'
conn._recv(can.Message(arbitration_id=0x300, data=[0x10,0x00,0x02,0x50,0x89])) #"respond" to interrogation
assert bytes(sent) == b'\xB1' #check that an ACK was sent.
assert conn.read() == b'\x50\x89' #positive response, same value.
conn.send(b'\x21\x01') #readDataByLocalIdentifier ID 1.
assert bytes(sent) == b'\x11\x00\x02\x21\x01'
