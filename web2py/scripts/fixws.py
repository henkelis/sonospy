import sys, glob
for filename in glob.glob(sys.argv[1]):
    data1=open(filename,'rb').read()
    open(filename+'.bak2','wb').write(data1)
    data2 = '\n'.join([line.rstrip() for line in open(filename,'rb')])+'\n'
    open(filename,'wb').write(data2)
    print filename, len(data1)-len(data2)
