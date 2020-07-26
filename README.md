# PyVCDS

PyVCDS is an attempt at implementing an open-source and cross-platform alternative to VCDS, using information that is freely available on the internet.

first off, the usual NO WARRANTY EXPRESSED OR IMPLIED, INCLUDING MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE  
and THIS IS EXPERIMENTAL SOFTWARE. I AM NOT RESPONSIBLE IF YOU BRICK YOUR CAR (such as, but NOT LIMITED TO using untested or experimental features such as long-coding)

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

## Roadmap
* More measurement block units and scaling code
* Measuring block label parsing (mapping code is present, but the code to generate said map is not)
* support for K-line (Low priority, since old, and VCDS unregistered can use cheap 3rd-party adapters for K-line stuff)
* UDF (does VW even use this? or is it all KWP?)
* "Long Codes" (Likely just KWP data blocks; just need a trace of the service being called from someone who has a hexcan and CAN sniffer)
* Measurement block descriptions, as well as a map for each ECU.
* Machine-readable debugging tracelogs (for the software itself)
* "Replay" of those traces with newer decoders.
* Better error handling (at least it now cleanly disconnects when an exception is thrown...)

## Testing
In order to test the features of the software without needing to have a car hooked up, a socketCAN equiped ECU simulator can be used.
The one used for working the initial kinks out of the VWTP stack is vag-diag-sim, although others can be used (such as a real "ECU in a box" simulator)

Unfortunately, the basic simulator used for initial testing is not advanced enough for testing much of anything aside from the basic measurement blocks and communication protocols (and the "ECU ID" request)  
It *is* a more sophisticated integration test, however. it can be configured to spit arbitrary data back at the tester in response to a query. allows testing code for crashes with "known good" responses from the ECU.

