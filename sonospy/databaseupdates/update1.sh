#!/bin/sh

db=$1

if [ -z "$db" ]; then
  echo Missing path to database. >&2
  exit 1
fi

cp $db $db.orig

# export tags
sqlite3 $db <<EOSQL
.output tags.sql
.dump tags
.output workvirtuals.sql
.dump workvirtuals
.output playlists.sql
.dump playlists
.output sorts.sql
.dump sorts
.quit
EOSQL

rm $db

# remove upnpclass field from tags table
mv tags.sql tags.sql.orig
sed "s/'object.item.audioItem.musicTrack',//" tags.sql.orig >tags2.sql
sed "s/ upnpclass text,//" tags2.sql >tags3.sql
cp tags3.sql tags.sql

# recreate tags
sqlite3 $db <<EOSQL
.read tags.sql
.read workvirtuals.sql
.read playlists.sql
.read sorts.sql
.quit
EOSQL

# add track_rowid column to playlists
sqlite3 $db <<EOSQL

BEGIN TRANSACTION;

create TEMPORARY table playlists_backup (playlist text COLLATE NOCASE,
    id text,
    plfile text, trackfile text, 
    occurs text, track text, track_id text,
    track_rowid integer,
    inserted text, created text, lastmodified text,
    plfilecreated text, plfilelastmodified text,
    trackfilecreated text, trackfilelastmodified text,
    scannumber integer, lastscanned text);

INSERT INTO playlists_backup SELECT 
    playlist, id, plfile, trackfile, occurs, track, track_id, 0, 
    inserted, created, lastmodified, plfilecreated, plfilelastmodified,
    trackfilecreated, trackfilelastmodified, scannumber, lastscanned
    FROM playlists;

DROP TABLE playlists;

create table playlists (playlist text COLLATE NOCASE,
    id text,
    plfile text, trackfile text, 
    occurs text, track text, track_id text,
    track_rowid integer,
    inserted text, created text, lastmodified text,
    plfilecreated text, plfilelastmodified text,
    trackfilecreated text, trackfilelastmodified text,
    scannumber integer, lastscanned text);

create unique index inxPlaylistTrackFiles on playlists (playlist, plfile, trackfile, occurs);
create index inxPlaylists on playlists (playlist);
create index inxPlaylistIDs on playlists (id);
create index inxPlaylistsScannumber on playlists (scannumber);

INSERT INTO playlists SELECT * FROM playlists_backup;

drop table if exists playlists_update;
create table playlists_update (playlist text COLLATE NOCASE,
    id text,
    plfile text, trackfile text, 
    occurs text, track text, track_id text,
    track_rowid integer,
    inserted text, created text, lastmodified text,
    plfilecreated text, plfilelastmodified text,
    trackfilecreated text, trackfilelastmodified text,
    scannumber integer, lastscanned text,
    updateorder integer, updatetype text);

create unique index inxPlaylistUpdateIdScanUpdate on playlists_update (playlist, plfile, trackfile, occurs, scannumber, updateorder);
create unique index inxPlaylistUpdateScanUpdateId on playlists_update (scannumber, updatetype, playlist, plfile, trackfile, occurs, updateorder);
create index inxPlaylistUpdateScannumber on playlists_update (scannumber);

DROP TABLE playlists_backup;

COMMIT;
analyze;
.quit
EOSQL

