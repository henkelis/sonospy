#!/bin/bash
# Daemonized loop below for use with volumed.sh
#----------------------------------------------------------------------------

# Add zones here, separate zone names with a space.  They are case
# sensitive. Enter desired max default volume after the colon.
# <zone name>:<max volume>

sonosZONE=( Deck:40 Spa:50 )

while :
do
	# Anything lower than 10 seems to create weird logic problems when
	# polling the current volume of a zone.  Not sure if it is related
	# to what I'm doing here or what Mark is doing within Sonospy.
	sleep 10

	# Loop through the zones and check their volume.  Reset accordingly.
	for i in "${sonosZONE[@]}"
	do
		# Parse our zone name and our max volume settings out of
		# the sonosZONE[@] string provided. -1 below is to parse
		# up until the :, 2- indicates to take anything AFTER
		# the colon.
		zoneNAME="$( cut -d ':' -f -1 <<< "$i" )"
		maxVOLUME="$( cut -d ':' -f 2- <<< "$i" )"

                # Set the zone to the input from $sonosZONE
                curl -s http://192.168.1.110:50101/data/rendererData?data=R::"$zoneNAME"%20%28ZP%29 &>/dev/null
                # Grab the relevant information about the zone so we can check the volume.
                INFO=$(curl -s $(echo "http://192.168.1.110:50101/data/rendererAction?data=class" | sed 's/ //g'))

                #--------------------------------------------------------------------------------------
                # UNCOMMENT TO DEBUG
                #--------------------------------------------------------------------------------------
		# echo -e "ZONEARRAY:\t$i\tPARSEDNAME:\t$zoneNAME\tPARSEDVOL:\t$maxVOLUME"

	        # Check the current time.  If it is after 11pm set the max volume to 20%
        	# If it is after midnight and before 7am, set it to 0.
	        curTIME=`date +%k%M`

	        if [ "$curTIME" -gt  2300 -a "$curTIME" -lt 2359 ]
        	then
                	maxVOLUME=20
	        fi

        	if [ "$curTIME" -gt 0 -a  "$curTIME" -lt 700 ]
	        then
        	        # Effectively mute it.
                	maxVOLUME=0
	        fi

		# If we've made it this far, we are checking now to see if the current volume is > maxVOLUME
		# as defined above.  If it is, reset the volume.

                #--------------------------------------------------------------------------------------
                # UNCOMMENT TO DEBUG
                #--------------------------------------------------------------------------------------
		# echo -e "CURL INFO:\t\t$INFO\"

		# Strip it just down to the volume number, no other information.
		INFO=${INFO#*"VOLUME::"}
		OUTPUT=$(echo $INFO|cut -d \_ -f1)

		#--------------------------------------------------------------------------------------
		# UNCOMMENT TO DEBUG
		#--------------------------------------------------------------------------------------
		# echo -e "INFO STRIPPED:\t$INFO\"
		# echo -e "ZONE: \t\t$i\tCURRENTVOLUME:\t$OUTPUT\tMAXVOLUME:\t$maxVOLUME"

		# Check our logic here to compare. Set volume accordingly.  Compare it
		# against maxVOLUME (as defined above) and then if it is violating that rule, lower the
		# volume.
		if [ "$OUTPUT" -gt "$maxVOLUME" ]
		then
	                #--------------------------------------------------------------------------------------
        	        # UNCOMMENT TO DEBUG
                	#--------------------------------------------------------------------------------------
			# echo -e "\t\t\t\tSetting zone:\t$zoneNAME\tCurrent Volume\t$OUTPUT\tto limit\t$maxVOLUME"
	        	curl -s http://192.168.1.110:50101/data/rendererAction?data=VOLUME::$maxVOLUME &>/dev/null
		fi
	done
done
