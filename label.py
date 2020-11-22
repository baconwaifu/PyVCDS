#!/usr/bin/env python3

import re
import io
import threading
#the *hooks* for loading CLB labels exist, but clb.py will *NEVER* be released. write your own.
try:
  import clb
except ImportError:
  clb = None
BASEDIR = "."

#Ross-Tech label parser

#Label Format regexes:
#'[0-9]{3},[0-5],[a-zA-Z]{1,}' is a measuring block.
#'B[0-9]{3},[0-5],[a-zA-Z]{1,}' is a basic setting.
#'L[0-9]{2},' is a "Login/Coding 2" entry. exact format unknown. 'L00' is "segment name"
#'C[0-9]{2},' is a "Coding" entry. exact format unknown. 'C00' is "segment name"
# ';' is a comment.

#the latter are for the "coding helper" functionality, which will not be replicated, so they can be
#noped

#Class for lazy-loading label trees at runtime. are optionally flushed out to a JSON file when a new label is inserted or loaded.
#note: due to *my* laziness, iterators will remain unimplemented.
#iteration over "all labeled parts" would be mostly useless.
class LazyLabel:
  def __init__(self, d=None, parent=None, pn=None):
    self.loader = LBLLoader #note; this is a *TYPE*
    self.backing = d
    self.p = parent
    self.pn = pn #kept around on block nodes just in case.
    self.lock = threading.Lock()
    with self.lock:
      if self.p and d:
        for k,v in self.backing.items(): #convert dictionaries into lazy label nodes.
          if type(v) is dict:
            self.backing[k] = LazyLabel(v, self)

  def flush(self): #used to flush to a util.Config (like) object. is a no-op without a top-level object implementation.
    if p: #we need a parent object to propagate the flush to!
      with p.lock: #to serialize writes up the tree.
        p.flush()
    else:
      util.log(3,"LazyLabel has no parent storage?") #warn if we try to flush to nothing.

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

blkmatch = re.compile('[0-9]{3}')

class LBLLoader:

  #technically, these are non-compliant, since they support nested redirects.
  @staticmethod
  def loadLabel(pn, fname):
    global blkmatch #a regex matcher for measuring blocks.
    suffix = pn.split("-")[-1]
    labels = {}
    with open(fname, "r") as fd:
      for line in fd.readlines():
        l = line.split(';')[0] #drop any comments.
        tok = l.split(',') #split the CSV...
        if tok[0] == "REDIRECT":
          file = tok[1]
          if suffix in tok[2:]:
            if file.toLower().endsWith(".clb"):
              return CLBLoader.loadLabel(pn, file)
            return loadLabel(pn, file) #found a redirect, load the labels from that.
        else: #new and old-style labels are identical here.
          if tok[0][0] == 'B': #basic setting.
            assert blkmatch.match(tok[0][1:]), "Invalid basic-settings label line?"
          elif tok[0][0] == 'A': #Adaption. useful.
            assert blkmatch.match(tok[0][1:]), "Invalid adaption line?"
          elif tok[0][0] == 'L': #we don't care about the coding helper. also picks up 'LC' (Long-Code)
            pass
          elif tok[0][0] == 'C': #also coding
            pass
          elif tok[0][0] == 'O':
            util.log(4,"Label file inclusion not implemented; used for partially-obfuscated labels?")
          else: #measuring block
            assert blkmatch.match(tok[0]), "Invalid Label Line?"
            blk = int(tok[0],16)
            if not blk in labels:
              labels[blk] = {}
            measure = int(tok[1])
            if measure == 0:
              labels[blk]["name"] = tok[2]
            else:
              labels[blk][measure  -1] = (tok[2],tok[3])
    if len(labels) == 0:
      return None
    return labels

  @staticmethod
  def loadNewLabel(pn, fname): #"New" ross-tech labels, uses the newer redirect method
    global blkmatch #a regex matcher for measuring blocks.
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
            if file.toLower().endsWith(".clb"): #use the CLB loader for CLBs.
              return CLBLoader.loadLabel(pn, file)
            return loadLabel(pn, file) #VCDS only supports a single-layer redirect, so punting to the old one is fine.
        else: #not a redirect.
          if tok[0][0] == 'B': #basic setting.
            assert blkmatch.match(tok[0][1:]), "Invalid basic-settings label line?"
            
          elif tok[0][0] == 'L': #we don't care about the coding helper.
            pass
          elif tok[0][0] == 'C': #also coding
            pass
          else: #measuring block
            assert blkmatch.match(tok[0]), "Invalid Label Line?"
            blk = int(tok[0],16)
            if not blk in labels:
              labels[blk] = {}
            measure = int(tok[1])
            if measure == 0:
              labels[blk]["name"] = tok[2]
            else:
              labels[blk][measure  -1] = (tok[2],tok[3])
    if len(labels) == 0:
      return None
    return labels

if not clb: #load a placeholder "not implemented" stub
  class CLBLoader:
    @staticmethod
    def loadLabel(pn, fname):
      raise NotImplementedError("CLB files are encrypted *for a reason*")
    @staticmethod
    def loadNewLabel(pn, fname):
      raise SyntaxError("CLB files cannot contain new-style labels")
else: #load the real deal from an external plugin
  from clb import CLBLoader

def getPath(pn, addr, basedir=BASEDIR):
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
