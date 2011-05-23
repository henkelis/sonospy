import sqlite3
import os

class proxy(object):
    def __init__(self, proxyname):
        self.proxyname = proxyname

class log(object):
    @staticmethod
    def debug(dstr):
        print dstr

class skeys(object):

    use_sorts = True
    def __init__(self, database, proxyname):
        self.dbname = database
        self.proxy = proxy(proxyname)
        self.log = log()

    def checkkeys(self, proxy, proxykey, controller, controllerkey):
        proxykeys = proxy.lower().split(',')
        proxykeys = [k.strip() for k in proxykeys]
        proxykeys = [k for k in proxykeys if k != '']
        proxyfound = proxykey.lower() in proxykeys or 'all' in proxykeys

        controllerkeys = controller.lower().split(',')
        controllerkeys = [k.strip() for k in controllerkeys]
        controllerkeys = [k for k in controllerkeys if k != '']
        controllerfound = controllerkey.lower() in controllerkeys or 'all' in controllerkeys

        return proxyfound and controllerfound

    def get_orderby(self, sorttype, controller):
        # TODO: only load this on start and updateid change
        if not self.use_sorts:
            return [(None, None, None, 10, 'dummy', None)]
        order_out = []
        db = sqlite3.connect(os.path.join(os.getcwd(), self.dbname))
        db.create_function("checkkeys", 4, self.checkkeys)
        c = db.cursor()
        try:
            # check for info for this controller and proxy
#            statement1 = """select sort_order, sort_prefix, sort_suffix, album_type, header_name from sorts where checkkey(proxyname, "%s") and checkkey(controller, "%s") and sort_type="%s" and active is not null and active!="" order by sort_seq""" % (self.proxy.proxyname, controller, sorttype)
            statement1 = """select sort_order, sort_prefix, sort_suffix, album_type, header_name from sorts where checkkeys(proxyname, "%s", controller, "%s") and sort_type="%s" and active is not null and active!="" order by sort_seq""" % (self.proxy.proxyname, controller, sorttype)
            # check for info for this controller and any proxy
#            statement2 = """select sort_order, sort_prefix, sort_suffix, album_type, header_name from sorts where checkkey(proxyname, "ALL") and checkkey(controller, "%s") and sort_type="%s" and active is not null and active!="" order by sort_seq""" % (controller, sorttype)
            # check for info for this proxy and any controller
#            statement3 = """select sort_order, sort_prefix, sort_suffix, album_type, header_name from sorts where checkkey(proxyname, "%s") and checkkey(controller, "ALL") and sort_type="%s" and active is not null and active!="" order by sort_seq""" % (self.proxy.proxyname, sorttype)
            # check for info for any proxy and any controller
#            statement4 = """select sort_order, sort_prefix, sort_suffix, album_type, header_name from sorts where checkkey(proxyname, "ALL") and checkkey(controller, "ALL") and sort_type="%s" and active is not null and active!="" order by sort_seq""" % (sorttype)
            # process checks in sequence, accepting first one found
#            statement_list = [statement1, statement2, statement3, statement4]
            statement_list = [statement1]
            for statement in statement_list:
                c.execute(statement)
                log.debug(statement)
                count = 0
                for row in c:
                    log.debug(row)
                    count += 1
                    so, sp, ss, albumtypestring, hn = row
                    # special case for album
                    if sorttype == 'ALBUM':
                        if not albumtypestring:
                            albumtypestrings = ['album']
                        else:
                            albumtypestrings = albumtypestring.split(',')
                            albumtypestrings = [k.strip() for k in albumtypestrings]
                            albumtypestrings = [k for k in albumtypestrings if k != '']
                            if not 'album' in albumtypestrings:
                                albumtypestrings.insert(0, 'album')
                        ats = []
                        for at in albumtypestrings:
                            albumtypenum, table = self.translate_albumtype(at, sorttype)
                            ats.append(albumtypenum)
                        albumtypenum = ats
                    else:
                        albumtypenum, table = self.translate_albumtype(albumtypestring, sorttype)
                    order_out.append((so, sp, ss, albumtypenum, table, hn))
                if count != 0:
                    break
        except sqlite3.Error, e:
            print "Error getting sort info:", e.args[0]
        c.close()
        if order_out == []:
            return [(None, None, None, 10, 'dummy', None)]
        log.debug(order_out)
        return order_out

    def translate_albumtype(self, albumtype, table):
        if not albumtype or albumtype == '':
            return '10', 'album'
        elif albumtype == 'album':
            return '10', albumtype
        elif albumtype == 'virtual':
            if table == 'COMPOSER_ALBUM':
                return '25', albumtype
            elif table == 'ARTIST_ALBUM':
                return '26', albumtype
            elif table == 'ALBUMARTIST_ALBUM':
                return '27', albumtype
            elif table == 'CONTRIBUTINGARTIST_ALBUM':
                return '28', albumtype
        elif albumtype == 'work':
            if table == 'COMPOSER_ALBUM':
                return '31', albumtype
            elif table == 'ARTIST_ALBUM':
                return '32', albumtype
            elif table == 'ALBUMARTIST_ALBUM':
                return '33', albumtype
            elif table == 'CONTRIBUTINGARTIST_ALBUM':
                return '34', albumtype

        elif albumtype == 'composer_virtual':
            return '25', albumtype
        elif albumtype == 'artist_virtual':
            return '26', albumtype
        elif albumtype == 'albumartist_virtual':
            return '27', albumtype
        elif albumtype == 'contributingartist_virtual':
            return '28', albumtype

        elif albumtype == 'composer_work':
            return '31', albumtype
        elif albumtype == 'artist_work':
            return '32', albumtype
        elif albumtype == 'albumartist_work':
            return '33', albumtype
        elif albumtype == 'contributingartist_work':
            return '34', albumtype

        else:
            return '10', 'album'

print skeys('sonos.db', 'sonos').get_orderby('ALBUM', 'CR200')
print "======================="
print skeys('sonos.db', 'sonos').get_orderby('ALBUM', 'ALL')
print "======================="
print skeys('sonos.db', 'sonos').get_orderby('ALBUM', 'CR200')
print "======================="
print skeys('sonos.db', 'summary').get_orderby('ALBUM', 'CR200')
print "======================="
print skeys('sonos.db', 'summary').get_orderby('ALBUM', 'ACR')

