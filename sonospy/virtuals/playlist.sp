# It is possible to create your own albums that appear like any other
# album in the proxy. Such albums can be 'virtuals' or 'works'. Virtuals 
# and works are essentially the same, but you can get the proxy to 
# treat them differently at runtime.

# Works are aimed at allowing you to pull together a set of tracks into
# a composer's single work. It's likely that you want to do that to be
# able to play one work comprised of several tracks, but only a subset
# of a CD, as one piece.

# Virtuals are aimed at allowing you to pull together a set of tracks
# into an album. You may for instance want to create a version of an album
# with certain tracks removed, or pull together favourite tracks from 
# several albums.

# This file defines the structure for work or virtual album definitions.
# To define a work or a virtual album so that it appears in the proxy,
# create a file with this format and populate it with a header and track
# detail records. Note that you can have multiple work and/or virtual
# definitions in the same file if desired.

# If you place this file in the scan path (you can have a completely
# different scan path for these files if you like), the scanner will
# read the file and populate the database with the details you specify.
# When you run the proxy, the works and virtuals you create will 
# appear just as physical albums do.

# All tracks that you specify must be in the database (tracks will be
# scanned first, followed by work/virtual files).

# Subsequent scans will re-read work/virtual files if they are changed.

# Changing a track referred to in a work/virtual will cause a re-read
# of associated work/virtual files.

# Deleting a track referred to in a work/virtual will cause the track
# to be removed from the work/virtual in the database (but note that
# the work/virtual file will not be changed).

# Tracks or playlists that can't be found will be logged as errors in
# the logs folder.

# You can use any base name for the work/virtual file. You can specify 
# alternate extensions for work and virtual files in scan.ini
# (work_file_extension and virtual_file_extension).

#
# header
#
# The minimum detail that a header needs is a title for the work or virtual.
# The other fields below can be left empty or removed completely.
#
#     'type' is work or virtual (defaults to virtual if not specified).
#
#     'title' is the base name of the work or virtual (can be overridden in
#     scan.ini).
#
#     Set other attributes to values to override values in all tracks for this
#     work or virtual.
#
#     Use string <blank> to blank out a tag.
#
#     Header remains in force until another header is encountered or end of
#     file.
#
#     Lines beginning with # are ignored, as are blank lines
#

type=
title=Green Curry Virtual
artist=The Green Curry Band
albumartist=
composer=<blank>
year=2012
genre=Stuff
cover=
discnumber=
inserted=
created=
lastmodified=

#
# tracks
#
# To add tracks to your work/virtual, list them here.
#
#     list of tracks for this work or virtual
#
#     tracks will be added in order given
#
#     you can specify a folder, and all tracks within that folder will be included (recursively)
#
#     the track list can contain playlist(s)
#
#     tracks can be specified more than once in the same list
#
#     track paths can be relative to the folder this file is stored in or absolute
#
#     lines beginning with # are ignored, as are blank lines
#
#     note - embedded workvirtual files are not supported
#            playlists containing playlists are not supported
#

track.flac
../music/track2.mp3
local/music/track3.wav
/home/mark/Music/m1/playlist.m3u

21st Century Breakdown/Green Day - ¿Viva La Gloria [Little Girl] [Album Version].mp3
21st Century Breakdown/Green Day - Know Your Enemy [Album Version].mp3
21st Century Breakdown/Green Day - ¿Viva La Gloria [Little Girl] [Album Version].mp3

R.E.M

##################

TYPE=work
title=Red Curry Work
artist=The Red Curry Band
albumartist=
composer=
year=
genre=
cover=
discnumber=
inserted=
created=
lastmodified=

/somewhere else/more music/flactrack.flac
21st Century Breakdown/Green Day - Peacemaker [Album Version].mp3
21st Century Breakdown/Green Day - Know Your Enemy [Album Version].mp3

