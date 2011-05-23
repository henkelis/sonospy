import os
import sys
import sqlite3
import csv

def unicode_csv_reader(unicode_csv_data, dialect=csv.excel, **kwargs):
    # csv.py doesn't do Unicode; encode temporarily as UTF-8:
    csv_reader = csv.reader(utf_8_encoder(unicode_csv_data),
                            dialect=dialect, **kwargs)
    for row in csv_reader:
        # decode UTF-8 back to Unicode, cell by cell:
        yield [unicode(cell, 'utf-8') for cell in row]

def utf_8_encoder(unicode_csv_data):
    for line in unicode_csv_data:
        if type(line) is unicode:
            line = line.encode('utf-8')
        yield line    
#        yield line.encode('utf-8')

def check_drop(dtype, name):
    select = 'SELECT count(*) FROM sqlite_master WHERE type="%s" AND name="%s"' % (dtype, name)
    drop = 'drop %s %s' % (dtype, name)
    c.execute(select)
    n, = c.fetchone()
    if n == 1:
        c.execute(drop)

def convert_path(path):
    filepath = path
    filepath = filepath.replace(path_before, path_after)
    filepath = filepath.replace(path_delim_before, path_delim_after)
    return filepath


if len(sys.argv) < 7:
    try:
        csvname = raw_input('csv filename >>> ')
        dbname = raw_input('database filename >>> ')
        path_before = raw_input('path before >>> ')
        path_after = raw_input('path after >>> ')
        path_delim_before = raw_input('path delim before >>> ')
        path_delim_after = raw_input('path delim after >>> ')
        the_processing = raw_input('"the" processing (before, after, remove) >>> ')
    except KeyboardInterrupt, EOFError:
        exit()
else:
    csvname = sys.argv[1]
    dbname = sys.argv[2]
    path_before = sys.argv[3]
    path_after = sys.argv[4]
    path_delim_before = sys.argv[5]
    path_delim_after = sys.argv[6]
    the_processing = sys.argv[7]

print csvname
print dbname
print path_before
print path_after
print path_delim_before
print path_delim_after
print the_processing

db = sqlite3.connect(os.path.join(os.getcwd(), dbname))

c = db.cursor()

#Title|Artist|Album|Genre|Track|Year|Album Artist|Composer|Codec|Tag|Length|Size|Last Modified|Path|Filename|Disc Number|Comment|Cover|Bitrate|Frequency

try:
    # tracks - contain all detail from tags
    check_drop('table','tracks')
    check_drop('index','inxTracks')
    check_drop('index','inxTrackId')
    check_drop('index','inxTrackTitles')
    check_drop('index','inxTrackAlbums')
    check_drop('index','inxTrackArtists')
    check_drop('index','inxTrackAlbumArtists')
    check_drop('index','inxTrackComposers')
    c.execute('''create table tracks (id text, parentID text, 
                                      title text, artist text, album text,
                                      genre text, track integer, year text,
                                      albumartist text, composer text, codec text,
                                      tag text, length text, size text,
                                      lastmodified text, path text, filename text,
                                      discnumber text, comment text, cover text,
                                      bitrate text, frequency text,
                                      res text, protocol text, upnpclass text)
              ''')
    c.execute('''create unique index inxTracks on tracks (title, album, artist, track)''')
    c.execute('''create unique index inxTrackId on tracks (id)''')
    c.execute('''create index inxTrackTitles on tracks (title)''')
    c.execute('''create index inxTrackAlbums on tracks (album)''')
    c.execute('''create index inxTrackArtists on tracks (artist)''')
    c.execute('''create index inxTrackAlbumArtists on tracks (albumartist)''')
    c.execute('''create index inxTrackComposers on tracks (composer)''')

    # artists - one entry for each unique artist/albumartist combination from tracks list
    #           view for unique artists and albumartists
    check_drop('table','artists')
    check_drop('view','artistalbumartists')
    check_drop('index','inxArtists')
    check_drop('index','inxArtistId')
    check_drop('index','inxArtistArtists')
    check_drop('index','inxArtistAlbumArtists')
    check_drop('index','inxArtistGenres')
    c.execute('''create table artists (id text, parentID text, 
                                       artist text,
                                       genre text, 
                                       albumartist text, 
                                       upnpclass text)
              ''')
    c.execute('''create view artistalbumartists as 
                    select id, parentID, albumartist as artist, genre, artist as albumartist, upnpclass from artists where albumartist != "" 
                    union
                    select id, parentID, artist, genre, artist as albumartist, upnpclass from artists where albumartist = ""''') 
    c.execute('''create unique index inxArtists on artists (artist, albumartist, genre)''')
    c.execute('''create unique index inxArtistId on artists (id)''')
    c.execute('''create index inxArtistArtists on artists (artist)''')
    c.execute('''create index inxArtistAlbumArtists on artists (albumartist)''')
    c.execute('''create index inxArtistGenres on artists (genre)''')

    # composers - one entry for each unique composer from tracks list
    check_drop('table','composers')
    check_drop('index','inxComposers')
    check_drop('index','inxComposerId')
    check_drop('index','inxComposerGenres')
    c.execute('''create table composers (id text, parentID text, 
                                       composer text,
                                       genre text, 
                                       upnpclass text)
              ''')
    c.execute('''create unique index inxComposers on composers (composer)''')
    c.execute('''create unique index inxComposerId on composers (id)''')
    c.execute('''create index inxComposerGenres on composers (genre)''')

    # genres - one entry for each unique genre from tracks list
    check_drop('table','genres')
    check_drop('index','inxGenres')
    check_drop('index','inxGenreId')
    c.execute('''create table genres (id text, parentID text, 
                                      genre text,
                                      upnpclass text)
              ''')
    c.execute('''create unique index inxGenres on genres (genre)''')
    c.execute('''create unique index inxGenreId on genres (id)''')
    
    # playlists
    check_drop('table','playlists')
    check_drop('index','inxPlaylists')
    check_drop('index','inxPlaylistId')
    c.execute('''create table playlists (id text, parentID text, 
                                         playlist text,
                                         path text,
                                         upnpclass text)
              ''')
    c.execute('''create unique index inxPlaylists on playlists (playlist)''')
    c.execute('''create unique index inxPlaylistId on playlists (id)''')
    
    # albums - one entry for each unique album/artist/albumartist/composer combination from tracks list
    #          view for source for album in list
    check_drop('table','albums')
    check_drop('view','albumalbumartists')
    check_drop('index','inxAlbums')
    check_drop('index','inxAlbumId')
    check_drop('index','inxAlbumAlbumArtists')
    check_drop('index','inxAlbumGenres')
    check_drop('index','inxAlbumComposers')
    check_drop('index','inxAlbumYears')
    c.execute('''create table albums (id text, parentID text, 
                                      album text, 
                                      artist text,
                                      genre text, 
                                      year text,
                                      albumartist text, 
                                      composer text,
                                      path text, 
                                      cover text,
                                      source text,
                                      upnpclass text)
              ''')
    c.execute('''create view albumalbumartists as 
                    select id, parentID, album, albumartist as artist, genre, year, artist as albumartist, composer, path, cover, "AA" as source, upnpclass from albums where albumartist != "" 
                    union
                    select id, parentID, album, artist, genre, year, artist as albumartist, composer, path, cover, "A" as source, upnpclass from albums where albumartist = ""''') 
    c.execute('''create unique index inxAlbums on albums (album, artist, albumartist, composer, path)''')
    c.execute('''create unique index inxAlbumId on albums (id)''')
    c.execute('''create index inxAlbumAlbums on albums (album)''')
    c.execute('''create index inxAlbumArtists on albums (artist)''')
    c.execute('''create index inxAlbumAlbumArtists on albums (albumartist)''')
    c.execute('''create index inxAlbumComposers on albums (composer)''')
    c.execute('''create index inxAlbumGenres on albums (genre)''')
    c.execute('''create index inxAlbumYears on albums (year)''')

except sqlite3.Error, e:
    print "Error creating database:", e.args[0]

artist_id = 1000001
artist_parentid = 1000000

album_id = 3000001
album_parentid = 3000000

composer_id = 4000001
composer_parentid = 4000000

genre_id = 5000001
genre_parentid = 5000000

track_id = 6000001
track_parentid = 6000000

playlist_id = 7000001
playlist_parentid = 7000000

csvreader = unicode_csv_reader(open(os.path.join(os.getcwd(), csvname), 'rb'), delimiter='|', quotechar='"')

try:
    count = 1
    for row in csvreader:
#        print row
        out = "processing row: " + str(count) + "\r" 
        sys.stdout.write(out)
        sys.stdout.flush()
        try:
            title, artist, album, genre, track, year, albumartist, composer, codec, tag, length, size, lastmodified, path, filename, discnumber, comment, cover, bitrate, frequency = row
        except:
            print "Error reading csv: ", sys.exc_info()[0]
            print "Row: ", row
#        if title == '': continue
#        if artist == '' and album == '': continue

        if the_processing == 'after' or the_processing == 'remove':
            if artist.lower().startswith("the ") and artist.lower() != "the the":
                postartist = artist[4:]
                if the_processing == 'after':
                    preartist = artist[0:3]
                    artist = postartist + ", " + preartist
                else: # 'remove'
                    artist = postartist

        try:
            track = int(track.split('/')[0])
        except ValueError:
            pass
        except AttributeError:
            pass
            
        path = convert_path(path)
        file_path = os.path.join(path, filename)
        if not os.path.isfile(file_path):
            print "File not found, ignored: " + file_path
            continue
        covername = ''
        for name in ('folder.jpg', 'Folder.jpg', 
                     'folder.png', 'Folder.png', 
                     'folder.bmp', 'Folder.bmp',
                     'folder.gif', 'Folder.gif',
                     'cover.jpg', 'Cover.jpg', 
                     'cover.png', 'Cover.png', 
                     'cover.bmp', 'Cover.bmp',
                     'cover.gif', 'Cover.gif'):
            cover_path = os.path.join(path, name)
            if os.path.isfile(cover_path):
                covername = name
                break
        cover = ''
        if covername != '':
            cover = cover_path
#            print cover

        res = ''
        protocol = ''
        upnpclass = 'object.item.audioItem.musicTrack'

        tracks = (str(track_id), str(track_parentid), title, artist, album, genre, str(track), year, albumartist, composer, codec, tag, length, size, lastmodified, path, filename, discnumber, comment, cover, bitrate, frequency, res, protocol, upnpclass)
#        print out
        try:
            c.execute('insert into tracks values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tracks)
            track_id += 1
        except sqlite3.Error, e:
#            print "Error inserting track (first duplicate) '" + str((tracks[3], tracks[4], tracks[5])) + "' :", e.args[0]
            tcount = 2
            while True:
                tstring = title + " (" + str(tcount) + ")"            
                tracks = (str(track_id), str(track_parentid), tstring, artist, album, genre, str(track), year, albumartist, composer, codec, tag, length, size, lastmodified, path, filename, discnumber, comment, cover, bitrate, frequency, res, protocol, upnpclass)
                try:
                    print tstring
                    c.execute('insert into tracks values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tracks)
                    track_id += 1
                    break
                except sqlite3.Error, e:
#                    print "Error inserting track (second duplicate) '" + str(tracks) + "' :", e.args[0]
                    tcount += 1

        albums = (str(album_id), str(album_parentid), album, artist, genre, year, albumartist, composer, path, cover, '', 'object.container.album.musicAlbum')
        try:
            c.execute('insert into albums values (?,?,?,?,?,?,?,?,?,?,?,?)', albums)
            album_id += 1
        except sqlite3.Error, e:
            pass
#            print "Error inserting album:", e.args[0]

        artists = (str(artist_id), str(artist_parentid), artist, genre, albumartist, 'object.container.person.musicArtist')
        try:
            c.execute('insert into artists values (?,?,?,?,?,?)', artists)
            artist_id += 1
        except sqlite3.Error, e:
            pass
#            print "Error inserting artist:", e.args[0]

        composers = (str(composer_id), str(composer_parentid), composer, genre, 'object.container.person.musicArtist')
        try:
            c.execute('insert into composers values (?,?,?,?,?)', composers)
            composer_id += 1
        except sqlite3.Error, e:
            pass
#            print "Error inserting composer:", e.args[0]

        genres = (str(genre_id), str(genre_parentid), genre, 'object.container.genre.musicGenre')
        try:
            c.execute('insert into genres values (?,?,?,?)', genres)
            genre_id += 1
        except sqlite3.Error, e:
            pass
#            print "Error inserting genre:", e.args[0]
        count += 1
        
except csv.Error, e:
    print ('Error reading CSV - line %d: %s' % (count, e))

db.commit()

c.close()


