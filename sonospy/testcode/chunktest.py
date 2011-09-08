
def chunker(startingIndex, totalMatches, requestedCount, chunks, show_separator):

    totalgroups = chunks
    groupsize = totalMatches                        # this is the number of records found for the count query
    if show_separator:
        groupsize += 1                              # add an extra record if we want to display a separator
    newtotal = groupsize * totalgroups              # this is the total records we will return to Sonos, including separators if appropriate

    start = startingIndex
    end = start + requestedCount - 1                # this is inclusive, zero based - so 0 means get the first entry

    grouplimits = []
    startgroup = 0
    endgroup = None
    for i in range(totalgroups):
        groupstart = (i * groupsize)
        groupend = groupstart + groupsize - 1
        grouplimits.append(groupstart)
        grouplimits.append(groupend)
        if start >= groupstart:
            startgroup = i
        if end <= groupend and endgroup == None:
            endgroup = i
    if endgroup == None:
        endgroup = totalgroups - 1

    groupdata = []

    displayseparator = False
    groupset = startgroup * 2
    thisgroupstart = grouplimits[groupset]
    thisgroupend = grouplimits[groupset+1]
    if start == thisgroupstart:
        thisgroupstartoffset = 0
        if show_separator:
            displayseparator = True
    else:
        thisgroupstartoffset = start - thisgroupstart
        if show_separator:
            thisgroupstartoffset -= 1
    if endgroup != startgroup:
        thisgroupendoffset = thisgroupend - thisgroupstart
    else:
        if end > thisgroupend:
            end = thisgroupend
        thisgroupendoffset = end - thisgroupstart
    if not show_separator:
        thisgroupendoffset += 1
    groupdata.append((startgroup, thisgroupstartoffset, thisgroupendoffset, displayseparator))

    for j in range(startgroup+1,endgroup-1+1):
        groupset = j * 2
        thisgroupstart = grouplimits[groupset]
        thisgroupend = grouplimits[groupset+1]
        thisgroupstartoffset = 0
        if show_separator:
            displayseparator = True
        thisgroupendoffset = thisgroupend - thisgroupstart
        if not show_separator:
            thisgroupendoffset += 1
        groupdata.append((j, thisgroupstartoffset, thisgroupendoffset, displayseparator))

    if endgroup != startgroup:
        groupset = endgroup * 2
        thisgroupstart = grouplimits[groupset]
        thisgroupend = grouplimits[groupset+1]
        thisgroupstartoffset = 0
        if show_separator:
            displayseparator = True
        if end > thisgroupend:
            end = thisgroupend
        thisgroupendoffset = end - thisgroupstart
        if not show_separator:
            thisgroupendoffset += 1
        groupdata.append((endgroup, thisgroupstartoffset, thisgroupendoffset, displayseparator))

#    print grouplimits
#    print "%d %d" % (startgroup, endgroup)
#    for k in groupdata:
#        print k
        
    return groupdata, newtotal

def printchunker(chunker):
    groupdata, newtotal = chunker
    for i in range(len(groupdata)):
        group, start, end, sep = groupdata[i]
        print "    %4d %4d %4d %s" % (group, start, end, sep)

def processtest(data, req, sep):
    returned, chunks = data
    if sep:
        total = (returned +1) * chunks
    else:
        total = returned * chunks
    requested = req
    print
    print "%4d %4d %4d" % (returned, chunks, total)
    count = int(total / requested)
    if (total % requested) != 0:
        count += 1
    for i in range(count):
        print "  %4d %4d" % (i*requested, i*requested + requested)
        printchunker(chunker(i*requested, returned, requested, chunks, sep))

#test = (41, 6)
#processtest(test, 100, True)

#test = (41, 6)
#processtest(test, 100, False)

test = (77, 1)
processtest(test, 100, False)

test = (77, 1)
processtest(test, 100, False)

test = (77, 3)
processtest(test, 100, True)

test = (77, 3)
processtest(test, 100, False)

test = (77, 3)
processtest(test, 99, True)

test = (77, 3)
processtest(test, 99, False)

test = (77, 3)
processtest(test, 101, True)

test = (77, 3)
processtest(test, 101, False)

print
print "3 chunks sep"
print "============"
for i in range(200):
    processtest((i+1,3), 100, True)

print
print "2 chunks sep"
print "============"
for i in range(200):
    processtest((i+1,2), 100, True)

print
print "1 chunk sep"
print "==========="
for i in range(200):
    processtest((i+1,1), 100, True)

print
print "3 chunks no sep"
print "==============="
for i in range(200):
    processtest((i+1,3), 100, False)

print
print "2 chunks no sep"
print "==============="
for i in range(200):
    processtest((i+1,2), 100, False)

print
print "1 chunk no sep"
print "=============="
for i in range(200):
    processtest((i+1,1), 100, False)

