# -*- coding: utf-8 -*- 
import urllib
import re
from xml.sax.saxutils import escape, unescape
import os
import socket
import time
from struct import pack
if os.name != 'nt':
    import fcntl

socket.setdefaulttimeout(15)

def get_ip_address(ifname):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, pack('256s', str(ifname[:15])))[20:24])
        return ip
    except:
        return socket.gethostbyname(socket.gethostname())

def get_active_ifaces():
    if os.name == 'nt':
        return [socket.gethostbyname(socket.gethostname())]
    else:
        try:
            rd = open('/proc/net/route').readlines()
        except (IOError, OSError):
            return [socket.gethostbyname(socket.gethostname())]
        net = [line.split('\t')[0:2] for line in rd]
        return [v[0] for v in net if v[1] == '00000000']    

active_ifaces = get_active_ifaces()
#print active_ifaces
ip_address = get_ip_address(active_ifaces[0])
#print ip_address

escape_entities = {'"' : '&quot;', "'" : '&apos;', " " : '%20'}
escape_entities_quotepos = {'"' : '&quot;', "'" : '&apos;'}
unescape_entities_quotepos = {'&quot;' : '"', '&apos;' : "'"}

url_escape_entities = {
                   " " : '%20',
                   "!" : '%21',
                   '"' : '%22',
                   "#" : '%23',
                   "$" : '%24',
#                   "%" : '%25',
                   "&" : '%26',
                   "'" : '%27',
                   "(" : '%28',
                   ")" : '%29',
                   "*" : '%2A',
                   "+" : '%2B',
                   "," : '%2C',
                   "-" : '%2D',
                   "." : '%2E',
                   "/" : '%2F',
                   ":" : '%3A',
                   ";" : '%3B',
                   "<" : '%3C',
                   "=" : '%3D',
                   ">" : '%3E',
                   "?" : '%3F',
                   "@" : '%40',
                   "[" : '%5B',
                   "\\" : '%5C',
                   "]" : '%5D',
                   "^" : '%5E',
                   "_" : '%5F',
                   "{" : '%7B',
                   "|" : '%7C',
                   "}" : '%7D',
                   "~" : '%7E',
                  }


def unwrap_data(datastring):
    # translate the string returned from the server to a list
    datastring = escape(datastring, escape_entities_quotepos)
    datadict = datastring.split('_|_')
    if datadict[len(datadict)-1] == '':
        datadict.pop()
    return datadict

def get_message(datadict):
    # remove any message from the end of the controlpoint response and return it
    message = None
    if datadict[len(datadict)-1].startswith('MESSAGE::'):
        messagestring = datadict.pop()
        message = messagestring.split('::')[1]
    return message

def get_return(datadict):
    # remove any return from the end of the controlpoint response and return it
    ret = None
    if datadict[len(datadict)-1].startswith('RETURN::'):
        retstring = datadict.pop()
        ret = retstring.split('::')[1]
    return ret

def index():
    response.flash = T('Welcome to sonospy')
    # default page - get list of servers and renderers to display
    try:
        datastring=urllib.urlopen('http://' + ip_address + ':50101/data/deviceData').read()
    except IOError:
        response.flash = T('Unable to connect to pycpoint webserver')
        return dict(message='')
    
    datadict = unwrap_data(datastring)
    return dict(message=datadict)

@service.json
def JSONgallery():
    itemcount = 0
    gallery = []
    for row in db().select(db.album.title,db.album.creator,db.album.artname,db.album.data, orderby=db.album.title.upper()):
        print row.title
        print row.creator
        print row.artname
        print row.data
        title = unescape(row.title, unescape_entities_quotepos)
        if title.startswith('<') and title.endswith('>'): title = '[' + title[1:-1] + ']'
        creator = unescape(row.creator, unescape_entities_quotepos)
        data = unescape(row.data, unescape_entities_quotepos)
        gallery.append((row.artname,title,'','',creator,data))
        itemcount += 1
    return gallery

def flow():
    itemcount = 0
    out = ''
    out += '<div id="contentflow" class="ContentFlow">'
    out += '<div class="loadIndicator"><div class="indicator"></div></div>'
    out += '<div class="flow" id="flowtarget">'
    for row in db().select(db.album.title,db.album.creator,db.album.artname,db.album.data, orderby=db.album.title.upper()):
        print row.title
        print row.creator
        print row.artname
        print row.data
        title = unescape(row.title, unescape_entities_quotepos)
        if title.startswith('<') and title.endswith('>'): title = '[' + title[1:-1] + ']'
        creator = unescape(row.creator, unescape_entities_quotepos)
        outtitle = title + "<br/>" + creator
        outtitle = escape(outtitle, escape_entities_quotepos)
        data = unescape(row.data, unescape_entities_quotepos)
        
        datas = data.split('::')
        id = datas[0]
        menu = datas[2]
        
#        if itemcount > 20: continue
        
        out += '<img class="item" id="' + id + '" menu="' + menu + '" src="' + row.artname + '" title="' + outtitle + '" data="' + data + '"></img>'
        itemcount += 1
        
    out += '</div>'
    out += '<div class="globalCaption"></div><br/><br/><br/>'
    out += '<div class="scrollbar"><div class="slider"><div class="position"></div></div></div>'
    out += '</div>'
#    print out
    return out

def insertalbum(id, title, creator, art, item):
    rows = db(db.album.albumid == id).select()
    if len(rows) == 0:
        db.album.insert(albumid=id,
                        title=title,
                        creator=creator,
                        arturi=art,
                        artname='/sonospy/static/art/blank.gif',
                        data=item)
    else:
        db(db.album.id == rows[0].id).update(title=title,
                                             creator=creator,
                                             arturi=art,
#                                             artname='/sonospy/static/art/blank.gif',
                                             data=item)

def clearalbums():
    db.album.truncate()
    redirect('/sonospy/default/index')

@service.json
def JSONloadalbumart(id=''):
    print "JSONloadalbumart"
    print id
    import urllib
    if id == '':
        numrecs = db(db.album.id > 0).count()
        return['count=' + str(numrecs)]    
    else:
        id = int(id)
        rows = db(db.album.id == id).select(db.album.id, db.album.arturi, db.album.artname)
        for row in rows:    # should only be one!
            if row.arturi == '':
                filename = 'applications/sonospy/static/art/blank.gif'
            else:        
                localname = 'applications/sonospy/static/art/' + str(id) + '.jpg'
                print "uri: " + str(row.arturi)
                print "lname: " + str(localname)
                (filename, headers) = urllib.urlretrieve(row.arturi, localname)
                print "headers: " + str(headers)
                if not 'Content-Type' in headers or headers['Content-Type'] == 'text/html':
                    filename = 'applications/sonospy/static/art/blank.gif'
            filename = filename[12:]
            print "fname: " + str(filename)
            db(db.album.id == row.id).update(artname = filename)
        return [id, filename]


def setrenderer():
    # tell the controlpoint which renderer is current
    print "---- setrenderer -----------------------------------"
    print "renderertitle: " + str(request.vars.renderertitle)
    print "renderertype: " + str(request.vars.renderertype)
    print "renderertarget: " + str(request.vars.renderertarget)
    print "queuetarget: " + str(request.vars.queuetarget)
    print "queuedata: " + str(request.vars.queuedata)
    print "queuechain: " + str(request.vars.queuechain)

    ptitle = escape(request.vars.renderertitle, url_escape_entities)
    ptype = request.vars.renderertype
    ptarget = request.vars.renderertarget
    qtarget = request.vars.queuetarget
    qdata = request.vars.queuedata
    qchainparams = request.vars.queuechain

    pentry = ptype + '::' + ptitle
    print "entry: " + str(pentry)

    # get the meta data for this renderer
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/rendererData?data='+pentry).read()
    datadict = unwrap_data(datastring)

    print "rendererData: " + str(datadict)
    print

    dataout = ''
    queueentry = ''
    for item in datadict:
        colonpos = item.find('::')
        id = item[:colonpos]
        text = item[colonpos+2:]
        if id == 'QUEUE':
            # this is the queue entry name
            dataout += "update_queueentry('" + text + "');"
            queueentry = text

    # get the now playing data for this renderer
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/rendererPoll?data='+pentry).read()
    datadict = unwrap_data(datastring)

    print "rendererPoll: " + str(datadict)
    print

    pollout = formatrendererstatus(datadict)

    # create queue browse script if appropriate
    queuescript = ''
    if queueentry != '':
        qentries = queueentry.split('::')
        qid = qentries[0]
        qtype = qentries[1]
        qmenu = qentries[2]
        qtext = qentries[3]
        qoption = 'tree'
        qstring = ''
        qoperator = ''
        qparams = ['paramtitle='+qtext, 'paramtype='+qtype, 'paramtarget='+qtarget, 'paramid='+qid, 'paramoption='+qoption, 'parammenutype='+qmenu, 'searchstring='+qstring, 'searchoperator='+qoperator, 'browsedata='+qdata, 'chainparams='+qchainparams]        
        queuescript1 = "ajax2('getdata', " + str(qparams) + ", ':eval');"
        # adjust qdata for subsequent calls - pass 0 as sequence
        qdata = '0' + qdata[1:]
        qparams = ['paramtitle='+qtext, 'paramtype='+qtype, 'paramtarget='+qtarget, 'paramid='+qid, 'paramoption='+qoption, 'parammenutype='+qmenu, 'searchstring='+qstring, 'searchoperator='+qoperator, 'browsedata='+qdata, 'chainparams='+qchainparams]        
        queuescript2 = "ajax2('getdata', " + str(qparams) + ", ':eval');"
        queuescript += queuescript1 + "update_queuecall(\"" + queuescript2 + "\");"
    else:
        # need to clear queue from html
        queuescript = "jQuery('#" + qtarget + "').html('');"

#    print "setrenderer return: "
#    print "dataout: " + str(dataout)
#    print "pollout: " + str(pollout)
#    print "queuescript: " + str(queuescript)

    allout = dataout + pollout + queuescript

#    print "allout: " + str(allout)

    return allout
    
def controlrenderer():
    # tell renderer to perform an action
    print "---- controlrenderer -----------------------------------"
    print "paramoption: " + str(request.vars.paramoption)
    poption = request.vars.paramoption
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/rendererAction?data='+poption).read()
    return ""
    
def pollrenderer():
    # get the current play status of the current renderer
    ptitle = escape(request.vars.renderertitle, url_escape_entities)
    ptype = request.vars.renderertype
    ptarget = request.vars.renderertarget
    pentry = ptype + '::' + ptitle
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/rendererPoll?data='+pentry).read()
    datadict = unwrap_data(datastring)
    out = formatrendererstatus(datadict)
    return out

def formatrendererstatus(datadict):
    # format the renderer play status
    out = ''
    for item in datadict:
        entry = item.split('::')
        id = entry[0]
        if len(entry) == 1:
            # some entries can validly have blank text
            if id == 'TRACK' or id == 'ARTIST' or id == 'ALBUM' or id == 'STATION' or id == 'ONNOW' or id == 'INFO':
                text = '-'
            elif id == 'ART':
                # for art use default image
                text = "/sonospy/static/artist.png"
            else:
                # entry has no text, ignore entry
                continue
        else:
            text = entry[1]
        if id == 'TRACK':
            out += "jQuery('#TITLE1').html('Track');"
            out += "jQuery('#LINE1').html('" + text + "');"
        elif id == 'ARTIST':
            out += "jQuery('#TITLE2').html('Artist');"
            out += "jQuery('#LINE2').html('" + text + "');"
        elif id == 'ALBUM':
            out += "jQuery('#TITLE3').html('Album');"
            out += "jQuery('#LINE3').html('" + text + "');"
        elif id == 'STATION':
            out += "jQuery('#TITLE1').html('Station');"
            out += "jQuery('#LINE1').html('" + text + "');"
        elif id == 'ONNOW':
            out += "jQuery('#TITLE2').html('On Now');"
            out += "jQuery('#LINE2').html('" + text + "');"
        elif id == 'INFO':
            out += "jQuery('#TITLE3').html('Info');"
            out += "jQuery('#LINE3').html('" + text + "');"
        elif id == 'ART':
#            out += "jQuery('#ART').html('<img src=\"" + text + "\" class=\"albumart\"></img>');"
            out += "jQuery('#ART').html('<img src=\"/sonospy/static/spinnerlarge.gif\" onLoad=\"replaceImage(this, &quot;" + text + "&quot)\" class=\"albumart\"></img>');"
        elif id == 'POSITION':
            if text != '0:00:00':
                out += "jQuery('#POSITION').html('" + text + "<br/>');"
        elif id == 'PERCENT':
            out += "setprogressbar(" + text + ");"
        elif id == 'VOLUME':
            out += "setvolumeslider(" + text + ");"
        elif id == 'VOLUME_FIXED':
            out += "disablevolumeslider(" + text + ");"
        elif id == 'MUTE':
            out += "setmute(" + text + ");"
        elif id == 'STATE':
            out += "setplay('" + text + "');"
    # recalc the height in case we changed the playing area height
    out += "setheight();"
    return out
    
def pollserver():
    # get the current update status of the current server
    ptitle = escape(request.vars.servertitle, url_escape_entities)
    ptype = request.vars.servertype
    qdata = request.vars.queuedata
    pentry = ptype + '::' + ptitle
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/serverPoll?data='+pentry).read()
    datadict = unwrap_data(datastring)

    print "pollserver return: " + str(datadict)

    out = ''
    for item in datadict:
        entry = item.split('::')
        id = entry[0]
        text = entry[1]
#        if id == 'QUEUE':
#            # the queue has changed, need to update it
#            # qdata contains a pre-formatted ajax call for the queue
#            out += qdata
#    print out

    return out

def pollqueue():
#    print "---- pollqueue -----------------------------------"
#    print "queueentry: " + str(request.vars.queueentry)
#    print "queuecall: " + str(request.vars.queuecall)
    # get the current update status of the current queue
    qentry = escape(request.vars.queueentry, url_escape_entities)
    qcall = request.vars.queuecall

    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/queuePoll?data='+qentry).read()
    datadict = unwrap_data(datastring)
    out = ''
    for item in datadict:
        entry = item.split('::')
        id = entry[0]
        text = entry[1]
        if id == 'QUEUE':
            # the queue has changed, need to update it
            # qcall contains a pre-formatted ajax call for the queue
            out += qcall
    return out

def getrootdata():
    # get the root data for the selected UPnP server
    print "---- getrootdata -----------------------------------"
    print "paramtitle: " + str(request.vars.paramtitle)
    print "paramtype: " + str(request.vars.paramtype)
    print "paramtarget: " + str(request.vars.paramtarget)
    
    ptitle = escape(request.vars.paramtitle, url_escape_entities)
    ptype = request.vars.paramtype
    ptarget = request.vars.paramtarget
    pentry = ptype + '::' + ptitle
    print "entry: " + str(pentry)

    # first get all the context menus for this server
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/rootMenus?data='+pentry).read()
    datadict = unwrap_data(datastring)

    # format the menus - create Javascript functions to load them
    # (we use individual functions as only the first one works if
    # we concatenate them all together (at least in Firefox))
    # Note that the first set is not a menu but the default action(s) for double click
    menucount = int(datadict[0])
    defaultscript = ''
    defaultscriptname = ''
    menuscripts = []
    menuscripttext = ''
    i = 1
    # process default option(s)
    entrycount = int(datadict[i])
    defaultscriptname = datadict[i+1]
    i += 2
    defaultscript += 'function ' + defaultscriptname + '() {'
    for e in range(entrycount):
        menuid = datadict[i]
        menutext = datadict[i+1]
        i += 2
        defaultscript += 'processmenu("' + menuid + '");'
    defaultscript += '};'
    menuscripts.append(defaultscript)
    # process the menus
    for m in range(1,menucount):
        entrycount = int(datadict[i])
        menuname = datadict[i+1]
        i += 2
        menuscripttext += 'function ' + menuname + '(id) {'
        menuscripttext += '  var menu = ['
        for e in range(entrycount):
            menuid = datadict[i]
            menutext = datadict[i+1]
            i += 2
            if menuid == 'SEP' and menutext == 'SEP':
                menuscripttext += '    $.contextMenu.separator,'
            else:
                menuscripttext += '    { "' + menutext + '": function(menuItem,menuObject) { processmenu("' + menuid + '",menuObject.target); } },'
        menuscripttext += '  ];'
        menuscripttext += '  ret=$(id).contextMenu(menu,{beforeShow:function bs(e){return beforeshowmenu(e)},afterShow:function as(m){aftershowmenu(m)}});'
        menuscripttext += '  return ret;'
        menuscripttext += '};'
        menuscripts.append(menuscripttext)
        menuscripttext = ''
    print menuscripts

    # get root entries for this server
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/rootData?data='+pentry).read()
    datadict = unwrap_data(datastring)

    # remove any message
    messagescript = ''
    message = get_message(datadict)
    if message == None or message == '':
        message = 'Ready'
    messagescript = 'setmessagebar("' + message + '");'

    # format the root entries - create an accordion
    out = ''
    itemcount = 0
    for item in datadict:
        entry = item.split('::')
        id = entry[0]
        type = entry[1]
        menu = entry[2]
        text = entry[3]
        if itemcount > 0:
            out += '</span>'
        if itemcount == 0:
            out += '<div id="accordion">'
        itemcount += 1
        
        if text == 'Current Queue':
            # don't display queue
            continue
        
        atarget = '"atarget' + id + '"'
        target = '"target' + id + '"'
        out += '<h3 accord="closed"><a id=' + atarget + ' href="#" menu="' + menu + '" type="' + type + '">' + text + '<span class="ui-icon ui-icon-triangle-1-ne"></span></a></h3>'
        out += '<span id=' + target + '>'
    if itemcount > 0:
        out += '</span></div>'

    # create a script to load the menu scripts we just created
    callscript = ''    
    for menuscript in menuscripts:
        callscript += 'var headID = document.getElementsByTagName("head")[0];'
        callscript += 'var script = document.createElement("script");'
        callscript += 'script.type = "text/javascript";'
        callscript += 'script.text = ' + menuscript + ';'
        callscript += 'headID.appendChild(script);'

    # create a script to store the default option script name
    defaultscript = 'document.forms[0].elements["defaultoptionname"].value="' + defaultscriptname + '";'

    # return the scripts we want to run:
    #     set the target html to be the accordion
    #     call the accordion creation function
    #     execute the script to load the menu creation scripts
    #     execute the script to bind the menus
    return "eval('" + messagescript + "');jQuery('#" + ptarget + "').html('" + out + "');liveaccordion();eval('" + callscript + "');eval('" + defaultscript + "');"


def getdata():
    # get data from the server relating to the parameter values
    print "---- getdata -----------------------------------"
    print "paramtitle: " + str(request.vars.paramtitle)
    print "paramtype: " + str(request.vars.paramtype)
    print "paramtarget: " + str(request.vars.paramtarget)
    print "paramid: " + str(request.vars.paramid)
    print "paramoption: " + str(request.vars.paramoption)
    print "parammenutype: " + str(request.vars.parammenutype)
    print "searchstring: " + str(request.vars.searchstring)
    print "searchoperator: " + str(request.vars.searchoperator)
    print "browsedata: " + str(request.vars.browsedata)
    print "chainparams: " + str(request.vars.chainparams)
    
    ptitle = escape(request.vars.paramtitle, url_escape_entities)
    ptype = request.vars.paramtype
    ptarget = request.vars.paramtarget
    pid = request.vars.paramid
    poption = request.vars.paramoption
    pmenu = request.vars.parammenutype
    psearch = escape(request.vars.searchstring, url_escape_entities)
    poperator = request.vars.searchoperator
    pdata = request.vars.browsedata
    pchain = request.vars.chainparams

    s_vars = True
    if 's_id' in request.vars.keys():
        ps_id = request.vars.s_id
    else:
        s_vars = False
    if 's_type' in request.vars.keys():
        ps_type = request.vars.s_type
    else:
        s_vars = False

    s_name = True
    if 'searchname' in request.vars.keys():
        searchname = request.vars.searchname
    else:
        s_name = False

    datas = pdata.split(',')
    dataseq = int(datas[0])
    datastart = int(datas[1])
    datacount = int(datas[2])

    # format request entry
    pentry = pid + '::' + ptype + '::' + pmenu + '::' + ptitle
    
    # append server id and type if passed
    if s_vars == True:
        pentry += '::' + ps_id + '::' + ps_type

    pentry += '::' + pdata

    # append search vars if present    
    if psearch != "":
        pentry += ':::' + psearch    
    if poperator != "":
        pentry += '::' + poperator
    print "entry: " + str(pentry)

    gotdata = False
    while gotdata == False:
        # get data from the server
        datastring=urllib.urlopen('http://' + ip_address + ':50101/data/getData?data='+pentry).read()
        datadict = unwrap_data(datastring)
        # check whether we have received any data
        if datadict[0].startswith('NOTREADY'):
            time.sleep(0.3)
        else:
            gotdata = True            

    # remove any message
    messagescript = ''
    message = get_message(datadict)
    if message != None:
        messagescript = 'setmessagebar("' + message + '");'

    # remove any return totals (must be present)
    messagescript = ''
    ret = get_return(datadict)
    rets = ret.split(':')
    retcount = int(rets[0])
    rettotal = int(rets[1])
    newtotal = datastart + retcount

    # special case - reset dataseq if it was called with zero
    if dataseq == 0:
        dataseq = 1
    
    # calc number of calls needed
    if dataseq == 1:
        recallcount = (rettotal / datacount) + 1

    # decide whether we want to separate
    chainparams = pchain.split(',')
    chainseparate = chainparams[0]
    if chainseparate == '1': separate = True
    else: separate = False
    currentletter = ''
    if separate == True:
        currentletter = chainparams[1]
        currenttarget = chainparams[2]
    if separate == True and dataseq == 1 and rettotal < 54:
        # not enough entries to separate - reset separate
        chainseparate == '0'
        separate = False

    message = "Returned " + str(newtotal) + " of " + str(rettotal)
    messagescript += 'setmessagebar("' + message + '");'

    # format the data received from the server as an unordered list
    out = ''

    firstsep = False        
    if dataseq == 1:
        firstsep = True
        if separate == False:
            out += '<ul type="none" id="navigation">'
        
    foldercount = 0
    searchitems = []
    multipletargets = ''
    allletters = []
    lettercount = 0

    # TODO: simplify all these booleans
    prevseparate = False
    firstseparate = True
    
    for item in datadict:

        extraentry = None
        rementry = item
        if '::::' in rementry:
            # this entry contains extra details
            entries = rementry.split('::::')
            rementry = entries[0]
            extraentry = entries[1].split('::')
        if ':::' in rementry:
            # this entry contains search criteria
            entries = rementry.split(':::')
            rementry = entries[0]
            searchentry = entries[1].split('::')
            searchtype = searchentry[0]
            if len(searchentry) >= 2:
                searchcriteria = searchentry[1]
            else:
                searchcriteria = None
            if len(searchentry) == 3:
                searchoperators = searchentry[2]
            else:
                searchoperators = None
        # must be a base entry
        entry = rementry.split('::')
        
        id = entry[0]
        sid = ''
        if '|||' in id:
            entries = id.split('|||')
            id = entries[0]
            sid = entries[1]
        type = entry[1]
        menu = entry[2]
        text = entry[3]
        
#        s_id = entry[4]
#        s_type = entry[5]
        
        target = 'target' + str(id)
        atarget = '"atarget' + id + '"'
        ref = '?' + target

        if separate == True:
            newbreak = False
        
            # check whether we need to separate
            thisletter = text[:1].upper()

            if thisletter.isalpha():
                if thisletter != currentletter:
                    currentletter = thisletter
                    newbreak = True
            else:
                if currentletter == '':
                    currentletter = '#'
                    newbreak = True

#            if newbreak == False and firstseparate == True and currenttarget != '':
            if newbreak == False and firstseparate == True:
            
                # this is a continuation of a previous separate - need to indent
                if currenttarget == '':
                    out = '<ul>' + out
                else:
                    out = '<li><span id="' + currenttarget + '"><ul>' + out
                firstseparate = False

            if newbreak == True:

                if firstsep == False:

                    if prevseparate == True:
                        out += '</ul>'
                        out += '</li>'
                        prevseparate = False

                    # it's possible that there isn't a preceding <li> entry in this pass (will be in a previous pass)
                    # - if so we need to add one otherwise the replace will remove the </li> we are about to add
                    # TODO: only check this once
                    if out.find('<li') == -1:
                        out = '<li><ul>' + out
                        prevseparate = True
                    
                    out += '</ul>'
                    out += '</li>'

                else:
                    firstsep = False

                allletters.append(currentletter)
                lettercount += 1
                l_target = 'target' + '__' + str(lettercount)
                l_atarget = '"atarget' + '__' + str(lettercount) + '"'
                l_menu = 'NONE'
                l_type = 'C'
                l_text = currentletter
                l_icon = '<span class="ui-icon ui-icon-minus" style="float:left"></span>'
#                l_play = ' class="dummy"'
                l_play = ''
                out += '<li tree="open" visited="y"' + l_play + '><span type="' + l_type + '"><a id=' + l_atarget + ' menu="' + l_menu + '" type="' + l_type + '">' + l_icon + l_text + '</a></span><span id="s' + l_target + '"></span><span id="' + l_target + '">'
                out += '<ul type="none" id="navigation">'

            else:

                l_target = 'target' + '__' + str(lettercount)
                
        play = ''
        search = ''
        if type == 'T':
            icon = '<span style="float:left"></span><img src="/sonospy/static/note.png">'
            play = ' class="play"'
        if type == 'N':
            icon = '<span style="float:left"></span><img src="/sonospy/static/block.png">'
            play = ' class="dummy"'
        elif type == 'C':
#            icon = '<span class="ui-icon ui-icon-plus" style="float:left"></span><img src="">' #TODO: check whether we need a null image
            icon = '<span class="ui-icon ui-icon-plus" style="float:left"></span><span class="ui-icon ui-icon-triangle-1-ne" style="float:right"></span>'
        elif type == 'A':
            icon = '<span class="ui-icon ui-icon-plus" style="float:left"></span><img src="/sonospy/static/album.png">'
        elif type == 'B':
            icon = '<span class="ui-icon ui-icon-plus" style="float:left"></span><img src="/sonospy/static/artist.png">'
        elif type == 'S':
            icon = '<span style="float:left"></span><img src="/sonospy/static/search.png">'
            search = ' searchtype="' + searchtype + '"'
            if text != 'ALL':
                searchitems.append(id + "::" + text)
            else:
                # have a multiple search option - pass the other options through
                c = 1
                st = ''
                for si in searchitems:
                    itemname = si.split("::")[1]
                    multipletargets += '<span id="' + target + '__' + str(c) + '" sname="' + itemname + '"></span>'
                    st += si + '__'
                    c += 1
                search += ' searchtype2="' + st[:-2] + '"'
            if searchcriteria != None:
                search += ' searchcriteria="' + searchcriteria + '"'
            if searchoperators != None:
                search += ' searchoperators="' + searchoperators + '"'
        
        extras = ''
        extracreator = ''
        extraalbum = ''
        extraart = ''
        if extraentry != None:
            for ex in extraentry:
                if ex.startswith('creator='):
                    extracreator = ex[8:]
                    extras += '<span class="extra"> [' + extracreator + ']</span>'
                elif ex.startswith('album='):
                    extraalbum = ex[6:]
                    extras += '<span class="extra"> [' + extraalbum + ']</span>'
                elif ex.startswith('art='):
                    extraart = ex[4:]
            if type == 'C':     # this works at the moment because the only container with extras is album
                insertalbum(id, text, extracreator, extraart, item)
                
        out += '<li tree="closed"' + play + search + '><span type="' + type + '"><a id=' + atarget + ' menu="' + menu + '" type="' + type + '" sid="' + sid + '">' + icon + text + extras + '</a></span><span id="s' + target + '"></span><span id="' + target + '"></span>' + multipletargets + '</li>'

        foldercount += 1

    # check if we received all entries
    chainscript = ''
    iconscript = ''
    if newtotal < rettotal:

        # there are more entries so we want to chain another ajax call
        # update the data values
        if (rettotal - newtotal) < datacount: datacount = rettotal - newtotal
        nextdata = str(dataseq+1) + ',' + str(newtotal) + ',' + str(datacount)
        # update the target
        target_base = ptarget.split('-')[0]
        nexttarget = target_base + '-' + str(dataseq+1)

        # check if we need to close a separate
        if separate == True:
            out += '</ul>'
            out += '</span></li>'

        # create targets for remaining calls
        if dataseq == 1:
            for call in range(recallcount):
                calltarget = target_base + '-' + str(dataseq+call+1)
                out += '<span id="' + calltarget + '"></span>'

        # set chain params
        chainparams = chainseparate + ','
        if chainseparate == '1':
            chainparams += currentletter
            # add letter continuation target
            du = l_target.split('__')
            if len(du) == 1: cont = '1'
            else: cont = str(int(du[1])+1)
            chainparams += ',' + du[0] + '__' + cont
            
        # call again - use call that doesn't use form fields in case user is making another call
        params = ['paramtitle='+ptitle, 'paramtype='+ptype, 'paramtarget='+nexttarget, 'paramid='+pid, 'paramoption='+poption, 'parammenutype='+pmenu, 'searchstring='+psearch, 'searchoperator='+poperator, 'browsedata='+nextdata, 'chainparams='+chainparams]        
        chainscript += "ajax2('getdata', " + str(params) + ", ':eval');"

    else:
        # there are no more browse entries
        # finalise separator

        if separate == True:
            out += '</ul>'
            out += '</li>'
        # finalise list
        out += '</ul>'
        # create a script to post process the server data icon after updating
        if poption == 'tree':
            iconscript = "jQuery('.clicker').attr('class', 'ui-icon ui-icon-minus').removeClass('clicker');"
        elif poption == 'accord':
            iconscript = "jQuery('.clicker').removeClass('ui-icon-refresh').addClass('ui-icon-triangle-1-s').removeClass('clicker');"

    # return the scripts we want to run:
    #     set the target html to be the list
    #     call the post processing script
    
#    print "ptarget: " + str(ptarget)
#    print "out: " + str(out)

    height = "setheight();"
    
    if dataseq <= 1 or separate == False:
        # prepend name separator if specified
        if s_name:
            out = searchname + out
        
        return "eval('" + messagescript + "');jQuery('#" + ptarget + "').html('" + out + "');" + chainscript + iconscript + height
    else:    
        return "eval('" + messagescript + "');jQuery('#" + ptarget + "').replaceWith('" + out + "');" + chainscript + iconscript + height

def calloption():
    # tell the controlpoint to perform the passed function on the passed item
    print "---- calloption -----------------------------------"
    print "paramtitle: " + str(request.vars.paramtitle)
    print "paramtype: " + str(request.vars.paramtype)
    print "paramtarget: " + str(request.vars.paramtarget)
    print "paramid: " + str(request.vars.paramid)
    print "paramsid: " + str(request.vars.paramsid)
    print "parammenuoption: " + str(request.vars.parammenuoption)
    print "parammenutype: " + str(request.vars.parammenutype)
 
    ptitle = escape(request.vars.paramtitle, url_escape_entities)
    ptype = request.vars.paramtype
    ptarget = request.vars.paramtarget
    pid = request.vars.paramid
    psid = request.vars.paramsid
    poption = request.vars.parammenuoption
    pmenu = request.vars.parammenutype
    
    if psid != '':
        pid += '|||' + psid
    
    if ptype == "":
        pentry = pid + '::' + pmenu + '::' + ptitle + ":::" + poption
    else:
        pentry = pid + '::' + ptype + '::' + pmenu + '::' + ptitle + ":::" + poption
    print "entry: " + str(pentry)
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/playData?data='+pentry).read()

    return ""

def calloptionmulti():
    # tell the controlpoint to perform the passed function on the passed item list
    print "---- calloptionmulti -----------------------------------"
    print "data: " + str(request.vars.data)
    print "option: " + str(request.vars.option)
 
    pdata = escape(request.vars.data, url_escape_entities)
    poption = request.vars.option
    
    pentry = 'MULTI' + ':::' + poption + ':::' + pdata
    print "entry: " + str(pentry)
    datastring=urllib.urlopen('http://' + ip_address + ':50101/data/playData?data='+pentry).read()

    return ""


def user():
    """
    exposes:
    http://..../[app]/default/user/login 
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    """
    return dict(form=auth())


def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request,db)


def call():
    """
    exposes services. for example:
    http://..../[app]/default/call/jsonrpc
    decorate with @services.jsonrpc the functions to expose
    supports xml, json, xmlrpc, jsonrpc, amfrpc, rss, csv
    """
    session.forget()
    return service()
