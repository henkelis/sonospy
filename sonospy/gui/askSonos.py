#!/usr/bin/env python

# askSonos Python Script ################
# A python script to poll the Sonospy
# backend to get various track and status
# info.
#########################################
import sys, socket, os, urllib

# help text ############################
helptext = """
    A python script to poll the sonospy backend to retrieve
    now-playing information as well as some status on the
    zone player itself.

    Please use at least the following two arguments:

    [arg1]: The zone player you want to poll (kitchen, living%20room,
    etc.)
        NOTE: A %20 is required for spaces in your ZP name.

    [arg2]: can be one of the following: track, album, artist, type
    class, position, percent, volume, volume_fixed, mute, state, art
        NOTE: volume, volume_fixed, mute and state all seem to
        belong to the zone player itself.

    [lower]: this third argument (sans brackets) is optional, but will
    output your results in lowercase, should you want that.

    example: python askSonos.py Portable track lower
    """
##########################################

# Error out if there aren't enough command
# line arguments.

if (len(sys.argv) <2):
    sys.exit(helptext)

# Check the sys.argv[2] for valid input, error out if not.
searchArg = sys.argv[2].lower()

def searchFor(searchType):
    try:
        return {
            'track'         :   'TRACK::',
            'album'         :   'ALBUM::',
            'artist'        :   'ARTIST::',
            'type'          :   'TYPE::',
            'class'         :   'CLASS::',
            'position'      :   'POSITION::',
            'percent'       :	'PERCENT::',
            'volume'        :   'VOLUME::',         # Not sure what this does...
            'volume_fixed'  :   'VOLUME_FIXED::',	# ..
            'mute'          :   'MUTE::',           # ..
            'state'         :   'STATE::',
            'art'           :	'ART::'
        }[searchType]
    except KeyError:
        sys.exit(helptext)

# Step 3 - get the host IP address (linux and windows?)

if os.name != "nt":
    import fcntl
    import struct
    def get_interface_ip(ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
                        s.fileno(),
                        0x8915,  # SIOCGIFADDR
                        struct.pack('256s', ifname[:15])
                )[20:24])

def get_lan_ip():
    ipaddy = socket.gethostbyname(socket.gethostname())
    if ipaddy.startswith("127.") and os.name != "nt":
        interfaces = ["eth0","eth1","eth2","wlan0","wlan1","wifi0","ath0","ath1","ppp0"]
        for ifname in interfaces:
                try:
                        ipaddy = get_interface_ip(ifname)
                        return ipaddy #find the first non 127 interface ip
                        break;
                except IOerror:
                    pass


# Step 4 - set and poll sys.argv[1] (The Zone Player)

# Set the Renderer
pEntry = "?data=R::"+ sys.argv[1] +" (ZP)"
pType = "Data"
rendererString=urllib.urlopen('http://' + get_lan_ip() + ':50101/data/renderer' + pType + pEntry).read()

# Set to Poll for Data
pType = "Poll"
pollString=urllib.urlopen('http://' + get_lan_ip() + ':50101/data/renderer' + pType + pEntry).read()


# Step 5 - Case Statement for what to strip out of the final output
stripME=searchFor(searchArg)

# Step 6 - Strip the output
# First instance of result (pollString.index(StripME)+len(stripME):]) trims the
# string to the value we're searching for.  The second result entry trims the
# rest of the string when it finds the delimiter (_|_)
result = (pollString[pollString.index(stripME)+len(stripME):])
result = (result[:result.index('_|_')])

# Step 7 - print in lowercase or not
if (len(sys.argv) >3):
    if (sys.argv[3].lower() == "lower"):
        print(result.lower())
    else:
        print(result)
else:
    print(result)
