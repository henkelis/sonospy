
rm 90s.db
rm last7days.db
rm last7daysupdates.db
rm a.db

# decade

./scan -d test.db -x 90s.db -w "where year >= 1990 and year < 2000"

# recently scanned

./scan -d test.db -x last7days.db -w "where (julianday(datetime('now')) - julianday(datetime(inserted, 'unixepoch'))) <= 7"

# recently changed

./scan -d test.db -x last7daysupdates.db -w "where (julianday(datetime('now')) - julianday(datetime(lastmodified, 'unixepoch'))) <= 7"

# alpha

./scan -d test.db -x a.db -w "where substr(lower(albumartist),1,1) = 'a'"

