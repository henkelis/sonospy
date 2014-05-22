@echo off

:: Check if any parameters were passed

IF "%~1"=="" GOTO NoParams

echo off
cd sonospy
pythonw pycpoint.py %* >../pycpoint.log 2>&1 

@echo off
cd ..
GOTO eof

:NoParams
echo "No arguments were passed. Exiting."
GOTO eof

:eof
