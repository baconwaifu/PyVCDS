#!/usr/bin/env python3
import binascii
import Crypto.Cipher as Cipher

#Some shared AES keys, usually for firmware/calibration encryption, possibly challenge-response in some cases?
#Keys are represented as a tuple with an implicit number of elements (to type of key)
#for AES, this is (key, iv), or (key,) for null IV. same for other "trivially" symmetric algorithms.
#for signature algorithms however, key format is a little different. those simply store the "protocol-serialized" pubkey.
#and in cases the privkey is known (such as due to a sony-level nonce-reuse fuckup with ECDSA) it shall be the second element of the
#tuple.

#a: Infineon TriCore ECU firmware encryption key/iv.
simos18 = {
 "a": (binascii.unhexlify('98D31202E48E3854F2CA561545BA6F2F'), binascii.unhexlify('E7861278C508532798BCA4FE451D20D1'))
}

def encrypt_aes(dat, key):
  cipher = Cipher.AES.new(key, Cipher.AES.MODE_CBC, iv)
  return cipher.encrypt(dat)
  
def decrypt_aes(dat, key):
  cipher = Cipher.AES.new(key, Cipher.AES.MODE_CBC, iv)
  return cipher.decrypt(dat)
