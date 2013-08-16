
import subprocess
import os
import codecs
from brisa.core import log

transcodetable_extension = {'mp2': 'mp3', 'pc': 'wav', 'ac3': 'mp3'}
smapitranscodetable_extension = {'mp2': 'mp3', 'pc': 'wav', 'ac3': 'mp3'}
#smapitranscodetable_extension = {'flac': 'mp3'}
#smapitranscodetable_extension = {'flac': 'ogg'}
transcodetable_resolution = {'flac': ((48000, 16, 2, 'flac'),(48000, 16, 6, 'flac'))} # tuple = samplerate, bitspersample, channels, fileextension
smapitranscodetable_resolution = {'flac': ((48000, 16, 2, 'flac'),(48000, 16, 6, 'flac'))} # tuple = samplerate, bitspersample, channels, fileextension

alsa_device_file = 'alsa.device'
alsa_device_script = os.path.join(os.getcwd(), 'getalsa.sh')
alsa_device = ''

def setalsadevice():
    global alsa_device
    if not os.access(alsa_device_file, os.R_OK):
        subprocess.Popen(alsa_device_script).wait()
    try:
        f = codecs.open(alsa_device_file, encoding='utf-8')
        alsa_device = f.readline().strip()
    except:
        pass
        
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

def checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec):

    transcode = False
    newtype = None
    ext = None
    
    if filetype.lower() in smapitranscodetable_extension.keys():
    
        transcode = True
        newtype = "%s.%s" % (filetype.lower(), smapitranscodetable_extension[filetype.lower()])
        ext = smapitranscodetable_extension[filetype.lower()]
        
    elif filetype.lower() in smapitranscodetable_resolution.keys():
    
        for entry in smapitranscodetable_resolution[filetype.lower()]:
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
                    ext = res_type
                    log.debug(newtype)
            
    return transcode, newtype, ext
    
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

    if transcodetype == 'ac3.mp3':
        # transcode using ffmpeg
        # ffmpeg -i <inputfile.ac3> -acodec libmp3lame -ab 320k -f mp3 -
        sub = subprocess.Popen([
                "ffmpeg",
                "-i",
                inputfile,
                "-acodec", "libmp3lame",
                "-ab", "320k",
                "-f", "mp3",
                "-"],
                stdout=subprocess.PIPE,
                stderr=devnull)
        return sub.stdout

    elif transcodetype == 'pc.wav':
        # parec --device=alsa_output.pci-0000_00_1b.0.analog-stereo.monitor --format=s16le --rate=44100 --channels=2 | sox --type raw -s2L --rate 44100 --channels 2 - --type wav -
        # use '''pactl list | grep -A2 'Source #' | grep 'Name: ' | cut -d" " -f2''' to get device
        
        p1 = subprocess.Popen([
                "parec",
                "--device=%s" % alsa_device,
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

    elif transcodetype == 'flac.mp3.old':
        # transcode using vlc
        
        log.debug(inputfile)

        p1 = subprocess.Popen([
            "vlc",
            "--quiet",
            "--intf=dummy",
            inputfile,
            "--sout=file/mp3:-"],
            stdout=subprocess.PIPE,
            stderr=devnull)

        return p1.stdout

    elif transcodetype == 'flac.mp3':
        # transcode using flac/lame
        # flac <inputfile.flac> -d -c | lame -s 48 -V0 --vbr-new -h -Y -m j - -
        
        p1 = subprocess.Popen([
                "flac",
                inputfile,
                "-d",
                "-c"],
                stdout=subprocess.PIPE,
                stderr=devnull)

        p2 = subprocess.Popen([
                "lame",
                "-s", "48",
                "-V", "0",
                "--vbr-new", 
                "-h",
                "-Y",
                "-m", "j",
                "-",
                "-"],
                stdin=p1.stdout,
                stdout=subprocess.PIPE,
                stderr=devnull)

        return p2.stdout

    elif transcodetype == 'flac.ogg':
        # transcode using flac
        # flac <inputfile.flac> -d -c --ogg -
       
        log.debug(inputfile)

        p1 = subprocess.Popen([
                "flac",
                inputfile,
                "-d",
                "-c",
                "--ogg",
                "-"],
                stdout=subprocess.PIPE,
                stderr=devnull)

        return p1.stdout
        
    elif transcodetype == 'flac.wav':
        # transcode using sox
        # not currently supported by streaming api
        
        log.debug(inputfile)

        p1 = subprocess.Popen([
                "sox",
                inputfile,
                "-s2L",
                "--rate", "44100",
                "--channels", "2",
                "--type", "wav",
                "-"],
                stdout=subprocess.PIPE,
                stderr=devnull)
        return p1.stdout

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


