# Ogg Vorbis support.
#
# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# $Id: oggvorbis.py 3976 2007-01-13 22:00:14Z piman $

"""Read and write Ogg Vorbis comments.

This module handles Vorbis files wrapped in an Ogg bitstream. The
first Vorbis stream found is used.

Read more about Ogg Vorbis at http://vorbis.com/. This module is based
on the specification at http://www.xiph.org/vorbis/doc/Vorbis_I_spec.html.
"""

__all__ = ["OggVorbis", "Open", "delete"]

import struct

from mutagen._vorbis import VCommentDict
from mutagen.ogg import OggPage, OggFileType, error as OggError

class error(OggError): pass
class OggVorbisHeaderError(error): pass

class OggVorbisInfo(object):
    """Ogg Vorbis stream information.

    Attributes:
    length - file length in seconds, as a float
    bitrate - nominal ('average') bitrate in bits per second, as an int
    """

    length = 0

    def __init__(self, fileobj):
        page = OggPage(fileobj)
        while not page.packets[0].startswith("\x01vorbis"):
            page = OggPage(fileobj)
        if not page.first:
            raise OggVorbisHeaderError(
                "page has ID header, but doesn't start a stream")
        (self.channels, self.sample_rate, max_bitrate, nominal_bitrate,
         min_bitrate) = struct.unpack("<B4i", page.packets[0][11:28])
        self.serial = page.serial

        max_bitrate = max(0, max_bitrate)
        min_bitrate = max(0, min_bitrate)
        nominal_bitrate = max(0, nominal_bitrate)

        if nominal_bitrate == 0:
            self.bitrate = (max_bitrate + min_bitrate) // 2
        elif max_bitrate and max_bitrate < nominal_bitrate:
            # If the max bitrate is less than the nominal, we know
            # the nominal is wrong.
            self.bitrate = max_bitrate
        elif min_bitrate > nominal_bitrate:
            self.bitrate = min_bitrate
        else:
            self.bitrate = nominal_bitrate

        if self.bitrate == 0 and self.length > 0:
            fileobj.seek(0, 2)
            self.bitrate = int((fileobj.tell() * 8) / self.length)
                

    def pprint(self):
        return "Ogg Vorbis, %.2f seconds, %d bps" % (self.length, self.bitrate)

class OggVCommentData(object):
    def __init__(self, offset, packet_start, packet_end):
        self.offset = offset
        self.packet_start = packet_start
        self.packet_end = packet_end
    def __repr__(self):
        attrs = ['offset', 'packet_start', 'packet_end']
        values = ["%s=%r" % (attr, getattr(self, attr)) for attr in attrs]
        return "<%s %s>" % (type(self).__name__, " ".join(values))

class OggVCommentDict(VCommentDict):
    """Vorbis comments embedded in an Ogg bitstream."""

    def __init__(self, fileobj, info):
        self.pages = []
        self.pages_data = []
        self.sections = []
        complete = False
        while not complete:
            page = OggPage(fileobj)
            if page.serial == info.serial:
                self.pages.append(page)
#                print page.packets
                packet_start = page.offset + 27 + page.segments
                packet_end = packet_start + page.lacings[0] - 1
#                print page
                page_data = OggVCommentData(page.offset, packet_start, packet_end)
#                print page_data
                self.pages_data.append(page_data)
                complete = page.complete or (len(page.packets) > 1)
        data = OggPage.to_packets(self.pages)[0][7:] # Strip off "\x03vorbis".
#        print data
        super(OggVCommentDict, self).__init__(data)
        
        picture_found = False
        for (tag, tagvalue), (offset, size) in zip(self, self.tag_data):
            # the offset is relative, calculate the absolute offset - we need to add the absolute page offset for the first page and the stripped off "\x03vorbis"
            abs_offset = offset + self.pages_data[0].packet_start + 7
            if tag == 'METADATA_BLOCK_PICTURE' and not picture_found:
                picture_found = True
#                print "tag: %s, offset: %s, abs offset: %s, size: %s" % (tag, offset, abs_offset, size)
                # find which page picture starts in
                length = count = 0
                for pd in self.pages_data:
                    data_length = pd.packet_end - pd.packet_start + 1
                    length += data_length
                    if offset <= length:
                        # picture starts on this page
                        tag_len = len(tag) + 1
                        data_start = abs_offset + tag_len
                        self.sections.append(data_start)
                        packet_left = pd.packet_end - data_start + 1
                        if packet_left >= size:
                            data_end = size
                            self.sections.append(data_end)
                        else:
                            self.sections.append(packet_left)
                            remaining = size - packet_left - tag_len
                            for i in range(count+1, len(self.pages_data)):
                                data_start = self.pages_data[i].packet_start
                                self.sections.append(self.pages_data[i].packet_start)
                                packet_length = self.pages_data[i].packet_end - self.pages_data[i].packet_start + 1
                                if packet_length >= remaining:
                                    self.sections.append(remaining)
                                    break
                                else:
                                    self.sections.append(packet_length)
                                    remaining -= packet_length
#                        print self.sections
                        break
                    count += 1

    def _inject(self, fileobj):
        """Write tag data into the Vorbis comment packet/page."""

        # Find the old pages in the file; we'll need to remove them,
        # plus grab any stray setup packet data out of them.
        fileobj.seek(0)
        page = OggPage(fileobj)
        while not page.packets[0].startswith("\x03vorbis"):
            page = OggPage(fileobj)

        old_pages = [page]
        while not (old_pages[-1].complete or len(old_pages[-1].packets) > 1):
            page = OggPage(fileobj)
            if page.serial == old_pages[0].serial:
                old_pages.append(page)

        packets = OggPage.to_packets(old_pages, strict=False)

        # Set the new comment packet.
        packets[0] = "\x03vorbis" + self.write()

        new_pages = OggPage.from_packets(packets, old_pages[0].sequence)
        OggPage.replace(fileobj, old_pages, new_pages)

class OggVorbis(OggFileType):
    """An Ogg Vorbis file."""

    _Info = OggVorbisInfo
    _Tags = OggVCommentDict
    _Error = OggVorbisHeaderError
    _mimes = ["audio/vorbis", "audio/x-vorbis"]

    def score(filename, fileobj, header):
        return (header.startswith("OggS") * ("\x01vorbis" in header))
    score = staticmethod(score)

Open = OggVorbis

def delete(filename):
    """Remove tags from a file."""
    OggVorbis(filename).delete()
