def selector(lst):
  while True:
    try:
      print("Do What?")
      for i in range(len(lst)):
        print("{}: {}".format(i,lst[i]))
      iput = input("> ")
      ret = int(iput)
      if ret < len(lst):
        return ret
    except ValueError:
      print("Enter the integer value of the selected option")

def dselector(dct, header="Do What?"):
  while True:
    try:
      print(header)
      for k,v in dct.items():
        print("{}: {}".format(k,v))
      ret = input("> ")
      if ret in dct or int(ret) in dct: #some of these use integer keys instead of strings
        return ret
    except ValueError:
      print("Enter the integer value of the selected option")
