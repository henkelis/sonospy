#!/usr/bin/env python

# scan,py
#
# scan.py copyright (c) 2011 Mark Henkelis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Mark Henkelis <mark.henkelis@tesco.net>

import os, sys
import optparse
import subprocess
import shlex
import filelog

def process_command_line(argv):
    """
        Return a 2-tuple: (settings object, args list).
        `argv` is a list of arguments, or `None` for ``sys.argv[1:]``.
    """
    if argv is None:
        argv = sys.argv[1:]

    # initialize parser object
    parser = optparse.OptionParser(
        formatter=optparse.TitledHelpFormatter(width=78),
        add_help_option=None)

    # gettags options
    parser.add_option("-d", "--database", dest="database", type="string", 
                      help="write tags to DATABASE", action="store",
                      metavar="DATABASE")
    parser.add_option("-x", "--extract", dest="extract", type="string", 
                      help="write extract to DATABASE", action="store",
                      metavar="EXTRACT")
    parser.add_option("-w", "--where", dest="where", type="string", 
                      help="where clause to extract on", action="store",
                      metavar="WHERE")
    parser.add_option("-e", "--exclude", dest="exclude", type="string",
                      action="append", metavar="EXCLUDE",
                      help="exclude foldernames containing this string")
    parser.add_option("-r", "--regenerate",
                      action="store_true", dest="regenerate", default=False,
                      help="regenerate update records")
    parser.add_option("-c", "--ctime",
                      action="store_true", dest="ctime", default=False,
                      help="user ctime rather than mtime to detect file changes")
    parser.add_option("-q", "--quiet",
                      action="store_true", dest="quiet", default=False,
                      help="don't print status messages to stdout")
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="print verbose status messages to stdout")
    parser.add_option('-h', '--help', action='help',
                      help='Show this help message and exit.')
                      
    # movetags options
    parser.add_option("-t", "--the", dest="the_processing", type="string", 
                      help="how to process 'the' before artist name (before/after/remove)", 
                      action="store",
                      metavar="THE")
                      
    settings, args = parser.parse_args(argv)
    return settings, args

def main(argv=None):
    options, args = process_command_line(argv)
    usage = ''
    if not options.database:
        usage = "'-d databasename' must be specified"
    if options.extract and not options.where:
        usage = "if '-x' is specified '-w' must be specified"
    if options.where and not options.extract:
        usage = "if '-w' is specified '-x' must be specified"
    if options.where and options.extract and options.exclude:
        usage = "if '-x' and '-w' are specified, '-e' must not be specified"
    if options.where and options.extract and options.regenerate:
        usage = "if '-x' and '-w' are specified, '-r' must not be specified"
    if options.exclude and options.regenerate:
        usage = "'-e' and '-r' cannot be specified together"

    if usage != '':
        print usage
        return 1
    else:

        filelog.clear_log_files()
    
        if os.name == 'nt':
            cmdroot = 'python '
        else:
            cmdroot = ''

        # run gettags
        cmd = cmdroot + "./gettags.py" + " -d " + options.database
        if options.extract:
            cmd += " -x " + options.extract
        if options.where:
            cmd += " -w " + '"' + options.where + '"'
        if options.exclude:
            cmd += " -e " + options.exclude
        if options.regenerate:
            cmd += " -r"
        if options.ctime:
            cmd += " -c"
        if options.quiet:
            cmd += " -q"
        if options.verbose:
            cmd += " -v"
        if args:
            for arg in args:
                cmd += " " + arg
        print cmd
        args = shlex.split(cmd)
        sub = subprocess.Popen(args).wait()
        if sub != 0:
            return sub
        else:
            # run movetags
            if options.extract:
                cmd = cmdroot + "./movetags.py" + " -s " + options.extract  + " -d " + options.extract
            else:
                cmd = cmdroot + "./movetags.py" + " -s " + options.database  + " -d " + options.database
            if options.the_processing:
                cmd += " -t " + options.the_processing
            if options.regenerate:
                cmd += " -r"
            if options.extract:
                # flag extract to movetags as regen, so correct order is picked up
                # note this will cause the target database to be cleared first
                cmd += " -r"
            if options.quiet:
                cmd += " -q"
            if options.verbose:
                cmd += " -v"
            print cmd
            args = shlex.split(cmd)
            sub = subprocess.Popen(args).wait()
            return sub

if __name__ == "__main__":
    status = main()
    sys.exit(status)

