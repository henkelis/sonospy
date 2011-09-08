import sqlite3
import sys

def cleartags(tags):
    id, \
    title, artist, album, \
    genre, track, year, \
    albumartist, composer, codec,  \
    length, size,  \
    lastmodified, path, filename,  \
    discnumber, comment, cover,  \
    bitrate, samplerate,  \
    bitspersample, channels, mime,  \
    currenttime, upnpclass, scannumber = tags
    tags = (id,
            '', '', '',
            '', '', '',
            '', '', '', 
            '', '', 
            '', path, filename, 
            '', '', '', 
            '', '',
            '', '', '', 
            '', '', scannumber)
    return tags
    
db = sqlite3.connect('temp.db1')
c = db.cursor()

c.execute('''create table scans (id integer primary key autoincrement,
                                 scanpath text)
          ''')
c.execute('''create unique index inxScans on scans (id)''')

c.execute('''create table tags (id integer primary key autoincrement,
                                title text, artist text, album text,
                                genre text, track text, year text,
                                albumartist text, composer text, codec text,
                                length text, size text,
                                lastmodified text, path text, filename text,
                                discnumber text, comment text, cover text,
                                bitrate text, samplerate text, 
                                bitspersample text, channels text, mime text,
                                lastupdated text, upnpclass text, 
                                scannumber integer)
          ''')
c.execute('''create unique index inxTagsPathFile on tags (path, filename)''')
c.execute('''create unique index inxTags on tags (id)''')
c.execute('''create index inxTagsScannumber on tags (scannumber)''')

c.execute('''create table tags_update (id integer,
                                       title text, artist text, album text,
                                       genre text, track text, year text,
                                       albumartist text, composer text, codec text,
                                       length text, size text,
                                       lastmodified text, path text, filename text,
                                       discnumber text, comment text, cover text,
                                       bitrate text, samplerate text, 
                                       bitspersample text, channels text, mime text,
                                       lastupdated text, upnpclass text,
                                       scannumber integer, updateorder integer, updatetype text)
          ''')
c.execute('''create unique index inxTagsDeleteIdScanUpdate on tags_update (id, scannumber, updateorder)''')
c.execute('''create index inxTagsDeleteScannumber on tags_update (scannumber)''')

c.execute('''insert into scans values (?,?)''', (None, 'path'))

for i in range(100000):
    out = "processing file: " + str(i) + "\r" 
    sys.stderr.write(out)
    sys.stderr.flush()

    tags = (None,
            '%10i' % i, 'artist', 'album',
            'genre', i, '2010',
            'albumartist', 'composer', 'codec', 
            120.0, 1000000, 
            1, 'path', str(i)+'flac', 
            1, 'comment', '', 
            200000, 48000,
            16, 2, 'audio/flac', 
            2, 'object.item.audioItem.musicTrack', 1)
    c.execute("""insert into tags values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tags)
    # create audit records
    tags = (c.lastrowid, ) + tags[1:]
    # pre
    itags = cleartags(tags)
    itags += (0, 'I')
    c.execute("""insert into tags_update values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", itags)
    # post
    tags += (1, 'I')
    c.execute("""insert into tags_update values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tags)

db.commit()
c.close()
exit()


