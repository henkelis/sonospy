###############################################################################
# NowPlaying Tab for use with sonospyGUI.py
###############################################################################
# Copyright, blah, blah
###############################################################################
# sonospy_proxy cannot run with the -p flag - edit the file if this mysteriously
# breaks.
#
# TODO:
#   - Discover ZPs?
#   - Integrate: ZP Name, Artist, self.track, Album, Artwork, Position
#   - Needs to error out when NOT PLAYING AT ALL!
###############################################################################

import wx
from wxPython.wx import *
import os
import sys
import socket
import urllib
import fcntl
import struct
import StringIO

zp = ""

class NowPlayingPanel(wx.Panel):
    """
    Launch Tab for finding and launching .db files
    """
    #----------------------------------------------------------------------
    def __init__(self, parent):
        """"""
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)

        panel = self
        sizer = wx.GridBagSizer(6, 5)

    # --------------------------------------------------------------------------
    # [0] ZonePlayer 1       ---------------------------------------------------

        # Create static box
        self.zp1 = wx.StaticBox(panel, label="Portable", size=(100,100))
        sbs_ZonePlayerStats = wx.StaticBoxSizer(self.zp1, wx.VERTICAL)
        zpSizer = wx.GridBagSizer(1, 2)
        statSizer = wx.GridBagSizer(3,2)

        sizerIndexX = 0

        zPlayer = self.zp1.Label
        zPlayer = zPlayer.replace(' ','%20')

        # Album Art

        # alternate (simpler) way to load and display a jpg image from a file
        # actually you can load .jpg .png .bmp or .gif files
        url = askSonos(zPlayer, "art")

        fp = urllib.urlopen(url)
        data = fp.read()
        data = StringIO.StringIO(data)
        fp.close()
        img = wxImageFromStream(data)
 
        if img.GetWidth > img.GetHeight():
            ratio = float(200.0/img.GetWidth())
        else:
            ratio = float(200.0/img.GetHeight())
        img = img.Scale(img.GetWidth()*ratio,img.GetHeight()*ratio)
        img = wx.BitmapFromImage(img)
        
        self.art = wx.StaticBitmap(panel, -1, img)

        # Add them to the sizer (zpSizer)
        zpSizer.Add(self.art, pos=(0, 0), flag=wx.EXPAND|wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Artist
        self.artist = wx.StaticText(panel, label="Artist: ")
        self.artistName = wx.StaticText(panel, label="")

        # Add them to the sizer (zpSizer)
        sizerIndexX += 1
        statSizer.Add(self.artist, pos=(0, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        statSizer.Add(self.artistName, pos=(0, 1), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # self.track
        sizerIndexX += 1
        self.track = wx.StaticText(panel, label="Track: ")
        self.trackName = wx.StaticText(panel, label="")

        # Add them to the sizer (zpSizer)
        statSizer.Add(self.track, pos=(1, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        statSizer.Add(self.trackName, pos=(1, 1), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Album
        sizerIndexX += 1
        self.album = wx.StaticText(panel, label="Album: ")
        self.albumName = wx.StaticText(panel, label="")

        # Add them to the sizer (zpSizer)
        statSizer.Add(self.album, pos=(2, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        statSizer.Add(self.albumName, pos=(2, 1), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        zpSizer.AddGrowableCol(8)

        sbs_ZonePlayerStats.Add(zpSizer, flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sbs_ZonePlayerStats.Add(statSizer, flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(sbs_ZonePlayerStats, pos=(0, 0), flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)

# Back to your normal programming. :)
        self.bt_Refresh = wx.Button(panel, label="Refresh")
        self.bt_Refresh.Bind(wx.EVT_BUTTON, self.bt_RefreshClick, self.bt_Refresh)
        sizer.Add(self.bt_Refresh, pos=(3,0), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)

    def bt_RefreshClick(self, event):
 
        if self.zp1.Label == "Living Room":
            self.zp1.Label = "Portable"
            zp = "Portable"
        else:
            self.zp1.Label = "Living Room"
            zp = "Living%20Room"
            
        self.artistName.Label = askSonos(zp, 'artist')
        self.trackName.Label = askSonos(zp, 'track')
        self.albumName.Label = askSonos(zp, 'album')
        url = askSonos(zp, "art")

        fp = urllib.urlopen(url)
        data = fp.read()
        data = StringIO.StringIO(data)
        fp.close()
        img = wxImageFromStream(data)

        if img.GetWidth > img.GetHeight():
            ratio = float(200.0/img.GetWidth())
        else:
            ratio = float(200.0/img.GetHeight())
        img = img.Scale(img.GetWidth()*ratio,img.GetHeight()*ratio)
        img = wx.BitmapFromImage(img)

       
def askSonos(zp, request):
    pEntry = "?data=R::"+ zp +" (ZP)"
    
    pType = "Data"
    rendererString=urllib.urlopen('http://' + get_lan_ip() + ':50101/data/renderer' + pType + pEntry).read()

    # Set to Poll for Data
    pType = "Poll"
    pollString=urllib.urlopen('http://' + get_lan_ip() + ':50101/data/renderer' + pType + pEntry).read()

    # Step 5 - Case Statement for what to strip out of the final output
    stripME=searchFor(request)

    # Step 6 - Strip the output
    # First instance of result (pollString.index(StripME)+len(stripME):]) trims the
    # string to the value we're searching for.  The second result entry trims the
    # rest of the string when it finds the delimiter (_|_)

    result = (pollString[pollString.index(stripME)+len(stripME):])
    result = (result[:result.index('_|_')])

    # Step 7 - print in lowercase or not
    return(result)

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


# Step 4 - set and poll sys.argv[1] (The Zone Player)

# Set the Renderer

# Step 3 - get the host IP address (linux and windows?)

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
