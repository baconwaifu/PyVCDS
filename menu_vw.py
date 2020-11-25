import menu
import struct
import vw
import kwp
import vwtp
import queue

def mod_menu(car):
  mod = menu.dselector({k:v for k,v in vw.modules.items() if k in car.enabled }, "Which Module?")
  mod = car.module(int(mod))
  with mod as m:
    while True:
      op = menu.selector(["Read Module ID", "Read Manufacturer Info", "Read Firmware Version", "Read Coding", "Re-Code module (EXPERIMENTAL)", "Read Measuring Block", "Load Labels for Module", "Drop to Python Console", "Back"])
      if op == 0:
        try:
          print(m.readID())
        except kwp.ENOENT:
          print("Module ID measuring block not supported")
      if op == 1:
        print(m.readManufactureInfo())
      if op == 2:
        print(m.readFWVersion())
      if op == 3:
        print("Not Yet Implemented")
      if op == 4:
        raise NotImplementedError("Writing module coding is currently unavailable")
      if op == 5:
        raise NotImplementedError("Reading measuring blocks from the menu is currently unsupported")
      if op == 6:
        if not m.pn: #we need to know the part number of the ECU before we can know it's label file.
          m.readPN()
        path = input("Enter label directory path:\n> ")
        vw.labels.setpath(path)
        if m.pn in vw.labels: #there's more to this behind the scenes; it will transparently attempt to load labels on the fly when called for
          print("Loaded")
        else:
          print("Error loading labels: missing or encrypted label file") #again, I *WILL NOT HELP* with decrypting clb labels.
      if op == 7:
        import pdb; pdb.set_trace()
      if op == 8:
        break

def main(sock):
    with vwtp.VWTPStack(sock) as stack, vw.VWVehicle(stack) as car: #host the connection outside the menu loop.
      while True:
        opt = ["Enumerate Modules", "Connect to Module", "Read DTCs by module", "Read Measuring Data Block by module", "Long-Coding", "Load Labels from VCDS", "Load Labels from JSON", "Back"]
        op = menu.selector(opt)
        if op == 0:
          print("Enumerating modules, please wait")
          car.enum()
          print("Modules Available:")
          for mod in car.enabled:
            print(" " + car.parts[mod]) #pre-formatted string.
        elif op == 1: #Connect to Module
          if not car.scanned:
            print("Enumerating modules, please wait")
            car.enum()
          mod_menu(car)
        elif op == 2:
          if not car.scanned:
            car.enum()
          for mod in car.enabled:
            print("Checking module '{}'".format(vw.modules[mod]))
            try:
              with car.module(mod) as m:
                dtc = m.readDTC()
                if len(dtc) > 0:
                  print("Found DTCs:")
                else:
                  print("No Faults detected")
                for d in dtc:
                  if d in vw.labels[module]["dtc"]:
                    print(vw.labels[module]["dtc"][d])
                  else:
                    print("Unknown DTC '{}'".format(d))
            except kwp.EPERM:
              print("Permissions error getting DTCs from module, skipping")
            except (ValueError, queue.Empty, kwp.KWPException) as e:
              print("Unknown fault getting DTCs from module:",e)
        elif op == 3: #read measuring block
          mods = {}
          for i in car.enabled:
            mods[i] = vw.modules[i]
          op2 = dselector(mods)
          with car.module(mod) as mod:
            blk = menu.dselector(vw.labels[module]["blocks"])
            blk = mod.readBlock(blk)
            for b in blk:
              print(b)
        elif op == 4: #long-code
          raise NotImplementedError("Need a CAN trace of someone with VCDS reading or writing a long-code")
        elif op == 5:
          raise NotImplementedError("VCDS Label parsing has not yet been implemented")
        elif op == 6:
          print("Path to the JSON file?")
          path = input("> ")
          fd = open(path, "r")
          js = fd.read()
          fd.close()
          vw.loadLabelsFromJSON(js)
        elif op == 7:
          return
