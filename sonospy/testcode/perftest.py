#!/usr/bin/python
# -*- encoding: utf8 -*-
import os
import sys
import sqlite3
import time

chunksize = 100

counts = [
#            '''select count(distinct albumartist) from tracks''',
            '''select count(1) from tracks''',
          ]
limitqueries = [
#            '''select 'albumartist' as recordtype, rowid, albumartist from tracks %s group by albumartist order by albumartist %s''',
            '''select title, albumartist, album from tracks %s order by title %s''',
          ]
blockqueries = [
#            '''select 'albumartist' as recordtype, rowid, albumartist from tracks %s group by albumartist order by albumartist %s''',
            '''select title, albumartist, album from tracks %s order by block %s''',
          ]
columndetails = [
#                    (2, 'albumartist'),
                    (0, 'title'),
                ]

db1 = sqlite3.connect('mark')
cs1 = db1.cursor()

for countquery, selectquery in zip(counts, limitqueries):
    print countquery
    print selectquery
    cs1.execute(countquery)
    recordcount, = cs1.fetchone()
    print recordcount
    count = 0
    iterations = recordcount / chunksize
    for i in range(iterations):
#        sys.stderr.write(str(count) + "\r")
#        sys.stderr.flush()
        chunkquery = selectquery % ('', 'limit %s, %s' % (count, chunksize))
        start = time.time()
        cs1.execute(chunkquery)
        diff = time.time() - start
        print '%6f - %6i - %s' % (diff, count, chunkquery.encode('utf-8'))
        count += chunksize

for countquery, selectquery, coldets in zip(counts, blockqueries, columndetails):
    print countquery
    print selectquery
    cs1.execute(countquery)
    recordcount, = cs1.fetchone()
    print recordcount
    colnum, colname = coldets
    count = 0
    iterations = recordcount / chunksize
    for i in range(iterations):
#        sys.stderr.write(str(count) + "\r")
#        sys.stderr.flush()
        if count == 0:
            chunkquery = selectquery % ('', 'limit %s' % (chunksize))
        else:
            chunkquery = selectquery % ("where block >= %s and block < %s" % (count, count + chunksize), '')
        start = time.time()
        cs1.execute(chunkquery)
        diff = time.time() - start
        print '%6f - %6i - %s' % (diff, count, chunkquery.encode('utf-8'))
        
        last = cs1.fetchall()[-1][colnum].replace("'","''")
        count += chunksize

cs1.close()

