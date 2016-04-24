#!/bin/bash
# Daemonized loop below for use with volumed.sh
#----------------------------------------------------------------------------

# Set to 1 to enable debugging. Set to 0 or nothing to turn it off.
debug=0

# ---------------------------------------------------------------------------
# TROUBLE SHOOTING?
# ---------------------------------------------------------------------------
# Having problems?  It is probably your port number in the below.

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
# sonosZONE = <zone name>:<max volume>
# ipADDR = ip address of machine running Sonospy
# portNUM = Sonospy's pycpoint.ini file setting
# timeOUT = how often do you want to run the loop
# safetyTimeSTART = Time to start stepping volume down (in 24hr notation)
# safetyTimeSTOP = Time to move to muteTimeStart (1 min before muteTimeSTART)
# muteTimeSTART = Time to force the zones to have 0 volume
# muteTimeSTOP = Time to let the sonosZONE volumes to kick back in

sonosZONE=( BBQ:60 Spa:75 Firepit:60 Kitchen:70 )
ipADDR="192.168.1.110"
portNUM="50108"
timeOUT=1
safetyTimeSTART=2300
safetyTimeSTOP=2359
safetyTimeVOL=25
muteTimeSTART=0
muteTimeSTOP=700

# Check if Sonospy is running, if it fails this test, skip past the loop
# and kill the daemon.

while [ "`pgrep -f pycpoint`" != "" ]
do
	# Anything lower than 10 seems to create weird logic problems when
	# polling the current volume of a zone.  Not sure if it is related
	# to what I'm doing here or what Mark is doing within Sonospy.
	sleep "$timeOUT"

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
                curl -s http://"$ipADDR":"$portNUM"/data/rendererData?data=R::"$zoneNAME"%20%28ZP%29 &>/dev/null
                # Grab the relevant information about the zone so we can check the volume.
                INFO=$(curl -s $(echo "http://$ipADDR:$portNUM/data/rendererAction?data=class" | sed 's/ //g'))

                #--------------------------------------------------------------------------------------
                # DEBUG
                #--------------------------------------------------------------------------------------
		if (( "$debug" )); then
			echo -e "INFO:\t$INFO"
			echo -e "ZONEARRAY:\t$i\tPARSEDNAME:\t$zoneNAME\tPARSEDVOL:\t$maxVOLUME"
		fi
	        # Check the current time.  If it is after 11pm set the max volume to 20%
        	# If it is after midnight and before 7am, set it to 0. Exclude inside the house.
	        curTIME=`date +%k%M`
		if [ "$zoneNAME" != "Kitchen" ]
		then
	        	if [ "$curTIME" -gt  "$safetyTimeSTART" -a "$curTIME" -lt "$safetyTimeSTOP" ]
	        	then
        	        	maxVOLUME="$safetyVOL"
	        	fi

	        	if [ "$curTIME" -gt "$muteTimeSTART" -a  "$curTIME" -lt "$muteTimeSTOP" ]
		        then
        		        # Effectively mute it.
                		maxVOLUME=0
		        fi
		fi
		# If we've made it this far, we are checking now to see if the current volume is > maxVOLUME
		# as defined above.  If it is, reset the volume.

                #--------------------------------------------------------------------------------------
                # DEBUG
                #--------------------------------------------------------------------------------------
		if (( "$debug" )); then
			echo -e "CURL INFO:\t\t$INFO"
		fi
		# Strip it just down to the volume number, no other information.
		INFO=${INFO#*"VOLUME::"}
		OUTPUT=$(echo $INFO|cut -d \_ -f1)

		#--------------------------------------------------------------------------------------
		# DEBUG
		#--------------------------------------------------------------------------------------
		if (( "$debug" )); then
			echo -e "INFO STRIPPED:\t$INFO"
			echo -e "ZONE: \t\t$i\tCURRENTVOLUME:\t$OUTPUT\tMAXVOLUME:\t$maxVOLUME"
		fi

		# In the off chance that sonospy dies while the daemon is running, this is here to 
		# prevent errors from being printed to the shell.  The loop will fail once, then
		# will stop the daemon below.
		if [ "$OUTPUT" == "" ]
		then
			OUTPUT=0
		fi

		if [ "$OUTPUT" == "NOCHANGE::0_|_" ]
		then
			OUTPUT=0
		fi

		if [ "$maxVOLUME" == "" ]
		then
			maxVOLUME=0
		fi

		# Check our logic here to compare. Set volume accordingly.  Compare it
		# against maxVOLUME (as defined above) and then if it is violating that rule, lower the
		# volume.
		if [ "$OUTPUT" -gt "$maxVOLUME" ]
		then
	                #--------------------------------------------------------------------------------------
        	        # DEBUG
                	#--------------------------------------------------------------------------------------
			if (( "$debug" )); then
				echo -e "\t\t\t\tSetting zone:\t$zoneNAME\tCurrent Volume\t$OUTPUT\tto limit\t$maxVOLUME"
			fi
	        	curl -s http://"$ipADDR":"$portNUM"/data/rendererAction?data=VOLUME::"$maxVOLUME" &>/dev/null
		fi
	done
done

# If the loop fails, Sonospy isn't running, at which point kill the daemon
echo -e "\nSonospy has stopped running..."
sh /home/chow/Applications/sonospy/sonospy/gui/volumed.sh stop
echo -ne $FAKE_PROMPT
exit 0
