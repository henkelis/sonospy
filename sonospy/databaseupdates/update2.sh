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
.quit
EOSQL

rm $db

# add asort fields to tags table
mv tags.sql tags.sql.orig
sed "s/inserted text, lastscanned text);/inserted text, lastscanned text, titlesort text, albumsort text, artistsort text, albumartistsort text, composersort text);/" tags.sql.orig >tags2.sql
sed "s/');$/','','','','','');/" tags2.sql >tags3.sql
cp tags3.sql tags.sql

# add asort and artid fields to workvirtuals table
mv workvirtuals.sql workvirtuals.sql.orig
sed "s/scannumber integer, lastscanned text);/scannumber integer, lastscanned text, titlesort text, albumsort text, artistsort text, albumartistsort text, composersort text, coverartid integer);/" workvirtuals.sql.orig >workvirtuals2.sql
sed "s/');$/','','','','','',0);/" workvirtuals2.sql >workvirtuals3.sql
cp workvirtuals3.sql workvirtuals.sql

# recreate database
sqlite3 $db <<EOSQL
.read tags.sql
.read workvirtuals.sql
.read playlists.sql
.quit
EOSQL

# set stats
sqlite3 $db <<EOSQL
analyze;
.quit
EOSQL

