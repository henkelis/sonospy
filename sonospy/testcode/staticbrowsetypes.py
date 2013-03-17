
# root alpha queries

browsetype == '!ALPHAalbumartist'
browsetype == '!ALPHAartist'
browsetype == '!ALPHAcomposer'
browsetype == '!ALPHAalbum'
browsetype == '!ALPHAgenre'
browsetype == '!ALPHAplaylist'
browsetype == '!ALPHAtrack'

# root list queries, are containers

browsetype == 'albumartist'
browsetype == 'artist'
browsetype == 'composer'
browsetype == 'album'
browsetype == 'genre'
browsetype == 'playlist'
browsetype == 'track'

# second level list queries

browsetype == 'albumartist:album'
browsetype == 'artist:album'
browsetype == 'composer:album'

browsetype == 'genre:albumartist'
browsetype == 'genre:artist'

# third level list queries

browsetype == 'genre:albumartist:album'
browsetype == 'genre:artist:album'

# all tracks from levels above track containers

browsetype == 'albumartist:track'
browsetype == 'artist:track'
browsetype == 'composer:track'

browsetype == 'genre:track'

browsetype == 'genre:albumartist:track'
browsetype == 'genre:artist:track'

# tracks from track containers

browsetype == 'album:track'
browsetype == 'playlist:track'

browsetype == 'albumartist:album:track'
browsetype == 'artist:album:track'
browsetype == 'composer:album:track'

browsetype == 'genre:albumartist:album:track'
browsetype == 'genre:artist:album:track'

