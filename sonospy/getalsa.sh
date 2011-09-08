#!/bin/sh
pactl list | grep -A 2 'Source #' | sed -ne 's/^.*Name: \(.\+\.monitor\)$/\1/p' | grep -iv headset | head -n 1 >alsa.device
