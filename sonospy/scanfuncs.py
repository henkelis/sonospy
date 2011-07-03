import re

def truncate_number(number):
    # find integer portion of number passed as string
    if not number:
        number = 0
    else:
        number = number.strip()
        numberparts = re.split('\D', number)
        if numberparts[0] == '':
            number = 0
        else:
            try:
                number = int(numberparts[0])
            except ValueError:
                number = 0
            except AttributeError:
                number = 0
    return number
    
def adjust_tracknumber(tracknumber):
    # adjust tracknumber so that it's numeric (but save empty string if not)
    if not tracknumber:
        tracknumber = ''
    else:
        tracknumber = tracknumber.strip()
        if tracknumber != '':
            try:
                tracknumber = int(re.split('\D', tracknumber)[0])
            except ValueError:
                tracknumber = ''
            except AttributeError:
                tracknumber = ''
    return tracknumber

