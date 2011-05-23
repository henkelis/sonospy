#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

import hashlib
import uuid
import random
import os
import thread
import time

def md5_hash(text):
    """ Generate a md5 hash with the given text """

    return hashlib.md5(text).hexdigest()


def hash(text, digest_alg = 'md5'):
    """
    Generates hash with the given text using the specified
    digest hashing algorithm
    """
    if not isinstance(digest_alg,str):
        h = digest_alg(text)
    else:
        h = hashlib.new(digest_alg)
        h.update(text)
    return h.hexdigest()

def get_digest(value):
    """
    Returns a hashlib digest algorithm from a string
    """
    if not isinstance(value,str):
        return value
    value = value.lower()
    if value == "md5":
        return hashlib.md5
    elif value == "sha1":
        return hashlib.sha1
    elif value == "sha224":
        return hashlib.sha224
    elif value == "sha256":
        return hashlib.sha256
    elif value == "sha384":
        return hashlib.sha384
    elif value == "sha512":
        return hashlib.sha512
    else:
        raise ValueError("Invalid digest algorithm")

web2py_uuid_locker = thread.allocate_lock() 
node_id = uuid.getnode()
milliseconds = int(time.time() * 1e3)

def rotate(i):
    a = random.randrange(256)
    b = (node_id >> 4*i) % 256
    c = (milliseconds >> 4*i) % 256
    return (a + b + c) % 256

def web2py_uuid():
    web2py_uuid_locker.acquire()    
    try:
        bytes = [chr(rotate(i)) for i in range(16)]
        return str(uuid.UUID(bytes=bytes, version=4))
    finally:
        web2py_uuid_locker.release()
