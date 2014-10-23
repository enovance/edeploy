#!/usr/bin/env python
#
# Copyright (C) 2013-2014 eNovance SAS <licensing@enovance.com>
#
# Author: Erwan Velu <erwan.velu@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

'''CGI script part of the eDeploy system.

It receives on its file form a file containing a Python dictionnary
with the hardware detected on the remote host. In return, it sends
a Python configuration script corresponding to the matched config.

If nothing matches, nothing is returned. So the system can abort
its configuration.

On the to be configured host, it is usually called like that:

$ curl -i -F name=test -F file=@/tmp/hw.lst http://localhost/cgi-bin/upload.py
'''

import ConfigParser
import cgi
import cgitb
import json
import os
import pprint
import re
import sys
import time

import matcher


def log(msg):
    'Error Logging.'
    sys.stderr.write('eDeploy: ' + msg + '\n')


def save_hw(items, name, hwdir):
    'Save hw items for inspection on the server.'
    try:
        filename = os.path.join(hwdir, name + '.hw')
        pprint.pprint(items, stream=open(filename, 'w'))
    except Exception, xcpt:
        log("exception while saving hw file: %s" % str(xcpt))


def generate_filename_and_macs(items):
    '''Generate a file name for a hardware using DMI information
    (product name and version) then if the DMI serial number is
    available we use it unless we lookup the first mac address.
    As a result, we do have a filename like :

    <dmi_product_name>-<dmi_product_version>-{dmi_serial_num|mac_address}'''

    # Duplicate items as it will be modified by match_* functions
    hw_items = list(items)
    sysvars = {}
    sysvars['sysname'] = ''

    matcher.match_spec(('system', 'product', 'name', '$sysprodname'),
                       hw_items, sysvars)
    if 'sysprodname' in sysvars:
        sysvars['sysname'] = re.sub(r'\W+', '', sysvars['sysprodname']) + '-'

    matcher.match_spec(('system', 'product', 'vendor', '$sysprodvendor'),
                       hw_items, sysvars)
    if 'sysprodvendor' in sysvars:
        sysvars['sysname'] += re.sub(r'\W+', '', sysvars['sysprodvendor']) + \
            '-'

    matcher.match_spec(('system', 'product', 'serial', '$sysserial'),
                       hw_items, sysvars)
    # Let's use any existing DMI serial number or take the first mac address
    if 'sysserial' in sysvars:
        sysvars['sysname'] += re.sub(r'\W+', '', sysvars['sysserial']) + '-'

    # we always need to have the mac addresses for pxemngr
    if matcher.match_multiple(hw_items,
                              ('network', '$eth', 'serial', '$serial'),
                              sysvars):
        if 'sysserial' not in sysvars:
            sysvars['sysname'] += sysvars['serial'][0].replace(':', '-')
    else:
        log('unable to detect network macs')

    return sysvars


def fatal_error(error):
    '''Report a shell script with the error message and log
    the message on stderr.'''
    print('''#!/bin/sh

cat <<EOF
%s
EOF

exit 1
''' % error)
    sys.stderr.write('%s\n' % error)
    sys.exit(1)


def main():
    '''CGI entry point.'''

    config = ConfigParser.ConfigParser()
    config.read('/etc/edeploy.conf')

    def config_get(section, name, default):
        'Secured config getter.'
        try:
            return config.get(section, name)
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
            return default

    cfg_dir = os.path.normpath(config_get('SERVER', 'HEALTHDIR', os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'health'))) + '/'

    # parse hw file given in argument or passed to cgi script
    if len(sys.argv) == 3 and sys.argv[1] == '-f':
        hw_file = open(sys.argv[2])
    else:
        cgitb.enable()

        form = cgi.FieldStorage()

        if 'file' not in form:
            fatal_error('No file passed to the CGI')

        fileitem = form['file']
        hw_file = fileitem.file

    try:
        hw_items = json.loads(hw_file.read(-1))
    except Exception, excpt:
        fatal_error("'Invalid hardware file: %s'" % str(excpt))

    filename_and_macs = generate_filename_and_macs(hw_items)
    dirname = time.strftime("%Y_%m_%d-%Hh%M", time.localtime())

    if form.getvalue('session'):
        dest_dir = cfg_dir + os.path.basename(form.getvalue('session')) + \
                '/' + dirname
    else:
        dest_dir = cfg_dir + '/' + dirname

    try:
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)
    except OSError, e:
        fatal_error("Cannot create %s directory (%s)" % (dest_dir, e.errno))

    save_hw(hw_items, filename_and_macs['sysname'], dest_dir)


if __name__ == "__main__":
    main()
