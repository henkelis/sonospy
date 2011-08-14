#! /usr/bin/python

import os
import sys
import subprocess

helptext = """
    A python script to simplify command line database extractions -- good for
    scheduled tasks.

    Usage:
        [arg1]: source database
        [arg2]: target database
        [arg3]:             [arg4]
        created             <,>,=,<=,>=#days
        inserted            <,>,=,<=,>=# days
        lastmodified        <,>,=,<=,>=# days
        lastaccessed        <,>,=,<=,>=# days
        year                <,>,=,<=,>=year
        genre               string
        artist              string
        composer            string
        bitrate             <,>,=,<=,>=bitrate
        albums              number

    Optional Argument:
        [arg5]: -o(verwrite target database)

    """
##########################################
if (len(sys.argv) <4):
    sys.exit(helptext)

if sys.argv[3] in helptext:
    a = 1
else:
    sys.exit(helptext)
    

def main():
    searchCMD = ""
    if sys.argv[3] in ["created", "inserted", "lastaccessed","lastmodified"]:
        searchCMD = "where (julianday(datetime(\'now\')) - julianday(datetime(" + sys.argv[3] +", \'unixepoch\'))) " + sys.argv[4]

    if sys.argv[3] in ["year", "bitrate"]:
        searchCMD = "where " + sys.argv[3] + " " + sys.argv[4]

    if sys.argv[3] in ["genre", "artist", "composer"]:
        searchCMD = "where " + sys.argv[3] +"=\'" + sys.argv[4] + "\'"

    if sys.argv[3] in ["albums", "album"]:
        searchCMD = "AS t WHERE t.created >= (SELECT a.created FROM albums AS a WHERE a.albumartist != 'Various Artists' ORDER BY a.created DESC LIMIT " + str(int(sys.argv[4])-1) + ",1)"

    if searchCMD !="":
        searchCMD = "\"" + searchCMD + "\""

    else:
        sys.exit(helptext)

    if (len(sys.argv) > 5):
        if sys.argv[5] == "-o":
            if os.path.exists(sys.argv[2]) == True:
                illegals = ["/", "~", "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "+","=",","]
                for illegal in illegals:
                    if illegal in sys.argv[2]:
                        print ("\nERROR:\tInvalid target database! You cannot use " + illegal + " in the target database name.")
                        return(1)
                os.remove(sys.argv[2])

    if os.name == 'nt':
        cmdroot = 'python '
    else:
        cmdroot = './'

    scanCMD = cmdroot + "scan.py " + "-d " + sys.argv[1] + " -x " + sys.argv[2] + " -w " + searchCMD

    sub = subprocess.Popen([scanCMD], shell=True).wait()
    return sub

if __name__ == "__main__":
    status = main()
    sys.exit(status)
    
