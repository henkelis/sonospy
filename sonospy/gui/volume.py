#!/usr/bin/env python

# volume Python Script ################
# A python script to allow for a rough
# automation of volume limiting so that
# a particular zone cannot exceed a
# fixed amount (maxVOLUME).  This has to
# be used in conjunction with cron or
# a Windows equivalent
#########################################
import sys, socket, os, urllib

# help text ############################
helptext = """
    A python script to allow for a rough
    automation of volume limiting so that
    a particular zone cannot exceed a
    fixed amount (maxVOLUME).  This has to
    be used in conjunction with cron or
    a Windows equivalent

    [arg1]: The zone player you want to poll (kitchen, living%20room,
    etc.)
        NOTE: A %20 is required for spaces in your ZP name.

    example: python volume.py Spa
    """
##########################################

# Error out if there aren't enough command
# line arguments.

if (len(sys.argv) <1):
    sys.exit(helptext)
    
    # Get the host IP address (linux and windows?)
    
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
