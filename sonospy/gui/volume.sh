#!/bin/bash
# CronTab this for max effect * * * * <pathtoscript>

# Check if sonospy is running.
pycPOINT=$(echo $(ps -o pid= -p `cat < ~/Applications/sonospy/pycpoint.pid`))

# Check the current time.  If it is after 11pm set the max volume to 20%
# If it is after midnight and before 7am, set it to 0.

curTIME=`date +%k%M`

if [ "$curTIME" -gt  2300 ]
then
        maxVOLUME=20
else
        maxVOLUME=50
fi

if [ "$curTIME" -gt 0 -a  "$curTIME" -lt 700 ]
then
        # Effetively mute it.
        maxVOLUME=0
else
        maxVOLUME=50
fi

if [ "$#" -ne 1 ]
then
        echo "Enter a zone name, please."
        exit
else
        # Check if sonospy is running.
        if [ "$pycPOINT" -gt 0 ]
        then
                stripME="VOLUME::"

                # If we've made it this far, we are checking now to see if the current volume is > maxVOLUME
                # as defined above.  If it is, reset the volume.

                # Set the zone to the input from $1
                curl http://192.168.1.110:50101/data/rendererData?data=R::"$1"%20%28ZP%29

                # Send it one command to refresh it -- not sure i need this.
                INFO=$(curl -s $(echo "http://192.168.1.110:50101/data/rendererAction?data=class" | sed 's/ //g'))
                # Strip it just down to the volume number, no other information.
                INFO=${INFO#*$stripME}
                OUTPUT=$(echo $INFO|cut -d \_ -f1)

                # Check our logic here to compare. Set volume accordingly.
                if [ "$OUTPUT" -gt "$maxVOLUME" ]
                then
                        echo -e "\n-----------------------\nZone: $1 is over max volume\n-----------------------"
                        curl http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$maxVOLUME
                else
                        curl http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$OUTPUT
                fi
        else
                echo "Sonospy not running..."
                cd ~/Applications/sonospy
                ./sonospy_web -sSonospy=00_EntireCollection,00_EntireCollection.sdb,userindex.ini
                cd -
        fi
