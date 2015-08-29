#!/bin/bash
# CronTab this for max effect * * * * <pathtoscript>

#CHANGE ME FOR MAX VOLUME FOR THE ZONES
maxVOLUME=50
maxVOLUME2=50

stripME="VOLUME::"
stripME2="VOLUME::"

# Do the deck zone -- never >  $maxVOLUME
curl http://192.168.1.110:50101/data/rendererData?data=R::Deck%20%28ZP%29
INFO=$(curl -s $(echo "http://192.168.1.110:50101/data/rendererAction?data=class" | sed 's/ //g'))
INFO=${INFO#*$stripME}
OUTPUT=$(echo $INFO|cut -d \_ -f1)

if [ "$OUTPUT" -gt "$maxVOLUME" ]
then
#	echo -e "\n-----------------------\nDeck is over max volume\n--------------------"
        curl http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$maxVOLUME
else
        curl http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$OUTPUT
fi

# Do the spa zone -- never >  $maxVOLUME
curl http://192.168.1.110:50101/data/rendererData?data=R::Spa%20%28ZP%29
INFO2=$(curl -s $(echo "http://192.168.1.110:50101/data/rendererAction?data=track" | sed 's/ //g'))
INFO2=${INFO2#*$stripME2}
OUTPUT2=$(echo $INFO2|cut -d \_ -f1)

if [ "$OUTPUT2" -gt "$maxVOLUME2" ]
then
#	echo -e "\n-----------------------\nSpa is over max volume\n--------------------"
        curl http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$maxVOLUME2
else
        curl http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$OUTPUT2
fi


