#{'encoding': 'utf-8',
# 'listen_interface': 'eth0',
# 'logging': 'DEBUG',
# 'logging_output': 'stdout',
# 'owner': 'brisa',
# 'version': '0.10.0',
# 'webserver_adapter': 'cherrypy'}

brisa-conf -d -s brisa
brisa-conf -s brisa -p encoding utf-8
brisa-conf -s brisa -p listen_interface eth0
#brisa-conf -s brisa -p logging INFO
brisa-conf -s brisa -p logging DEBUG
brisa-conf -s brisa -p logging_output stdout
brisa-conf -s brisa -p owner brisa
brisa-conf -s brisa -p version 0.10.0
#brisa-conf -s brisa -p webserver_adapter cherrypy
#brisa-conf -s brisa -p webserver_adapter circuits.web
brisa-conf -i brisa
