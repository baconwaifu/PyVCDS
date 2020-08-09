# PyVCDS

PyVCDS is an attempt at implementing an open-source and cross-platform alternative to VCDS, using information that is freely available on the internet.

first off, the usual NO WARRANTY EXPRESSED OR IMPLIED, INCLUDING MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE  
and THIS IS EXPERIMENTAL SOFTWARE. I AM NOT RESPONSIBLE IF YOU DAMAGE, BRICK, OR OTHERWISE IMPACT OPERATION OF YOUR CAR (such as, but NOT LIMITED TO using untested or experimental features such as long-coding)

I AM NOT AFFILIATED WITH ROSS-TECH IN ANY WAY, AND HAVE NOT USED ANY VCDS MATERIAL IN THIS PROGRAM.

Due to the easy availability of Ross-tech's labels, I will *NOT* be including any labels
that are present in ross-tech's label database. As an alternative, this software can read labels
and build a local cache from ross-tech's files.

THE ELM327 IS NOT SUPPORTED. earlier versions have numerous bugs around raw CAN transport, which includes the clones.  
System requirements:

* Python 3
* the python CAN bus API. officially tested on linux and socketCAN.  
* any adapter that works with the aformentioned software (ie: NOT a hex-can or ELM327)  
the officially tested adapter hardware is a [CANdleLight](https://github.com/HubertD/candleLight) board (STM32F072) running the [candleLight_fw](https://github.com/candle-usb/candleLight_fw)

## Implemented Features:
* VWTP 2.0, the underlying transport used in all CAN VWs
* KWP2000 (synchronous operation only, periodic responses are not supported)
* Measurement block download and parsing
* Enumeration of available ECUs for connection (may or may not work)
* Retreival of serial numbers, VIN and other module information from ECUs (just a measuring block)
* Reading measurement block labels from ross-tech label files.
* Tracing of VWTP/KWP transactions; used for black-box testing with other scan tools.
* Tracing of "raw" VWTP transactions; used for investigating internal CAN bus traffic on VWs

## Roadmap
* More measurement block units and scaling code
* Module names from label files
* support for K-line (Low priority, since old, and VCDS unregistered can use cheap 3rd-party adapters for K-line stuff)
* UDF (does VW even use this? or is it all KWP?)
* "Long Codes" (Likely just KWP data blocks; just need a trace of the service being called from someone who has a hexcan and CAN sniffer)
* Better error handling (at least it now cleanly disconnects when an exception is thrown...)
* Session hijacking using an external scan tool. KWP has no protections against MITM.
* "Store and Forward" tracer. can be used to implement the above. note: this will *NEVER* support OBD2 due to potential misuse!
* Contributions to vag-diag-sim to support more KWP functions and crash less

## Testing
In order to test the features of the software without needing to have a car hooked up, a socketCAN equiped ECU simulator can be used.
The one used for working the initial kinks out of the VWTP stack is vag-diag-sim, although others can be used (such as a real "ECU in a box" simulator)

Unfortunately, the basic simulator used for initial testing is not advanced enough for testing much of anything aside from the basic measurement blocks and communication protocols (and the "ECU ID" request)  
It *is* a more sophisticated integration test, however. it can be configured to spit arbitrary data back at the tester in response to a query. allows testing code for crashes with "known good" responses from the ECU.

## Getting Started
Getting started with this toolkit simply involves running `diag.py` in a terminal.

The basic menu supports CAN/OBD-2 commands, such as retrieving the VIN or powertrain/emmisions DTCs (Not yet...)

The "OEM Enhanced" menu utilizes the VIN gathered over OBD-2 to determine the appropriate protocol and menu to use.  
For Volkswagen, this is VWTP/KWP. It's a fairly standard implementation of KWP2000 over CAN, just using
a proprietary transport protocol instead of ISO-TP. VW seems to use "Blocks" for everything, which are simply
local data identifiers.  
Once in the OEM enhanced menu, the option to "Enumerate Modules" is shown; this attempts to connect to every known module in-turn
in a similar manner to VCDS's "Auto-Scan" (but without recording anything other than the part number yet)  
Any operation involving a module, must first enumerate available modules. the list is cached while connected to the vehicle.  
Currently, you can get active DTCs (incomplete; can split DTCs, but dumps raw hex), load VCDS-compatible labels, and read known blocks (Not yet)

## Running Traces
The easiest way to implement some features is to take a "trace" of another scan tool, such as a hex-can.  
This program facilitates that with `tracer.py` or `candump` and can be used with an obd-2 splitter.  
Plug both adapters into the splitter, start `tracer.py` or `candump` (preferred) and start VCDS
and do the desired operation. take screenshots of each step, to add context to the trace.

NOTE: usage in a VM is *UNTESTED*, but as long as USB passthrough works, and using a new enough `gs_usb` device,
it should work fine.  
when using on the same machine as VCDS, run this in a VM, as hex-can stuff may not like being in a VM

## Contributing
* Contributors with a HEX-CAN scan tool are appreciated.
    * Use `tracer.py` or `candump` with an OBD-2 splitter, and attach the output (and relevant VCDS screenshots) to a github issue.
    * When using a VM, use a linux VM on windows using a `gs_usb` adapter (such as the CANdleLight project)
* Contributions of labels must be for labels that are *not present* in Ross-tech's database.
    * Violations of this rule may lead to being **permanently banned** from further contribution.
* All support requests must include:
    * *exact* part number
    * anonymized VIN (get from diag.py)
    * The address of the module in question
    * the block, DTC, or routine in question.
