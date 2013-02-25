#!/usr/bin/python
# -*- encoding: utf8 -*-
import os
import sys
import sqlite3
import locale
locale.setlocale(locale.LC_ALL, "")

db = sqlite3.connect(':memory:')

db.create_collation('NOCASE', locale.strcoll)

c = db.cursor()

c.execute('''create table Albumartist (id integer primary key autoincrement,
                                       albumartist text COLLATE NOCASE, 
                                       lastplayed integer,
                                       playcount integer)
          ''')
c.execute('''create unique index inxAlbumartists on Albumartist (albumartist)''')

# seed autoincrement
c.execute('''insert into Albumartist values (200000000,'','','')''')
c.execute('''delete from Albumartist where id=200000000''')

corpus = [u"Art", u"Älg", u"Ved", u"Wasa"]

for i in range(4):
    c.execute('''insert into Albumartist values (?, ?, ?, ?)''', (None, corpus[i], 0, 0))

c.execute('''select albumartist from Albumartist order by albumartist''')

for row in c:
    print row[0].encode('utf-8')

