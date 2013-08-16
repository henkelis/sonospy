from customsd import post_customsd

zpip = '192.168.1.72'

for sid in range(240, 254):
    print sid
    post_customsd(zpip, sid, None, None, None)


