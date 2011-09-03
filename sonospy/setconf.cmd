rem #{'encoding': 'utf-8',
rem # 'listen_interface': 'eth0',
rem # 'logging': 'DEBUG',
rem # 'logging_output': 'stdout',
rem # 'owner': 'brisa',
rem # 'version': '0.10.0',
rem # 'webserver_adapter': 'cherrypy'}

python brisa-conf -i brisa
python brisa-conf -d -s brisa
python brisa-conf -s brisa -p encoding utf-8
python brisa-conf -s brisa -p listen_interface eth0
python brisa-conf -s brisa -p logging DEBUG
rem python brisa-conf -s brisa -p logging INFO
python brisa-conf -s brisa -p logging_output stdout
python brisa-conf -s brisa -p owner brisa
python brisa-conf -s brisa -p version 0.10.0
rem python brisa-conf -s brisa -p webserver_adapter cherrypy
rem python brisa-conf -s brisa -p webserver_adapter circuits.web
python brisa-conf -i brisa
