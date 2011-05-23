#!/usr/bin/env python 
# coding: utf8

import re
import unicodedata

def urlify(s, max_length=80):
    s = s.lower()
    # string normalization, eg è => e, ñ => n
    s = unicodedata.normalize('NFKD', s.decode('utf-8')).encode('ASCII', 'ignore')
    # strip entities
    s = re.sub('&\w+;', '', s)
    # strip everything but letters, numbers, dashes and spaces
    s = re.sub('[^a-z0-9\-\s]', '', s)
    # replace spaces with dashes
    s = s.replace(' ', '-')
    # strip multiple contiguous dashes
    s = re.sub('-{2,}', '-', s)
    # strip dashes at the beginning and end of the string
    s = s.strip('-')
    # ensure the maximum length
    s = s[:max_length-1]
    return s
