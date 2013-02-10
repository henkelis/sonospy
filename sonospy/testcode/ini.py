

class SMAPI(object):
    def __init__(self, name):
        self.name = name
        self.ms = MediaServer(self)
    def load_ini(self):
        self.ininame = self.name

class DCD(object):
    def __init__(self, name):
        self.name = name
        self.ms = MediaServer(self)
    def load_ini(self):
        self.ininame = self.name

class MediaServer(object):
    def __init__(self, ini):
        # ini is loaded from reference to caller
        self.ini = ini
    def printini(self):
        print self.ini.name


S = SMAPI('SMAPI')
S.load_ini()
print S.ininame
S.ms.printini()

D = DCD('DCD')
D.load_ini()
print D.ininame
D.ms.printini()

