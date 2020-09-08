# PyVCDS

PyVCDS is an attempt at implementing an open-source and cross-platform alternative to VCDS, using information that is freely available on the internet, and experimentation on an old (2007...) VW.

first off, the usual NO WARRANTY EXPRESSED OR IMPLIED, INCLUDING MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE  
and THIS IS EXPERIMENTAL SOFTWARE. I AM NOT RESPONSIBLE IF YOU DAMAGE, BRICK, OR OTHERWISE IMPACT OPERATION OF YOUR CAR (such as, but NOT LIMITED TO using untested or experimental features such as long-coding)

I AM NOT AFFILIATED WITH ROSS-TECH IN ANY WAY, AND HAVE NOT USED ANY VCDS MATERIAL IN THIS PROGRAM.

Due to the "easy availability" of Ross-tech's labels, I will *NOT* be including any labels
that are present in ross-tech's label database. As an alternative, this software can read *plaintext* labels
and build a local cache from ross-tech's files. **CLB LABELS ARE NOT, AND WILL *NEVER* BE SUPPORTED**.
The entire purpose of CLB files is to prevent competitors from trivially using them, and therefore I will *NEVER*
support decryption of CLB labels. I may document the *file format*, but key material and/or decryptors will
NEVER be released.

If you ***NEED*** to use CLB labels, buy a hex-can and use VCDS. I won't help you.


THE ELM327 IS NOT SUPPORTED. earlier versions have numerous bugs around raw CAN transport, which includes the clones.  
System requirements:

* Python 3
* the python CAN bus API. officially tested on linux and socketCAN.  
* any adapter that works with the aformentioned software (ie: NOT a hex-can or ELM327)  
the officially tested adapter hardware is a [CANdleLight](https://github.com/HubertD/candleLight) board (STM32F072) running the [candleLight_fw](https://github.com/candle-usb/candleLight_fw)

## Implemented Features:
* VWTP 2.0, AKA "TP20", the underlying transport used in all CAN VWs
* KWP2000 (synchronous operation only, periodic responses are not supported)
* Measurement block download and parsing
* Enumeration of available ECUs for connection (works. mostly. not very well though.)
* Retreival of serial numbers, VIN and other module information from ECUs (just parameters to readEcuIdentification)
* Reading measurement block labels from *plaintext* ross-tech label files.
* Tracing of VWTP/KWP transactions; used for black-box testing with other scan tools. (VWTP `proto == 1`)
* Tracing of "raw" VWTP transactions; used for investigating internal CAN bus traffic on VWs (usually, `proto != 1` traffic)

## Roadmap
* More measurement block units and scaling code
* Module names from label files
* support for K-line (Low priority, since old, and VCDS unregistered can use cheap 3rd-party adapters for K-line stuff)
* UDF (Newer VWs; will likely shim on top of `scapy` since it already has a maintained implementation)
* "Long Codes" (Likely just KWP data blocks; just need a trace of the service being called from someone who has a hexcan and CAN sniffer)
* Better error handling (at least it now cleanly disconnects when an exception is thrown...)
* "Session hijacking" using an external scan tool. KWP has no protections against MITM.
* "Store and Forward" tracer. can be used to implement the above. note: this will *NEVER* support OBD2 due to potential misuse!
* Contributions to vag-diag-sim to support more KWP functions and crash less.

## Testing
In order to test the features of the software without needing to have a car hooked up, a socketCAN equiped ECU simulator can be used.
The one used for working the initial kinks out of the VWTP stack is vag-diag-sim, although others can be used (such as a real "ECU in a box" simulator)

Unfortunately, the basic simulator used for initial testing is not advanced enough for testing much of anything aside from the basic measurement blocks and communication protocols (and the "ECU ID" request)  
It *is* a more sophisticated integration test, however. it can be configured to spit arbitrary data back at the tester in response to a query. allows testing code for crashes with "known good" responses from the ECU.

## Getting Started
Getting started with this toolkit simply involves running `diag.py` in a terminal.

The basic menu supports CAN/OBD-2 commands, such as retrieving the VIN or powertrain/emmisions DTCs (Not yet the latter...)

The "OEM Enhanced" menu utilizes the VIN gathered over OBD-2 to determine the appropriate protocol and menu to use.  
For Volkswagen, this is VWTP/KWP. It's a fairly standard implementation of the KWP2000 application layer over CAN, just using
a proprietary transport protocol instead of ISO-TP. VW seems to use "Blocks" for everything, which is a holdover term from the old
KWP1282 protocol, in KWP2000 Measuring Blocks are just parameters to `readDataByLocalIdentifier`.  
Once in the OEM enhanced menu, the option to "Enumerate Modules" is shown; this attempts to connect to every known module in-turn
in a similar (but more primitive) manner to VCDS's "Auto-Scan" (but without recording anything other than the part number yet)  
Any operation involving a module, must first enumerate available modules. the list is cached while connected to the vehicle.  
Currently, you can get active DTCs (incomplete; can split DTCs, but dumps raw hex), load VCDS-compatible labels, and read known blocks (Not yet)

## Running Traces
The easiest way to implement some features is to take a "trace" of another scan tool, such as a hex-can.  
This program facilitates that with `tracer.py` or `candump` and can be used with an obd-2 splitter.  
Plug both adapters into the splitter, start `tracer.py` or `candump` (preferred) and start VCDS
and do the desired operation. take screenshots of each step, to add context to the trace.

NOTE: usage in a VM is *UNTESTED*, but as long as USB passthrough works, and using a new enough `gs_usb` device,
it should work fine.  
when using on the same machine as VCDS, run this in a VM, or use one of the fancy wifi-can things they sell.

## Contributing
* Contributors with a HEX-CAN scan tool are appreciated.
    * Use `tracer.py` or `candump` with an OBD-2 splitter, and attach the output (and relevant VCDS screenshots) to a github issue.
    * When using a VM, use a linux VM on windows using a `gs_usb` adapter (such as the CANdleLight project)
* Contributions of labels must be for labels that are *not present* in Ross-tech's database.
    * Violations of this rule may lead to being **permanently banned** from further contribution.
* All support requests must include:
    * *exact* part number (unless that's the problem...)
    * "anonymized" VIN (get from diag.py)
    * The module in question
    * the block, DTC, or routine in question.
