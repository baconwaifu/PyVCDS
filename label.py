#!/usr/bin/env python3

import re
import io

#Ross-Tech label parser

#Class for lazy-loading label trees at runtime. are optionally flushed out to a JSON file when a new label is inserted or loaded.
#note: due to laziness, iterators will remain unimplemented until loading is implemented.
#the "lazy" to iterators is loading keys (and relevant child metadata) but leaving "dummy" objects as `v` in (k,v)
#until it's actually accessed, at which point the information is loaded on-demand, or all at once (whichever is more efficient)
class LazyLabel:
  def __init__(self, d=None, parent=None, pn=None):
    self.backing = d
    self.p = parent
    self.pn = pn #kept around on block nodes just in case.
    self.lock = threading.Lock()
    with self.lock:
      if self.p and d:
        for k,v in self.backing.items():
          if type(v) is dict:
            self.backing[k] = LazyLabel(v, self)

  def flush(self): #used to flush to a util.Config (like) object. is a no-op without a top-level object implementation.
    if p:
      with p.lock: #to serialize writes up the tree.
        p.flush()

  def __getitem__(self, idx):
    if idx in self.backing:
      return self.backing[idx] #cached result, short-circuit.
    else:
      if self.p:
        raise KeyError("Label exists, but not that specific block") #we're a module node, toss a KeyError
      else: #we're the root node, so find a matching label file.
        lbl = getPath(idx, 0)
        if lbl == None:
          raise KeyError("Label file not found")
        else:
          self[idx] = lbl #set and trigger a flush
      return self[idx]

  def __len__(self): #FIXME: abstract the lazy?
    return self.backing.__len__()

  def __contains__(self, item): #FIXME: abstract the lazy?
    v = self.backing.__contains__(item)
    if v:
      return True
    try:
      if self.__getitem__(item): #only way to check is to try!
        return True
    except KeyError:
      pass
    return False

  def __setitem__(self, idx, val): 
    if self.p and type(val) is dict: #measuring-block dicts get converted to lazy label objects for flushing on change.
      val = LazyLabel(val, self, idx)
    with self.lock:
      self.backing[idx] = val
      self.flush()


#technically, these are non-compliant, since they support nested redirects.
def loadLabel(pn, fname):
  suffix = pn.split("-")[-1]
  labels = {}
  with open(fname, "r") as fd:
    for line in fd.readlines():
      l = line.split(';')[0] #drop any comments.
      tok = l.split(',')
      if tok[0] == "REDIRECT":
        file = tok[1]
        if suffix in tok[2:]:
          return findLabel(pn, file) #found a redirect, load the labels from that.
      else:
        blk = int(tok[0],16)
        if not blk in labels:
          labels[blk] = {}
        measure = int(tok[1])
        if measure == 0:
          labels[blk]["name"] = tok[2]
        else:
          labels[blk][measure - 1] = (tok[2],tok[3])
  return labels

def loadNewLabel(pn, fname): #"New" ross-tech labels, uses the newer redirect method
  raise NotImplementedError("New-style labels are unsupported")
  suffix = pn.split("-")[-1]
  labels = {}
  with open(fname, "r") as fd:
    for line in fd.readlines():
      l = line.split(';')[0] #drop any comments.
      tok = l.split(',')
      if tok[0] == "REDIRECT":
        file = tok[1]
        patt = tok[2]
        patt = patt.replace("?", "[A-Z0-9]") #replace the VCDS "wildcard" with an equivalent regex stub
        patt = re.compile(patt)
        if patt.match(pn): #found a redirect, load the labels from that
          return findLabel(pn, file) #VCDS only supports a single-layer redirect, so punting to the old one is fine.
      else:
        blk = int(tok[0],16)
        if not blk in labels:
          labels[blk] = {}
        measure = int(tok[1])
        if measure == 0:
          labels[blk]["name"] = tok[2]
        else:
          labels[blk][measure  -1] = (tok[2],tok[3])
  return labels

def getPath(pn, addr, basedir="./Labels"):
    path = os.path.join(basedir,"TEST-"+hex(self.idx)[2:]+".LBL") #TEST-AA.LBL
    if os.path.exists(path):
      return loadLabel(pn, path)
    path = os.path.join(basedir,part+".LBL") #XXX-XXX-XXX-XX.LBL
    if os.path.exists(path):
      return loadLabel(pn, path)
    path = os.path.join(basedir,part[:12]+".LBL") #drop the suffix letters
    if os.path.exists(path):
      return loadLabel(pn, path)
    path = os.path.join(basedir,part[:2]+"-"+hex(self.idx)[2:]+".LBL") #AA-XX.LBL
    if os.path.exists(path):
      return loadNewLabel(pn, path) #Note: this uses new-style redirects.
    return None #no known label.
