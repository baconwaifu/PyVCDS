#!/usr/bin/env python3

import can

import kwp
import vwtp
from vw import labels


class blockMeasure:
    def __init__(self, name, func):
        self.func = func
        self.name = name
        self.label = None

    def unscale(self, a, b):
        ret = blockMeasure(self.name, None)
        ret.value = self.func(a, b)
        return ret

    def __str__(self):
        if self.label:
            return "{} {} {}".format(self.value, self.name, self.label)
        else:
            return "{} {}".format(self.value, self.name)

    def __repr__(self):
        return self.__str__()


scalers = {
    0x1: blockMeasure("/min", lambda a, b: (a * b) / 5),
    0x4: blockMeasure("°ATDC", lambda a, b: (b - 127) * .01 * a),  # BTDC is expressed as a negative number.
    0x7: blockMeasure("km/h", lambda a, b: .01 * a * b),
    0x8: blockMeasure("binary", lambda a, b: (a << 8) | b),
    0x10: blockMeasure("binary", lambda a, b: (a << 8) | b),
    0x11: blockMeasure("ASCII", lambda a, b: bytes([a, b]).decode("ascii")),
    0x12: blockMeasure("mbar", lambda a, b: (a * b) * 25),
    0x14: blockMeasure("%", lambda a, b: ((a * b) / 128) - 1),
    0x15: blockMeasure("V", lambda a, b: (a * b) / 1000),
    0x16: blockMeasure("ms", lambda a, b: .001 * a * b),
    0x17: blockMeasure("%", lambda a, b: (b * a) / 256),
    0x19: blockMeasure("g/s (air)", lambda a, b: (100 / a) * b),
    0x1A: blockMeasure("°C", lambda a, b: b - a),
    0x21: blockMeasure("%", lambda a, b: b * 100 if a == 0 else (b * 100) / a),  # same unit, different scaling.
    0x22: blockMeasure("kW", lambda a, b: (b - 128) * .01 * a),
    0x23: blockMeasure("/h", lambda a, b: (a * b) / 100),
    0x25: blockMeasure("binary", lambda a, b: (a << 8) | b),
    0x27: blockMeasure("mg/stroke (fuel)", lambda a, b: (a * b) / 256),
    0x31: blockMeasure("mg/stroke (air)", lambda a, b: (a * b) / 40),
    0x33: blockMeasure("mg/stroke (Δ)", lambda a, b: ((b - 128) / 255) * a),
    0x36: blockMeasure("Count", lambda a, b: (a * 256) + b),
    0x37: blockMeasure("seconds", lambda a, b: (a * b) / 200),
    0x51: blockMeasure("°CF", lambda a, b: ((a * 11200) + (b * 436)) / 1000),  # torsion; check formula.
    0x5E: blockMeasure("Nm", lambda a, b: a * ((b / 50) - 1)),  # torque; check formula.
    0x100: blockMeasure("[Unknown Unit]", lambda a, b: (a << 8) | b)
}


def parseBlock(block):
    blk = []
    buf = block[2:]
    for i in range(0, len(buf), 3):
        if buf[i] in scalers:
            blk.append(scalers[buf[i]].unscale(buf[i + 1], buf[i + 2]))
        else:
            blk.append(scalers[256].unscale(buf[i + 1], buf[i + 2]))
    return blk


def labelBlock(ecu, blknum, blk):
    for i in range(len(blk)):
        blk.label = labels[(ecu, blknum)][i]


if __name__ == "__main__":
    import sys

    sock = can.interface.Bus(channel='vcan0', bustype='socketcan')
    stack = vwtp.VWTPStack(sock)

    conn = stack.connect(1)  # "ECU"
    kw = kwp.KWPSession(conn)
    with conn:
        assert kw.request("startDiagnosticSession", 0x89) == b'\x50\x89'  # positive response, same value.
        print(parseBlock(kw.request("readDataByLocalIdentifier", 0x2)))
    kw.close()
    sys.exit(0)  # need to do this because of threads.
