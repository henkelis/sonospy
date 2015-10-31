import argparse
import sqlite3, os
import gzip

# Mimic the sqlite3 console shell's .dump command
# Author: Paul Kippes <kippesp@gmail.com>

def _iterdump(connection, table_name):
    """
    Returns an iterator to the dump of the database in an SQL text format.

    Used to produce an SQL dump of the database.  Useful to save an in-memory
    database for later restoration.  This function should not be called
    directly but instead called from the Connection method, iterdump().
    """

    cu = connection.cursor()
    table_name = table_name

    yield('BEGIN TRANSACTION;')

    # sqlite_master table contains the SQL CREATE statements for the database.
    q = """
       SELECT name, type, sql
        FROM sqlite_master
            WHERE sql NOT NULL AND
            type == 'table' AND
            name == :table_name
        """
    schema_res = cu.execute(q, {'table_name': table_name})
    for table_name, type, sql in schema_res.fetchall():
        if table_name == 'sqlite_sequence':
            yield('DELETE FROM sqlite_sequence;')
        elif table_name == 'sqlite_stat1':
            yield('ANALYZE sqlite_master;')
        elif table_name.startswith('sqlite_'):
            continue
        else:
            yield('%s;' % sql)

        # Build the insert statement for each row of the current table
        res = cu.execute("PRAGMA table_info('%s')" % table_name)
        column_names = [str(table_info[1]) for table_info in res.fetchall()]
        q = "SELECT 'INSERT INTO \"%(tbl_name)s\" VALUES("
        q += ",".join(["'||quote(" + col + ")||'" for col in column_names])
        q += ")' FROM '%(tbl_name)s'"
        query_res = cu.execute(q % {'tbl_name': table_name})
        for row in query_res:
            yield("%s;" % row[0])

    # Now when the type is 'index', 'trigger', or 'view'
    #q = """
    #    SELECT name, type, sql
    #    FROM sqlite_master
    #        WHERE sql NOT NULL AND
    #        type IN ('index', 'trigger', 'view')
    #    """
    #schema_res = cu.execute(q)
    #for name, type, sql in schema_res.fetchall():
    #    yield('%s;' % sql)

    yield('COMMIT;')        
    
parser = argparse.ArgumentParser(description='Dump database to SQL file')
parser.add_argument('dbname', help='database name')
args = parser.parse_args()

print 'Database: %s' % args.dbname
try:
    fstat = os.stat(args.dbname)
except OSError:
    print 'Can\'t access %s' % args.dbname
    exit(1)
try:
    con = sqlite3.connect(args.dbname)
except sqlite3.Error, e:
    print "Error connecting to %s: %s" % (args.dbname, e.args[0])
    exit(1)
with gzip.open('dump.txt.gz', mode='w') as zf:
    for line in _iterdump(con, 'tags'):
        zf.write('%s\n' % line.encode('utf8'))
    for line in _iterdump(con, 'workvirtuals'):
        zf.write('%s\n' % line.encode('utf8'))
zf.close()
print 'Output file: %s' % 'dump.txt.gz'
    
