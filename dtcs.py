import sqlite3

import util


# SAE DTCs are sourced from the 2012 document in the federal register

# Powertrain SAE DTC ranges:
# P0001–P0099: Fuel and air metering, auxiliary emissions controls
# P0100–P0199: Fuel and air metering
# P0200–P0299: Fuel and air metering (injector circuit)
# P0300–P0399: Ignition system or misfire
# P0400–P0499: Auxiliary emissions controls
# P0500–P0599: Vehicle speed controls, and idle control systems
# P0600–P0699: Computer output circuit
# P0700–P0799: Transmission
# P1000-P1999: OEM DTC
# P3000-P3999: OEM/SAE Reserved.

# B0000-B0999: SAE
# B1000-B2999: OEM
# B3000-B3999: Reserved By Document (As of 2012)

# Chassis Ranges: same as above
# Network: Same


# interface designed so that internet DTC lookups can be called in the future
class DTCProvider:
    def query(self, dtc):
        raise NotImplementedError("DTCProvider cannot be called directly")


class JSONDTCProvider(DTCProvider):
    def __init__(self, json, manufacturer=None):
        self.js = json.parse(json)  # dict of manufacturer VIN codes, each a dict of associated DTCs.
        self.man = manufacturer  # this is the VIN-prefix, not a name.

    def query(self, dtc):  # P3000 to P3399 are OEM, P3400 to P3999 are SAE.
        if dtc[1] == "0" or dtc[1] == "2" or dtc[1] == "3":  # try SAE DTC
            if dtc[1] != "3":  # 3 is "probably" SAE DTC, but also an OEM prefix in some cases.
                try:
                    return self.js[self.man][dtc]
                except KeyError:
                    util.log(3, "Unknown SAE Standard DTC '{}'! contact maintainer".format(dtc))
                    return "<Unknown SAE DTC>"
            elif dtc in self.js["SAE"]:  # is the DTC a known standard one?
                return self.js["SAE"][dtc]
        if not self.man or not self.man in self.js:
            # we don't have a manufacturer, or we don't have a DTC table for that manufacturer.
            return "<Unknown OEM DTC - No OEM DTCs loaded>"
        if dtc in self.js[self.man]:
            return self.js[self.man][dtc]
        return "<Unknown OEM DTC>"


# relevant schema: 'dtc' column is DTC "text" form, and 'en' column is DTC description (in english)
class SQLiteDTCProvider(DTCProvider):
    def __init__(self, path, manufacturer=None):
        self.db = sqlite3.open(path)
        self.man = manufacturer  # VIN prefix, not a name.
        raise NotImplementedError("SQLite DTC databases are currently unsupported")

    def __enter__(self):
        pass

    def __exit__(self, a, b, c):
        if self.db:
            self.db.close()
            self.db = None
