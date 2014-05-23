from customsd import post_customsd
import argparse

parser = argparse.ArgumentParser(description='Remove all SMAPI services')
parser.add_argument('zpip', help='zoneplayer IP')

args = parser.parse_args()

for sid in range(240, 254) + [255]:
    print sid
    post_customsd(args.zpip, sid, None, None, None, None)


