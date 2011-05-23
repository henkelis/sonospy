# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

import pygst
import time
pygst.require('0.10')
import gst

from brisa.core import log
from brisa.utils.looping_call import LoopingCall


class GSTRenderer(object):

    def __init__(self):
        self.build_pipeline()
        self.__av_uri = None
        self.time_format = gst.Format(gst.FORMAT_TIME)
        self.player_state = 0
        loop = LoopingCall(self.poll_bus)
        loop.start(0.2, True)

    def poll_bus(self):
        if self.bus:
            message = self.bus.poll(gst.MESSAGE_ERROR|gst.MESSAGE_EOS,
                                    timeout=1)
            if message:
                self.on_message(self.bus, message)

    def get_state(self):
        if self.player_state == 0:
            return 'STOPPED'
        if self.player_state == 1:
            return 'PLAYING'
        if self.player_state == 2:
            return 'PAUSED_PLAYBACK'

    def __set_uri(self, uri):
        self.player.set_property('uri', uri)
        self.__av_uri = uri

    def __get_uri(self):
        return self.__av_uri

    av_uri = property(__get_uri, __set_uri)

    def build_pipeline(self):
        self.player = gst.element_factory_make("playbin", "player")
        self.bus = self.player.get_bus()
        self.player.set_state(gst.STATE_READY)

    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.player.set_state(gst.STATE_NULL)
            self.player_state = 0
        elif t == gst.MESSAGE_ERROR:
            self.player.set_state(gst.STATE_NULL)
            self.player_state = 0

    def play(self):
        if self.av_uri is not None:
            if (self.player.set_state(gst.STATE_PLAYING) ==
                gst.STATE_CHANGE_FAILURE):
                log.error("error trying to play %s.", self.av_uri)
            self.player_state = 1
        else:
            log.info("av_uri is None, unable to play.")

    def stop(self):
        if self.player.set_state(gst.STATE_READY) == gst.STATE_CHANGE_FAILURE:
            log.error("error while stopping the player")
        self.player_state = 0

    def pause(self):
        if self.player.set_state(gst.STATE_PAUSED) == gst.STATE_CHANGE_FAILURE:
            log.error("error while pausing the player")
        self.player_state = 2

    def seek(self, unit, target):
        if unit == "ABS_TIME":
            target_time = self.convert_int(target)
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target_time)

        if unit == "REL_TIME":
            target_time = self.convert_int(target)
            cur_pos = self.query_position()[1]
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target_time+cur_pos)

        if unit == "ABS_COUNT":
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target)

        if unit == "REL_COUNT":
            cur_pos = self.query_position()[1]
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target + cur_pos)

    def set_volume(self, volume):
        self.player.set_property("volume", volume/10)

    def get_volume(self):
        return int(self.player.get_property("volume")*10)

    def query_duration(self):
        time.sleep(0.3)
        try:
            dur_int = self.player.query_duration(self.time_format, None)[0]
            dur_str = self.convert_ns(dur_int)
        except gst.QueryError:
            dur_int = -1
            dur_str = ''

        return dur_str, dur_int

    def query_position(self):
        try:
            pos_int = self.player.query_position(self.time_format, None)[0]
            pos_str = self.convert_ns(pos_int)
        except gst.QueryError:
            pos_int = -1
            pos_str = ''

        return pos_str, pos_int

    def convert_ns(self, time):
        hours, left_time = divmod(time/1000000000, 3600)
        minutes, left_time = divmod(left_time, 60)
        return '%02d:%02d:%02d' % (hours, minutes, left_time)

    def convert_int(self, time_str):
        time_str = time_str.strip('")( ')
        (hours, min, sec) = time_str.split(":")
        time_int = int(hours) * 3600 + int(min) * 60 + int(sec)
        time_int = time_int * 1000000000
        return time_int


class GSTRendererMaemo(object):

    def __init__(self):
        self.build_elements()
        self.__av_uri = None
        self.time_format = gst.Format(gst.FORMAT_TIME)
        self.player_state = 0
        self.current_volume = 0

        #  0-Stopped, 1-Playing, 2-Paused

    def build_elements(self):
        self.player = gst.Pipeline()
        self.filesrc = gst.element_factory_make("gnomevfssrc", "filesrc")
        self.typefinder = gst.element_factory_make("typefind", "typefinder")
        self.typefinder.connect("have-type", self.__cb_typefound)
        self.player.add(self.filesrc, self.typefinder)

        gst.element_link_many(self.filesrc, self.typefinder)

        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)

        self.mp3audiosink = gst.element_factory_make("dspmp3sink")
        self.mp3audioqueue = gst.element_factory_make("queue")
        self.mp3audiobin = gst.Bin('mp3bin')
        self.mp3audiobin.add(self.mp3audioqueue, self.mp3audiosink)

        self.videosink = gst.element_factory_make("xvimagesink", 'videosink')

        self.hantrovideodec = gst.element_factory_make("hantro4100dec")
        self.hantrovideoqueue = gst.element_factory_make("queue")
        self.hantrovideobin = gst.Bin('hantrobin')
        self.hantrovideobin.add(self.hantrovideoqueue, self.hantrovideodec)

        self.mpegvideodec = gst.element_factory_make("ffdec_mpegvideo")
        self.mpegvideoqueue = gst.element_factory_make("queue")
        self.mpegvideobin = gst.Bin('mpegbin')
        self.mpegvideobin.add(self.mpegvideoqueue, self.mpegvideodec)

        self.aacaudiosink = gst.element_factory_make("dspaacsink")
        self.aacaudioqueue = gst.element_factory_make("queue")
        self.aacaudiobin = gst.Bin('aacbin')
        self.aacaudiobin.add(self.aacaudioqueue, self.aacaudiosink)

        gst.element_link_many(self.hantrovideoqueue, self.hantrovideodec)
        gst.element_link_many(self.mp3audioqueue, self.mp3audiosink)
        gst.element_link_many(self.mpegvideoqueue, self.mpegvideodec)
        gst.element_link_many(self.aacaudioqueue, self.aacaudiosink)

        self.hantrovideobin.add_pad(gst.GhostPad('sink',
                                    self.hantrovideoqueue.get_pad('sink')))
        self.hantrovideobin.add_pad(gst.GhostPad('src',
                                    self.hantrovideodec.get_pad('src')))

        self.mp3audiobin.add_pad(gst.GhostPad('sink',
                                    self.mp3audioqueue.get_pad('sink')))

        self.mpegvideobin.add_pad(gst.GhostPad('sink',
                                    self.mpegvideoqueue.get_pad('sink')))
        self.mpegvideobin.add_pad(gst.GhostPad('src',
                                    self.mpegvideodec.get_pad('src')))

        self.aacaudiobin.add_pad(gst.GhostPad('sink',
                                    self.aacaudioqueue.get_pad('sink')))

    def reset_elements(self):
        if self.player.get_by_name('mp3bin') is not None:
            self.mp3audiobin.unparent()
            self.player.remove(self.mp3audiobin)
        if self.player.get_by_name('hantrobin') is not None:
            self.hantrovideobin.unparent()
            self.player.remove(self.hantrovideobin)
        if self.player.get_by_name('mpegbin') is not None:
            self.mpegvideobin.unparent()
            self.player.remove(self.mpegvideobin)
        if self.player.get_by_name('videosink') is not None:
            self.videosink.unparent()
            self.player.remove(self.videosink)

        self.player.remove(self.filesrc)
        self.player.remove(self.typefinder)
        self.player.add(self.filesrc, self.typefinder)

        gst.element_link_many(self.filesrc, self.typefinder)

    def get_state(self):
        if self.player_state == 0:
            return 'STOPPED'
        if self.player_state == 1:
            return 'PLAYING'
        if self.player_state == 2:
            return 'PAUSED_PLAYBACK'

    def __set_uri(self, uri):
        self.player.set_state(gst.STATE_NULL)
        self.reset_elements()
        self.filesrc.set_property('location', uri)
        self.filesrc.set_property('iradio-mode', True)
        self.filesrc.set_property('typefind', True)
        self.__av_uri = uri
        self.set_volume(self.current_volume)
        self.player.set_state(gst.STATE_READY)

    def __get_uri(self):
        return self.__av_uri

    av_uri = property(__get_uri, __set_uri)

    def on_pad_added_mp3(self, element, pad):
        caps = pad.get_caps()
        name = caps[0].get_name()
        aqpad = self.mp3audiobin.get_pad('sink')
        if name == 'audio/mpeg':
            if not aqpad.is_linked(): # Only link once
                pad.link(aqpad)
            self.mp3audiobin.set_state(gst.STATE_PLAYING)

    def __cb_typefound(self, element, prob, caps):
        if str(caps).find("audio/mpeg") is not -1:
            if self.mp3audiobin.get_parent() is None:
                self.player.add(self.mp3audiobin)
                gst.element_link_many(self.typefinder, self.mp3audiobin)
                self.mp3audiobin.set_state(gst.STATE_PLAYING)
            else:
                self.mp3audiobin.set_state(gst.STATE_READY)
                self.mp3audiobin.set_state(gst.STATE_PLAYING)

        elif str(caps).find("application/x-id3") is not -1:
            if self.mp3audiobin.get_parent() is None:
#                id3lib = gst.element_factory_make("id3demux")
#                self.player.add(id3lib)
                self.player.add(self.mp3audiobin)
                gst.element_link_many(self.typefinder, id3lib)
                self.player.add(self.mp3audiobin)
                id3lib.connect('pad-added', self.on_pad_added_mp3)

            else:
                self.mp3audiobin.set_state(gst.STATE_READY)
                self.mp3audiobin.set_state(gst.STATE_PLAYING)

        elif str(caps).find("video/x-msvideo") is not -1:
             # Create elements
            if self.hantrovideobin.get_parent() is None:
                demux = gst.element_factory_make("avidemux")
                self.player.add(demux)
                # Link source and demux elements
                gst.element_link_many(self.typefinder, demux)
                # Connect handler for 'pad-added' signal
                demux.connect('pad-added', self.on_pad_added)
                self.player.add(self.hantrovideobin, self.videosink)
                gst.element_link_many(self.hantrovideobin, self.videosink)

                demux.set_state(gst.STATE_PLAYING)

        elif str(caps).find("video/mpeg") is not -1:
            # Create elements
            if self.mpegvideobin.get_parent() is None:
                demux = gst.element_factory_make("mpegdemux")
                self.player.add(demux)
                # Link source and demux elements
                gst.element_link_many(self.typefinder, demux)
                # Connect handler for 'pad-added' signal
                demux.connect('pad-added', self.on_pad_added)
                self.player.add(self.mpegvideobin, self.videosink)
                gst.element_link_many(self.mpegvideobin, self.videosink)

                demux.set_state(gst.STATE_PLAYING)

        elif caps == "adts_mpeg_stream" or caps == "audio/x-ac3" or \
                                        caps == "audio/x-dts":
            if self.aacaudiobin.get_parent() is None:
                self.player.add(self.aacaudiobin)
                gst.element_link_many(self.typefinder, self.aacaudiobin)
                self.aacaudiobin.set_state(gst.STATE_PLAYING)
            else:
                self.aacaudiobin.set_state(gst.STATE_READY)
                self.aacaudiobin.set_state(gst.STATE_PLAYING)

        elif caps == "video/quicktime":
            pass

        else:
            log.error("format not support %s", str(caps))
            self.player.set_state(gst.STATE_NULL)
            self.__av_uri = None

    def on_pad_added(self, element, pad):
        caps = pad.get_caps()
        name = caps[0].get_name()
        if name == 'audio/mpeg':
            if self.mp3audiobin.get_parent() is None:
                self.player.add(self.mp3audiobin)
            aqpad = self.mp3audiobin.get_pad('sink')
            if not aqpad.is_linked(): # Only link once
                pad.link(aqpad)
            self.mp3audiobin.set_state(gst.STATE_PLAYING)
        elif name == 'audio/x-ac3' or name == 'audio/x-dts':
            if self.aacaudiobin.get_parent() is None:
                self.player.add(self.aacaudiobin)
            aqpad = self.aacaudiobin.get_pad('sink')
            if not aqpad.is_linked(): # Only link once
                pad.link(aqpad)
                self.mp3audiobin.set_state(gst.STATE_PLAYING)
        elif name == 'video/mpeg':
            vqpad = self.mpegvideobin.get_pad('sink')
            if not vqpad.is_linked(): # Only link once
                pad.link(vqpad)
                self.videosink.set_state(gst.STATE_PLAYING)
                self.mpegvideobin.set_state(gst.STATE_PLAYING)
        else:
            vqpad = self.hantrovideobin.get_pad('sink')
            if not vqpad.is_linked(): # Only link once
                pad.link(vqpad)
                self.videosink.set_state(gst.STATE_PLAYING)
                self.hantrovideobin.set_state(gst.STATE_PLAYING)

    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.player.set_state(gst.STATE_NULL)
            self.player_state = 0
            self.player.set_state(gst.STATE_READY)

        elif t == gst.MESSAGE_ERROR:
            self.player.set_state(gst.STATE_NULL)
            log.error(str(message))
            self.player_state = 0
            self.player.set_state(gst.STATE_READY)

    def play(self):
        if self.av_uri is not None:
            if self.player.set_state(gst.STATE_PLAYING) == \
                 gst.STATE_CHANGE_FAILURE:
                log.error("gst_renderer error while trying to play")
                return
            self.player_state = 1
        else:
            log.info("av_uri is None, unable to play.")

    def stop(self):
        self.player.set_state(gst.STATE_NULL)
        if self.player.set_state(gst.STATE_READY) == gst.STATE_CHANGE_FAILURE:
            log.error("error stopping")
            return
        self.player_state = 0

        self.av_uri = self.__av_uri

    def pause(self):
        if self.player.set_state(gst.STATE_PAUSED) == gst.STATE_CHANGE_FAILURE:
            log.error("error pausing")
            return
        self.player_state = 2

    def seek(self, unit, target):
        if unit == "ABS_TIME":
            target_time = self.convert_int(target)
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target_time)

        if unit == "REL_TIME":
            target_time = self.convert_int(target)
            cur_pos = self.query_position()[1]
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target_time+cur_pos)

        if unit == "ABS_COUNT":
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target)

        if unit == "REL_COUNT":
            cur_pos = self.query_position()[1]
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH,
                                    target + cur_pos)

    def set_volume(self, volume):
        self.current_volume = volume
        self.mp3audiosink.set_property("volume", volume * 65535 / 100)
        self.aacaudiosink.set_property("volume", volume * 65535 / 100)

    def get_volume(self):
        self.current_volume = \
                self.mp3audiosink.get_property("volume") * 100 / 65535
        return self.mp3audiosink.get_property("volume") * 100 / 65535

    def query_duration(self):
        time.sleep(0.3)
        try:
            dur_int = self.player.query_duration(self.time_format, None)[0]
            dur_str = self.convert_ns(dur_int)
        except:
            dur_int = -1
            dur_str = ''

        return dur_str, dur_int

    def query_position(self):
        try:
            pos_int = self.player.query_position(self.time_format, None)[0]
            pos_str = self.convert_ns(pos_int)
        except:
            pos_int = -1
            pos_str = ''

        return pos_str, pos_int

    def convert_ns(self, time):
        time = time / 1000000000
        time_base = [3600, 60, 1]
        result = []
        append = result.append
        for base_item in time_base:
            time_unit, time = divmod(time, base_item)
            append(time_unit)
        result = tuple(result)
        return '%02d:%02d:%02d' % result

    def convert_int(self, time_str):
        time_str = time_str.strip('")( ')
        (hours, min, sec) = time_str.split(":")
        time_int = int(hours) * 3600 + int(min) * 60 + int(sec)
        time_int = time_int * 1000000000
        return time_int
