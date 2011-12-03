import mutagen
from mutagen.easyid3 import EasyID3
print EasyID3.valid_keys.keys()

audio = mutagen.File("/home/mark/Music/GD/Green Day - Christians Inferno [Album Version].mp3")
print str(audio)
print str(audio.keys())

audio = mutagen.File("/home/mark/Music/GD/Green Day - Christians Inferno [Album Version].mp3", easy=True)
print str(audio)
print str(audio.keys())

