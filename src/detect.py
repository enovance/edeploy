#!/usr/bin/env python
#
# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
#
# Author: Frederic Lepied <frederic.lepied@enovance.com>
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

'''Main entry point for hardware and system detection routines in eDeploy.'''

from commands import getstatusoutput as cmd
import pprint
import sys
import xml.etree.ElementTree as ET
import subprocess
import socket
import fcntl
import struct
from netaddr import *

import diskinfo
import hpacucli
import infiniband as ib
import os


def size_in_gb(size):
    'Return the size in GB without the unit.'
    ret = size.replace(' ', '')
    if ret[-2:] == 'GB':
        return ret[:-2]
    elif ret[-2:] == 'TB':
        return ret[:-2] + '000'
    else:
        return ret


def detect_hpa(hw_lst):
    'Detect HP RAID controller configuration.'
    try:
        cli = hpacucli.Cli(debug=False)
        if not cli.launch():
            return False
        controllers = cli.ctrl_all_show()
        if len(controllers) == 0:
            sys.stderr.write("Info: No hpa controller found\n")
            return False

        for controller in controllers:
            slot = 'slot=%d' % controller[0]
            for _, disks in cli.ctrl_pd_all_show(slot):
                for disk in disks:
                    hw_lst.append(('disk', disk[0], 'type', disk[1]))
                    hw_lst.append(('disk', disk[0], 'slot',
                                   str(controller[0])))
                    hw_lst.append(('disk', disk[0], 'size',
                                   size_in_gb(disk[2])))
        return True
    except hpacucli.Error as expt:
        sys.stderr.write('Info: detect_hpa : %s\n' % expt.value)
        return False


def detect_disks(hw_lst):
    'Detect disks.'
    names = diskinfo.disknames()
    sizes = diskinfo.disksizes(names)
    for name in [name for name, size in sizes.items() if size > 0]:
        hw_lst.append(('disk', name, 'size', str(sizes[name])))
        item_list = ['vendor', 'model', 'rev']
        for my_item in item_list:
            try:
                with open('/sys/block/%s/device/%s' % (name,
                                                       my_item),
                          'r') as dev:
                    hw_lst.append(('disk', name, my_item,
                                   dev.readline().rstrip('\n').strip()))
            except Exception, excpt:
                sys.stderr.write(
                    'Failed at getting disk information '
                    'at /sys/block/%s/device/%s: %s\n' % (name,
                                                          my_item,
                                                          str(excpt)))

        item_list = ['WCE', 'RCD']
        item_def = {'WCE': 'Write Cache Enable', 'RCD': 'Read Cache Disable'}
        for my_item in item_list:
            sdparm_cmd = subprocess.Popen("sdparm -q --get=%s /dev/%s | "
                                          "awk '{print $2}'" % (my_item, name),
                                          shell=True,
                                          stdout=subprocess.PIPE)
            for line in sdparm_cmd.stdout:
                hw_lst.append(('disk', name, item_def.get(my_item),
                               line.rstrip('\n').strip()))


def modprobe(module):
    'Load a kernel module using modprobe.'
    status, _ = cmd('modprobe %s' % module)
    if status == 0:
        sys.stderr.write('Info: Probing %s failed\n' % module)


def detect_ipmi(hw_lst):
    'Detect IPMI interfaces.'
    modprobe("ipmi_smb")
    modprobe("ipmi_si")
    modprobe("ipmi_devintf")
    if os.path.exists('/dev/ipmi0') or os.path.exists('/dev/ipmi/0') \
            or os.path.exists('/dev/ipmidev/0'):
        for channel in range(0, 16):
            status, _ = cmd('ipmitool channel info %d 2>&1 | grep -sq Volatile'
                            % channel)
            if status == 0:
                hw_lst.append(('system', 'ipmi', 'channel', '%s' % channel))
                break
    else:
        # do we need a fake ipmi device for testing purpose ?
        status, _ = cmd('grep -qi FAKEIPMI /proc/cmdline')
        if status == 0:
            # Yes ! So let's create a fake entry
            hw_lst.append(('system', 'ipmi-fake', 'channel', '0'))
            sys.stderr.write('Info: Added fake IPMI device\n')
            return True
        else:
            sys.stderr.write('Info: No IPMI device found\n')
            return False


def get_CIDR(netmask):
    binary_str = ''
    for octet in netmask:
        binary_str += bin(int(octet))[2:].zfill(8)
    return str(len(binary_str.rstrip('0')))


def detect_infiniband(hw_lst):
  'Detect Infiniband devinces.'
  status, _ = cmd('lspci -d 15b3: |grep -sq Mellanox')
  if status == 0:
    ib_card = 0
    for devices in range(ib_card, len(ib.ib_card_drv())):
      card_type = ib.ib_card_drv()[devices]
      ib_infos = ib.ib_global_info(card_type)
      nb_ports = ib_infos['nb_ports']
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'card_type', card_type))
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'device_type', ib_infos['device_type']))
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'fw_version', ib_infos['fw_ver']))
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'hw_version', ib_infos['hw_ver']))
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'nb_ports', nb_ports))
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'sys_guid', ib_infos['sys_guid']))
      hw_lst.append(('infiniband', 'card%i' % ib_card, 'node_guid', ib_infos['node_guid']))
      for port in range(1, int(nb_ports)+1):
        ib_port_infos = ib.ib_port_info(card_type,port)
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'state', ib_port_infos['state']))
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'physical_state', ib_port_infos['physical_state']))
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'rate', ib_port_infos['rate']))
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'base_lid', ib_port_infos['base_lid']))
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'lmc', ib_port_infos['lmc']))
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'sm_lid', ib_port_infos['sm_lid']))
        hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card,port), 'port_guid', ib_port_infos['port_guid']))
    return True
  else:
    sys.stderr.write('Info: No Infiniband device found\n')
    return False


def detect_system(hw_lst, output=None):
    'Detect system characteristics from the output of lshw.'

    socket_count = 0

    def find_element(xml, xml_spec, sys_subtype,
                     sys_type='product', sys_cls='system', attrib=None):
        'Lookup an xml element and populate hw_lst when found.'
        elt = xml.findall(xml_spec)
        if len(elt) >= 1:
            if attrib:
                hw_lst.append((sys_cls, sys_type, sys_subtype,
                               elt[0].attrib[attrib]))
                return elt[0].attrib[attrib]
            else:
                hw_lst.append((sys_cls, sys_type, sys_subtype, elt[0].text))
                return elt[0].text
        return None

    # handle output injection for testing purpose
    if output:
        status = 0
    else:
        status, output = cmd('lshw -xml')
    if status == 0:
        xml = ET.fromstring(output)
        find_element(xml, "./node/serial", 'serial')
        find_element(xml, "./node/product", 'name')
        find_element(xml, "./node/vendor", 'vendor')
        find_element(xml, "./node/version", 'version')

        for elt in xml.findall(".//node[@id='firmware']"):
            name = elt.find('physid')
            if name is not None:
                find_element(elt, 'version', 'version', 'bios', 'firmware')
                find_element(elt, 'date', 'date', 'bios', 'firmware')
                find_element(elt, 'vendor', 'vendor', 'bios', 'firmware')

        for elt in xml.findall(".//node[@id='memory']"):
            name = elt.find('physid')
            if name is not None:
                find_element(elt, 'size', 'size', 'total', 'memory')
                bank_count = 0
                for bank_list in elt.findall(".//node[@id]"):
                    if ('bank:') in bank_list.get('id'):
                        bank_count = bank_count+1
                        for bank in elt.findall(".//node[@id='%s']" %
                                                (bank_list.get('id'))):
                            find_element(bank, 'size', 'size',
                                         bank_list.get('id'), 'memory')
                            find_element(bank, 'clock', 'clock',
                                         bank_list.get('id'), 'memory')
                            find_element(bank, 'description', 'description',
                                         bank_list.get('id'), 'memory')
                            find_element(bank, 'vendor', 'vendor',
                                         bank_list.get('id'), 'memory')
                            find_element(bank, 'serial', 'serial',
                                         bank_list.get('id'), 'memory')
                            find_element(bank, 'slot', 'slot',
                                         bank_list.get('id'), 'memory')
                if bank_count > 0:
                    hw_lst.append(('memory', 'banks', 'count', bank_count))

        for elt in xml.findall(".//node[@class='network']"):
            name = elt.find('logicalname')
            if name is not None:
                find_element(elt, 'serial', 'serial', name.text, 'network')
                find_element(elt, 'vendor', 'vendor', name.text, 'network')
                find_element(elt, 'product', 'product', name.text, 'network')
                find_element(elt, 'size', 'size', name.text, 'network')
                ipv4 = find_element(elt, "configuration/setting[@id='ip']", 'ipv4',
                             name.text, 'network', 'value')
                if ipv4 is not None:
                    SIOCGIFNETMASK = 0x891b
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        netmask = socket.inet_ntoa(fcntl.ioctl(s, SIOCGIFNETMASK, struct.pack('256s', name.text))[20:24])
                        hw_lst.append(('network', name.text, 'ipv4-netmask', netmask))
                        cidr = get_CIDR(netmask.split('.'))
                        hw_lst.append(('network', name.text, 'ipv4-cidr', cidr))
                        hw_lst.append(('network', name.text, 'ipv4-network', "%s" % IPNetwork('%s/%s' % (ipv4, cidr)).network))
                    except:
                        True

                find_element(elt, "configuration/setting[@id='link']", 'link',
                             name.text, 'network', 'value')
                find_element(elt, "configuration/setting[@id='driver']",
                             'driver', name.text, 'network', 'value')
                find_element(elt, "configuration/setting[@id='duplex']",
                             'duplex', name.text, 'network', 'value')
                find_element(elt, "configuration/setting[@id='speed']",
                             'speed', name.text, 'network', 'value')
                find_element(elt, "configuration/setting[@id='latency']",
                             'latency', name.text, 'network', 'value')
                find_element(elt, "configuration/setting[@id='autonegotiation']",
                             'autonegotiation', name.text, 'network', 'value')

        for elt in xml.findall(".//node[@class='processor']"):
            name = elt.find('physid')
            if name is not None:
                hw_lst.append(('cpu', 'physical_%s' % (socket_count),
                               'physid', name.text))
                find_element(elt, 'product', 'product',
                             'physical_%s' % socket_count, 'cpu')
                find_element(elt, 'vendor', 'vendor',
                             'physical_%s' % socket_count, 'cpu')
                find_element(elt, 'size', 'frequency',
                             'physical_%s' % socket_count, 'cpu')
                find_element(elt, 'clock', 'clock',
                             'physical_%s' % socket_count, 'cpu')
                find_element(elt, "configuration/setting[@id='cores']",
                             'cores', 'physical_%s' % socket_count,
                             'cpu', 'value')
                find_element(elt, "configuration/setting[@id='enabledcores']",
                             'enabled_cores', 'physical_%s' % socket_count,
                             'cpu', 'value')
                find_element(elt, "configuration/setting[@id='threads']",
                             'threads', 'physical_%s' % socket_count, 'cpu',
                             'value')
                socket_count = socket_count+1
    else:
        sys.stderr.write("Unable to run lshw: %s\n" % output)

    hw_lst.append(('cpu', 'physical', 'number', str(socket_count)))
    status, output = cmd('nproc')
    if status == 0:
        hw_lst.append(('cpu', 'logical', 'number', str(output)))


def _main():
    'Command line entry point.'
    hrdw = []

    detect_hpa(hrdw)
    detect_disks(hrdw)
    detect_system(hrdw)
    detect_ipmi(hrdw)
    detect_infiniband(hrdw)
    pprint.pprint(hrdw)

if __name__ == "__main__":
    _main()
