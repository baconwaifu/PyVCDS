import struct


# note: these are designed to be nested, to support variants with minor differences efficiently.
class VWCanBus:
    def __init__(self, base, spec):
        self.base = base
        self.spec = spec

    def repr(self, msg):
        if self.spec and msg.arbitration_id in self.spec:
            return self.spec[msg.arbitration_id](msg)
        if self.base:
            return self.base.repr(msg)
        return "<Unknown {}>".format(hex(msg.arbitration_id))

    def __contains__(self, obj):
        if self.spec and obj in self.spec:
            return True
        if self.base and self.base.__contains__(obj):
            return True
        return False


# Common gateway frames for every VWTP diagnostics VW.
# and a few other frames that seem to be common cross-generation.
common = VWCanBus(None, {
    0x280: lambda a: "ECU 1 RPM: {}".format(struct.unpack(">H", a.data[4:6])[0] // 4),
    0x300: lambda a: "Diag Outbound 1",
    0x301: lambda a: "Diag Outbound 2",
    0x302: lambda a: "Diag Outbound 3",
    # these can go all the way up to 30F, but those aren't common unless you're doing bulk live-data collection
    0x65f: lambda a: "VIN segment",  # first byte is chunk number.
})

models = {
    "3C": VWCanBus(common, {
        0x07d: lambda a: "Gateway Frame",
        0x0c2: lambda a: "Steering C2",
        0x0d0: lambda a: "Power Steering Torque: {} Steering Angle Segment: {}".format(a.data[2] * 0.00390625,
                                                                                       a.data[4] * 0.175781),
        0x181: lambda a: "Window Controls (Tentative)",
        0x1a0: lambda a: "ABS Vehicle Speed: {}".format(struct.unpack(">h", a.data[2:4])[0]),
        0x289: lambda a: "Steering 289, Cruise Control (Tentative)",
        0x291: lambda a: "Central Lock Control Signal (Tentative)",
        0x2c1: lambda a: "Steering 2c1, Turn Indicator Status (Tentative)",
        0x2c3: lambda a: "Key Status",
        0x2fc: lambda a: "Steering 2fc (Tentative)",
        0x310: lambda a: "Driver Door Status (Tentative)",
        0x312: lambda a: "Passenger Door Status (Tentative)",
        0x320: lambda a: "Instrument Cluster 320",
        0x35B: lambda a: "Gateway 35B, RPM, Oil, Water temp?",
        0x35F: lambda a: "Gateway 35F",
        0x380: lambda a: "Instrument Cluster 380",
        0x381: lambda a: "Driver Door Control Status (Tentative)",
        0x38a: lambda a: "Gateway 38a",
        0x391: lambda a: "Fob Control (Tentative)",
        0x392: lambda a: "Gateway 392",
        0x393: lambda a: "Gateway 393",
        0x395: lambda a: "Anti-Theft Control (Tentative)",
        0x3D0: lambda a: "EPS 2",
        0x3D2: lambda a: "E. Power Steering 3, Assistance: {}".format(a.data[2] * 0.00390625),
        0x3e5: lambda a: "Auxillary Heater",
        0x435: lambda a: "Radio MDI",
        0x436: lambda a: "SatNav",
        0x470: lambda a: "Gateway 470, Door Open State (Tentative)",
        0x480: lambda a: "Fuel Gauge (Tentative)",
        0x4a0: lambda a: "ABS 2, Wheel speed",
        0x51a: lambda a: "Instrument Cluster 51A",
        0x520: lambda a: "Instrument Cluster 520, Odometer?",
        0x527: lambda a: "Gateway 527, Ambient Temperature Sensor: {} (Untested Scaling)".format(a.data[4]),
        0x531: lambda a: "Light Control",
        # note: this has a pair of sequence bytes following the state frame. *be careful*.
        0x557: lambda a: "Gateway 557",
        0x570: lambda a: "Gateway 570",
        0x571: lambda a: "Battery Voltage: {} ".format(((a.data[0] / 2) + 50) / 10),
        0x572: lambda a: "Gateway 572",
        0x5C1: lambda a: "Steering Wheel Buttons",
        0x5C6: lambda a: "Steering 5C6",
        0x5D0: lambda a: "Gateway 5D0",
        0x5D1: lambda a: "Wiper Control",
        0x601: lambda a: "Power Mirror Switch",
        0x60E: lambda a: "Instrument Cluster 60E",
        0x621: lambda a: "Instrument Cluster 621, Status Light State?",
        0x62e: lambda a: "Instrument Cluster 62e",
        0x62f: lambda a: "MFD Status",
        0x635: lambda a: "Brightness Knob: {}%".format((a.data[0] / 64) * 100),
        0x65D: lambda a: "Time/Odometer?",
        0x688: lambda a: "MFD->Compass",
        0x689: lambda a: "Compass->MFD",
        0x70c: lambda a: "Steering 70C"
    }),
}
