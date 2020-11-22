#!/usr/bin/env python3

import sa2
from kwp import KWPException #everything else is a class method
import struct


class FlashException(Exception):
  pass

class VWECUFlashInterface:
  def __init__(self, kwp, own=False, mode='r'):
    self.own = own #do we own the KWP socket?
    self.kwp = kwp
    self.mode = mode
    self.cursor = 0 #offset into ECU flash region
#    self.base = 0x80000000 #FIXME: detect base flash region based on ECU
    #note: we only support 4-byte seeds, which the struct.unpack will check for us. 
    if mode == 'r':
      seed = struct.unpack(">I", kwp.request("securityAccess", 3, b'')[2:]) #trim the response number and access level from the seed response
      key = (seed + 0x00011170) & 0xffffffff #FIXME: figure out the prekey for every ECU.
    elif mode == 'w':
      ecu = kwp.request('readEcuIdentification', 92)[2:] #get hardware ID
      e = 0
      for b in ecu:
        e += b
      ecu = e & 0x3f #only 3f entries in the prekey table, so clamp to that.
      seed = struct.unpack(">I", kwp.request("securityAccess", 1, b'')[2:])
      run = XorKey(seed, ecu)
      key = run.run()
    try: 
      if mode == 'r':
        kwp.request("securityAccess", 4, struct.pack(">I", key))
      elif mode == 'w':
        kwp.request("securityAccess", 2, struct.pack(">I", key))
    except KWPException as e:
      util.log(2, "Unable to unlock ECU, probably triggered lockout.")
      util.log(2, "if the below says 'exceedNumberOfAttempts' then go take a 10-minute drive before trying again. (to kill time; ignition only needs to be 'on' to count down)")
      util.log(2, e)
      raise FlashException("Unable to unlock ECU?")

  #I think ME9.6 ECUs use PowerPC cores?
  def read(self, l): #NOTE: this does *NOT* handle an unspecified length as of now
    if mode != 'r':
      raise FlashException("Can't read from write-only session")
    if l > 0xffffff:
      raise FlashException("KWP only supports 3-byte addresses!")
    if self.cursor > 0xffffff:
      raise FlashException("Cursor out of range? higher than possible address space")
    up = bytearray()
    up += struct.pack(">I", self.cursor)[1:] #trim to 3-byte
    up += b'00' #0: no compression, 0: no encryption (high and low nibbles, respectively)
    up += struct.pack(">I", l)[1:]
    req = self.kwp.request("requestUpload", bytes(up))
    size = 0
    out = bytearray()
    while size < l:
      try:
        buf = self.kwp.request("transferData", b'')[2:] #no arguments if using it for upload.
      except KWPException as e:
        if str(e) == "transferAborted":
          util.log(5, "Transfer Aborted by ECU")
          return out #current 'buf' is undefined.
      if size + len(buf) > l:
        util.log(3,"ECU sent extra data, truncating!")
        buf = buf[:l-size] #truncate extra data.
      out += buf
      size += len(buf)
    return out    
    
  #TODO: figure out compression and encryption. rumors of encryption being RSA, evidence points to a 10-byte xor of b'RobertCode' instead.
  #Routine C5 is supposedly "CalculateFlashChecksum," which appears to return a truncated CRC32b (last two bytes? or first two?)) 
  #write routine is "requestDownload" followed by block erase (routine C4) before transfering data, exiting the transfer, then running the checksum.
  #it appears most ECUs have a 128k 'reserved' boot block that isn't touched by flash tools. probably manufacture bootloader?
  #if you want to be clever, checksum the block and buffer before writing. because that's still *significantly* faster than an erase+program...
  #note: writes *MUST BE ALIGNED TO ERASE BLOCKS*. this command *DOES NOT CHECK THAT* because some ECUs may use wierd alignment or erase block sizes.
  def write(self, buf):
    if mode != 'w':
      raise FlashException("Can't write to read-only session")
    if
    raise NotImplementedError("Writing to ECU is not yet implemented, and is *totally untested*. this will *probably* brick something. buy the maintainer an airbag controller or something to testbench with.")

  def seek(self, cur):
    self.cursor = cur

  def __enter__(self):
    pass
  def __exit__(self, a, b, c):
    if self.own:
      self.kwp.__exit__(a,b,c)
