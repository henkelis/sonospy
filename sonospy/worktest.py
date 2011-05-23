import re

def splitwork(workstring):
    workstring = workstring.strip()
    worknumber = None
    if workstring != '':
        try:
            worknumberstring = re.split('\D', workstring)[0]
            if worknumberstring != '' and workstring[len(worknumberstring):len(worknumberstring)+1] == ',':
                workstring = workstring[len(worknumberstring)+1:]
                worknumber = int(worknumberstring)
        except ValueError:
            pass
        except AttributeError:
            pass
    return worknumber, workstring
    
print splitwork('32,apple pie')
print splitwork('99 Red Balloons')
print splitwork('This is it')
