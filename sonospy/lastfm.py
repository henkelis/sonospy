# -*- coding: utf-8 -*- 
import urllib
import time
import sqlite3
from xml.etree.ElementTree import Element, SubElement, dump
from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree
from brisa.core.network import parse_xml

def process_first(xml):
    elt = parse_xml(xml)
    elt = elt.getroot()
    pages = 0
    if elt.tag == 'lfm' and elt.get('status') == "ok":
        rt = elt.find('recenttracks')
        pages = int(rt.get('totalPages'))
    return pages
            
def process_page(xml):
    elt = parse_xml(xml)
    elt = elt.getroot()
    if elt.tag == 'lfm' and elt.get('status') == "ok":
        rt = elt.find('recenttracks')
        tracks = []
        for trackentry in rt.findall('track'):
            track = artist = album = date = ''
            ar = trackentry.find('artist')
            if ar != None:
                artist = ar.text
            tr = trackentry.find('name')
            if tr != None:
                track = tr.text
            al = trackentry.find('album')
            if al != None:
                album = al.text
            da = trackentry.find('date')
            if da != None:
                date = da.text
                ptime = da.get('uts')
            tracks.append((ptime, track, album, artist))
        return tracks
    else:
        return None
            
def main():

    url = 'http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks'
    user = '&user=henkelis'
    limit = '&limit=200'
    key = '&api_key=56a785a0b5f93faf62f3a120ddadba68'
    firstcallurl = '%s%s%s%s' % (url, user, limit, key)

    db = sqlite3.connect('lastfmplays.db')
    cs = db.cursor()
    cs.execute('''drop table if exists plays''')
    cs.execute('''create table plays (playtime float, zone text, service text, title text, artist text, album text, duration integer, uri text, uriname text, database text, processed boolean)''')
    cs.execute('''create index inxPlaysTime on plays (playtime)''')

    try:
        xml = urllib.urlopen(firstcallurl).read()
        pages = process_first(xml)
        print pages
        for i in range(pages):
            page = '&page=%d' % (i+1)
            pagecallurl = '%s%s%s%s%s' % (url, user, limit, page, key)
            cont = False
            for j in range(10):
                time.sleep(1)
                xml = urllib.urlopen(pagecallurl).read()
                out = process_page(xml)
                if not out:
                    continue
                for line in out:
                    print line
                    ptime, track, album, artist = line
                    cs.execute('insert into plays values (?,?,?,?,?,?,?,?,?,?,?)', (ptime, '', '', track, artist, album, '', '', '', '', 0))
                cont = True
                break
            if not cont:
                break
    except IOError:
        xml = ''

    db.commit()
    cs.close()

if __name__ == "__main__":
    main()
