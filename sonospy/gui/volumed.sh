#!/bin/bash
#!/bin/sh

# Quick start-stop-daemon example, derived from Debian /etc/init.d/ssh
# Taken from: https://gist.github.com/alobato/1968852
# --------------------------------------------------------------------
# TO DO:
#	1) Set up daemon so that it checks if it is running before
#	   starting

set -e

# Must be a valid filename
NAME="Sonospy Volume Monitor"
PIDFILE=~/Applications/sonospy/sonospy/gui/volume.pid

#This is the command to be run, give the full pathname
DAEMON=~/Applications/sonospy/sonospy/gui/volume.sh
DAEMON_OPTS=""

export PATH="${PATH:+$PATH:}/usr/sbin:/sbin"

case "$1" in
  start)
        echo "Starting daemon: "$NAME
	start-stop-daemon --start --quiet --make-pidfile --pidfile $PIDFILE --exec $DAEMON -- $DAEMON_OPTS
	;;
  stop)
        echo "Stopping daemon: "$NAME
	start-stop-daemon --stop --quiet --oknodo --pidfile $PIDFILE
	;;
  restart)
        echo "Restarting daemon: "$NAME
	start-stop-daemon --stop --quiet --oknodo --retry 30 --pidfile $PIDFILE
	start-stop-daemon --start --make-pidfile --quiet --pidfile $PIDFILE --exec $DAEMON -- $DAEMON_OPTS
	;;

  *)
	echo "Usage: "$1" {start|stop|restart}"
	exit 1
esac

exit 0
