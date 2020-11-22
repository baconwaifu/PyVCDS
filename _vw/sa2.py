import sa2_seed_key as sa

#Wrapper around someone else's SA2 implementation.
#SA2 is used on all UDS VWs for firmware flashing (and probably more things)
class SA2BytecodeRunner:
  def __init__(self, bytecode, seed):
    self.runner = sa.Sa2SeedKey(bytecode, seed)
    self.ran = False
    self.key = None
  def run(self):
    if self.ran: #short-circuit if we've already derived the key; should never actually *hit* this, but easy performance op if the key is re-used.
      return self.key
    self.key = self.runner.execute()
    self.ran = True
    return self.key



#ported from https://github.com/bri3d/kwp2000
#used for CAN-bus VWs as well as old k-line vehicles. possibly some UDS ones as well? (source for K-line cars using it: http://www.freediag.org/opendiag/4983.html)
#gives access to security level 2, or "write"
#security level 4 is read-only access, and is a much simpler algorithm ((seed + prekey) & 0xffffffff) where prekey is probably(?) 0x00011170
class XorKey:
  #the "processing factor" for the seed; *should* be selected from ECUID, but for some reason a lot use the last factor? (dec 63)
  SEED_DATA = [
            0x0A221289,0x144890A1,0x24212491,0x290A0285,
            0x42145091,0x504822C1,0x0A24C4C1,0x14252229,
            0x24250525,0x2510A491,0x28488863,0x29148885,
            0x422184A5,0x49128521,0x50844A85,0x620CC211,
            0x124452A9,0x18932251,0x2424A459,0x29149521,
            0x42352621,0x4A512289,0x52A48911,0x11891475,
            0x22346523,0x4A3118D1,0x64497111,0x0AE34529,
            0x15398989,0x22324A67,0x2D12B489,0x132A4A75,
            0x19B13469,0x25D2C453,0x4949349B,0x524E9259,
            0x1964CA6B,0x24F5249B,0x28979175,0x352A5959,
            0x3A391749,0x51D44EA9,0x564A4F25,0x6AD52649,
            0x76493925,0x25DE52C9,0x332E9333,0x68D64997,
            0x494947FB,0x33749ACF,0x5AD55B5D,0x7F272A4F,
            0x35BD5B75,0x3F5AD55D,0x5B5B6DAD,0x6B5DAD6B,
            0x75B57AD5,0x5DBAD56F,0x6DBF6AAD,0x75775EB5,
            0x5AEDFED5,0x6B5F7DD5,0x6F757B6B,0x5FBD5DBD
  ]
  def __init__(self, seed, ecu):
    self.seed = seed
    self.ecu = ecu
  def run(self):
    seed = self.seed
    #note: original java implementation used an "unsigned shift" for the rshift, but python numbers don't "have" a visible sign bit
    #and as such can be treated as pure u32.
    # (seed << 1) | (seed >> 31) is bitwise left rotate, by ORing the MSBit to the left-shift.
    for i in range(5): #5 shifts
      if ((seed & 0x80000000) == 0x80000000): # if the "to overflow" bit is set, xor with 'key'
        seed = (SEED_DATA[self.ecu]) ^ ((seed << 1) | (seed >> 31)) & 0xffffffff # rotate left, xor, and clamp.
      else:
        seed = ((seed << 1) | (seed >> 31)) #rotate left only
