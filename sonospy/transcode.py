
import subprocess
import os
from brisa.core import log

transcodetable_extension = {'mp2': 'mp3', 'pc': 'wav'}
transcodetable_resolution = {'flac': ((48000, 16, 2, 'flac'),(48000, 16, 6, 'flac'))} # tuple = samplerate, bitspersample, channels, fileextension

def checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec):

    transcode = False
    newtype = None
    
    if filetype.lower() in transcodetable_extension.keys():
    
        transcode = True
        newtype = "%s.%s" % (filetype.lower(), transcodetable_extension[filetype.lower()])
        
    elif filetype.lower() in transcodetable_resolution.keys():
    
        for entry in transcodetable_resolution[filetype.lower()]:
            max_samplerate, max_bitspersample, num_channels, res_type = entry
            log.debug(max_samplerate)
            log.debug(max_bitspersample)
            log.debug(num_channels)
            log.debug(res_type)
            if int(channels) == num_channels:
                log.debug(channels)
                if int(samplerate) > max_samplerate or int(bitspersample) > max_bitspersample:
                    log.debug(samplerate)
                    log.debug(bitspersample)
                    transcode = True
                    newtype = "%s_%s_%s.%s_%s_%s.%s" % (bitspersample, int(int(samplerate)/1000), channels, max_bitspersample, int(int(max_samplerate)/1000), 2, res_type)
                    log.debug(newtype)
            
    return transcode, newtype

streams = ['http://', 'rtsp://']

def checkstream(filename, filetype):

    stream = False
    newtype = None
    for s in streams:
        if filename.startswith(s):
            stream = True
            newtype = "%s.%s" % ('stream', filetype.lower())

    return stream, newtype

def transcode(inputfile, transcodetype):

    log.debug(inputfile)
    log.debug(transcodetype)

    devnull = file(os.devnull, 'ab')

    if transcodetype == 'mp2.mp3':
        # transcode using lame
        # lame -s 48 -V0 --vbr-new -h -Y -m j <inputfile.mp2> -
        sub = subprocess.Popen([
                "lame",
                "-s", "48",
                "-V", "0",
                "--vbr-new", 
                "-h",
                "-Y",
                "-m", "j",
                inputfile,
                "-"],
                stdout=subprocess.PIPE,
                stderr=devnull)
        return sub.stdout

    if transcodetype == 'pc.wav':
        # parec --device=alsa_output.pci-0000_00_1b.0.analog-stereo.monitor --format=s16le --rate=44100 --channels=2 | sox --type raw -s2L --rate 44100 --channels 2 - --type wav -
        # use '''pactl list | grep -A2 'Source #' | grep 'Name: ' | cut -d" " -f2''' to get device
        
        p1 = subprocess.Popen([
                "parec",
                "--device=alsa_output.pci-0000_00_1b.0.analog-stereo.monitor",
                "--format=s16le",
                "--rate=44100",
                "--channels=2"],
                stdout=subprocess.PIPE,
                stderr=devnull)
        p2 = subprocess.Popen([
                "sox",
                "--type", "raw",
                "-s2L",
                "--rate", "44100",
                "--channels", "2",
                "-",
                "--type", "wav",
                "-"],
                stdin=p1.stdout,
                stdout=subprocess.PIPE,
                stderr=devnull)
        return p2.stdout

    elif transcodetype.startswith('stream.'):
        # transcode using vlc
        
        log.debug(inputfile)

        p1 = subprocess.Popen([
            "vlc",
            "--quiet",
            "--intf=dummy",
            inputfile,
            "--sout=file/wav:-"],
            stdout=subprocess.PIPE,
            stderr=devnull)

        return p1.stdout

        # temp testing with mplayer follows
        # (mplayer does not seem to like redirecting to stdout)
        #mplayer -really-quiet -vc null -vo null -ao pcm:nowaveheader:file=/dev/fd/4 - 4>&1 1>/dev/null | lame] --silent -r -x -q  - -
        '''
        p1 = subprocess.Popen([
                "mplayer",
                "-really-quiet",
                "-nolirc",
                "-dumpaudio",
                "-dumpfile /dev/stdout"],
#                "-vo null",
#                "-msglevel all=-1",
#                "-ao pcm:fast:file=/dev/stdout",
#                "-ao pcm:file=/dev/stdout",
#                inputfile],
#                bufsize=40000,
                stdout=subprocess.PIPE,
                stderr=devnull)

        return p1.stdout
        '''

    transcodefacets = transcodetype.split('.')

    if transcodefacets[0].endswith('2') and transcodefacets[1] == '16_48_2' and transcodefacets[2] == 'flac':
        # transcode using sox
        # sox <inputfile.flac> -C 0 -b 16 -r 48000 -t flac -
        sub = subprocess.Popen([
                "sox",
                inputfile,
                "-C", "0",
                "-b", "16",
                "-r", "48000",
                "-t", "flac",
                "-"],
                stdout=subprocess.PIPE,
                stderr=devnull)

    elif transcodefacets[0].endswith('6') and transcodefacets[1] == '16_48_2' and transcodefacets[2] == 'flac':
        # transcode using sox
        # sox <inputfile.flac> -C 0 -b 16 -r 48000 -t flac - remix 1-3 4-6
        sub = subprocess.Popen([
                "sox",
                inputfile,
                "-C", "0",
                "-b", "16",
                "-r", "48000",
                "-t", "flac",
                "-",
                "remix", "1-3", "4-6"],
                stdout=subprocess.PIPE,
                stderr=devnull)

    # this one doesn't do anything, left as example
    elif transcodetype == '@@@@@@':
        # transcode using flac/sox/flac pipeline
        # flac <inputfile.flac> -d -c | sox -t wav - -r 48000 -2 -t wav - | flac - 
        p1 = subprocess.Popen([
                "flac",
                inputfile,
                "-d",
                "-c"],
                stdout=subprocess.PIPE,
                stderr=devnull)

        p2 = subprocess.Popen([
                "sox",
                "-t", "wav",
                "-",
                "-r", "48000",
                "-2",
                "-t", "wav",
                "-"],
                stdin=p1.stdout,
                stdout=subprocess.PIPE,
                stderr=devnull)

        p3 = subprocess.Popen([
                "flac",
                "-"],
                stdin=p2.stdout,
                stdout=subprocess.PIPE,
                stderr=devnull)
                
        sub = p3

    return sub.stdout


