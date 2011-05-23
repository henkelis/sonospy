import ConfigParser

# get ini settings
config = ConfigParser.ConfigParser()
config.optionxform = str
config.read('scan.ini')

# names

# work_name_structure="%s - %s - %s" % (_shortgenre, work, artist)
# _shortgenre_field_transform=genre.split(' / ')[-1]
# virtual_name_structure="%s" % (virtual)

work_name_structure = '"%s - %s - %s" % (genre, work, artist)'
try:        
    work_name_structure = config.get('movetags', 'work_name_structure')
except ConfigParser.NoSectionError:
    pass
except ConfigParser.NoOptionError:
    pass

virtual_name_structure = '"%s" % (virtual)'
try:        
    virtual_name_structure = config.get('movetags', 'virtual_name_structure')
except ConfigParser.NoSectionError:
    pass
except ConfigParser.NoOptionError:
    pass

work_field_sep_pos = work_name_structure.rfind('(')
work_string = work_name_structure[:work_field_sep_pos]
work_fields = work_name_structure[work_field_sep_pos+1:]
work_fields = work_fields[:work_fields.rfind(')')]
work_fields = work_fields.split(',')
x_fields = []
for field in work_fields:
    field = field.strip()
    if field[0] == '_':
        field_transform = None
        field_transform_name = field + '_field_transform'
        try:        
            field_transform = config.get('movetags', field_transform_name)
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if field_transform:        
            x_fields.append(field_transform)
    else:            
        x_fields.append(field)
work_fields = ','.join(x_fields)
work_name_structure = '%s (%s)' % (work_string, work_fields)

print work_name_structure
