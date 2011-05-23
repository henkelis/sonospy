# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>
# Thanks to ushare project for informations in your dlna.h file

""" Digital Living Network Alliance constants and flags.
"""

# Play speed
#    1 normal
#    0 invalid
DLNA_ORG_PS = 'DLNA.ORG_PS'
DLNA_ORG_PS_VAL = '01'

# Convertion Indicator
#    1 transcoded
#    0 not transcoded
DLNA_ORG_CI = 'DLNA.ORG_CI'
DLNA_ORG_CI_VAL = '0'

# Operations
#    00 not time seek range, not range
#    01 range supported
#    10 time seek range supported
#    11 both supported
DLNA_ORG_OP = 'DLNA.ORG_OP'
DLNA_ORG_OP_VAL = '01'

# Flags
#    senderPaced                      80000000  31
#    lsopTimeBasedSeekSupported       40000000  30
#    lsopByteBasedSeekSupported       20000000  29
#    playcontainerSupported           10000000  28
#    s0IncreasingSupported            8000000   27
#    sNIncreasingSupported            4000000   26
#    rtspPauseSupported               2000000   25
#    streamingTransferModeSupported   1000000   24
#    interactiveTransferModeSupported 800000    23
#    backgroundTransferModeSupported  400000    22
#    connectionStallingSupported      200000    21
#    dlnaVersion15Supported           100000    20
DLNA_ORG_FLAGS = 'DLNA.ORG_FLAGS'
DLNA_ORG_FLAGS_VAL = '01500000000000000000000000000000'

# Media Format
DLNA_ORG_PN = 'DLNA.ORG_PN'

protocol_info_dict = {'audio/mpeg': 'MP3', 'audio/mp4': 'AAC_ISO_320',
                      'audio/x-ms-wma': 'WMABASE', 'image/jpeg': 'JPEG_SM',
                      'video/mpeg': 'MPEG_PS_PAL',
                      'video/mp4': 'MPEG4_P2_MP4_SP_AAC',
                      'video/x-ms-wmv': 'WMVMED_BASE'}


def get_protocol_info(type):
    ''' Return DLNA protocolInfo '''

    if type == 'video/x-msvideo':
        type = 'video/avi'

    mtype = protocol_info_dict.get(type)

    if not mtype:
        mtype = ''

    info = '%s=%s;%s=%s;%s=%s;%s=%s;%s=%s'%(DLNA_ORG_PS, DLNA_ORG_PS_VAL,
                                            DLNA_ORG_CI, DLNA_ORG_CI_VAL,
                                            DLNA_ORG_OP, DLNA_ORG_OP_VAL,
                                            DLNA_ORG_PN, mtype,
                                            DLNA_ORG_FLAGS, DLNA_ORG_FLAGS_VAL)

    protocol_info = 'http-get:*:%s:%s' % (type, info)

    return protocol_info
