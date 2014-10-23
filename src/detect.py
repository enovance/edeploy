#!/usr/bin/env python
#
# Copyright (C) 2013-2014 eNovance SAS <licensing@enovance.com>
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
import diskinfo
import fcntl
import hpacucli
import infiniband as ib
import json
import megacli
from netaddr import IPNetwork
import os
import socket
import struct
import string
from subprocess import Popen, PIPE
import sys
import xml.etree.ElementTree as ET
import re
import detect_utils

SIOCGIFNETMASK = 0x891b


def output_lines(cmdline):
    "Run a shell command and returns the output as lines."
    res = Popen(cmdline, shell=True, stdout=PIPE)
    return res.stdout


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
    disk_count = 0
    try:
        cli = hpacucli.Cli(debug=False)
        if not cli.launch():
            return False
        controllers = cli.ctrl_all_show()
        if len(controllers) == 0:
            sys.stderr.write("Info: No hpa controller found\n")
            return False

    except hpacucli.Error as expt:
        sys.stderr.write('Info: detect_hpa : %s\n' % expt.value)
        return False

    hw_lst.append(('hpa', "slots", "count", len(controllers)))
    for controller in controllers:
        try:
            slot = 'slot=%d' % controller[0]
            controllers_infos = cli.ctrl_show(slot)
            for controller_info in controllers_infos.keys():
                hw_lst.append(('hpa', slot.replace('=', '_'),
                               controller_info,
                               controllers_infos[controller_info]))
            for _, disks in cli.ctrl_pd_all_show(slot):
                for disk in disks:
                    disk_count += 1
                    hw_lst.append(('disk', disk[0], 'type', disk[1]))
                    hw_lst.append(('disk', disk[0], 'slot',
                                   str(controller[0])))
                    disk_infos = cli.ctrl_pd_disk_show(slot, disk[0])
                    for disk_info in disk_infos.keys():
                        value = disk_infos[disk_info]
                        if disk_info == "size":
                            value = size_in_gb(disk_infos[disk_info])
                        hw_lst.append(('disk', disk[0], disk_info,
                                       value))
        except hpacucli.Error as expt:
            sys.stderr.write('Info: detect_hpa : controller %d : %s\n'
                             % (controller[0], expt.value))

    hw_lst.append(('disk', 'hpa', 'count', str(disk_count)))
    return True


def detect_megacli(hw_lst):
    'Detect LSI MegaRAID controller configuration.'
    ctrl_num = megacli.adp_count()
    disk_count = 0
    if ctrl_num > 0:
        for ctrl in range(ctrl_num):
            for enc in megacli.enc_info(ctrl):
                for slot_num in range(enc['NumberOfSlots']):
                    disk_count += 1
                    disk = 'disk%d' % slot_num
                    info = megacli.pdinfo(ctrl,
                                          enc['DeviceId'],
                                          slot_num)

                    # If no PdType, it means that's not a disk
                    if 'PdType' not in info.keys():
                        continue

                    hw_lst.append(('pdisk',
                                   disk,
                                   'ctrl',
                                   str(ctrl_num)))
                    hw_lst.append(('pdisk',
                                   disk,
                                   'type',
                                   info['PdType']))
                    hw_lst.append(('pdisk',
                                   disk,
                                   'id',
                                   '%s:%d' % (info['EnclosureDeviceId'],
                                              slot_num)))
                    hw_lst.append(('pdisk',
                                   disk,
                                   'size',
                                   info['CoercedSize'].split()[0]))
                for ld_num in range(megacli.ld_get_num(ctrl)):
                    disk = 'disk%d' % ld_num
                    info = megacli.ld_get_info(ctrl, ld_num)
                    hw_lst.append(('ldisk',
                                   disk,
                                   'current_access_policy',
                                   info['CurrentAccessPolicy']))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'current_cache_policy',
                                   info['CurrentCachePolicy']))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'disk_cache_policy',
                                   info['DiskCachePolicy']))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'name',
                                   info['Name']))
                    try:
                        hw_lst.append(('ldisk',
                                       disk,
                                       'number_of_drives',
                                       str(info['NumberOfDrives'])))
                    except:
                        pass
                    try:
                        hw_lst.append(('ldisk',
                                       disk,
                                       'number_of_drives_per_span',
                                       str(info['NumberOfDrivesPerSpan'])))
                    except:
                        pass
                    hw_lst.append(('ldisk',
                                   disk,
                                   'raid_level',
                                   info['RaidLevel']))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'sector_size',
                                   str(info['SectorSize'])))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'state',
                                   info['State']))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'Size',
                                   size_in_gb(info['Size'])))
                    hw_lst.append(('ldisk',
                                   disk,
                                   'strip_size',
                                   info['StripSize']))
        hw_lst.append(('disk', 'megaraid', 'count', str(disk_count)))
        return True
    else:
        return False


def detect_disks(hw_lst):
    'Detect disks.'
    names = diskinfo.disknames()
    sizes = diskinfo.disksizes(names)
    disks = [name for name, size in sizes.items() if size > 0]
    hw_lst.append(('disk', 'logical', 'count', str(len(disks))))
    for name in disks:
        hw_lst.append(('disk', name, 'size', str(sizes[name])))
        item_list = ['device/vendor', 'device/model', 'device/rev',
                     'queue/optimal_io_size', 'queue/physical_block_size']
        for my_item in item_list:
            try:
                with open('/sys/block/%s/%s' % (name, my_item), 'r') as dev:
                    hw_lst.append(('disk', name, my_item.split('/')[1],
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
            sdparm_cmd = Popen("sdparm -q --get=%s /dev/%s | "
                               "awk '{print $2}'" % (my_item, name),
                               shell=True,
                               stdout=PIPE)
            for line in sdparm_cmd.stdout:
                hw_lst.append(('disk', name, item_def.get(my_item),
                               line.rstrip('\n').strip()))

        # In some VMs, the disk-by id doesn't exists
        if os.path.exists('/dev/disk/by-id/'):
            for entry in os.listdir('/dev/disk/by-id/'):
                if os.path.realpath('/dev/disk/by-id/' + entry).split('/')[-1] == \
                   name:
                    id_name = "id"
                    if entry.startswith('wwn'):
                        id_name = "wwn-id"
                    elif entry.startswith('scsi'):
                        id_name = "scsi-id"
                    hw_lst.append(('disk', name, id_name, entry))


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


def get_cidr(netmask):
    'Convert a netmask to a CIDR.'
    binary_str = ''
    for octet in netmask.split('.'):
        binary_str += bin(int(octet))[2:].zfill(8)
    return str(len(binary_str.rstrip('0')))


def detect_infiniband(hw_lst):
    '''Detect Infiniband devinces.

To detect if an IB device is present, we search for a pci device.
This pci device shall be from vendor Mellanox (15b3) form class 0280
Class 280 stands for a Network Controller while ethernet device are 0200'''
    status, _ = cmd("lspci -d 15b3: -n|awk '{print $2}'|grep -q '0280'")
    if status == 0:
        ib_card = 0
        for devices in range(ib_card, len(ib.ib_card_drv())):
            card_type = ib.ib_card_drv()[devices]
            ib_infos = ib.ib_global_info(card_type)
            nb_ports = ib_infos['nb_ports']
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'card_type', card_type))
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'device_type', ib_infos['device_type']))
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'fw_version', ib_infos['fw_ver']))
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'hw_version', ib_infos['hw_ver']))
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'nb_ports', nb_ports))
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'sys_guid', ib_infos['sys_guid']))
            hw_lst.append(('infiniband', 'card%i' % ib_card,
                           'node_guid', ib_infos['node_guid']))
            for port in range(1, int(nb_ports)+1):
                ib_port_infos = ib.ib_port_info(card_type, port)
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'state', ib_port_infos['state']))
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'physical_state',
                               ib_port_infos['physical_state']))
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'rate', ib_port_infos['rate']))
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'base_lid', ib_port_infos['base_lid']))
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'lmc', ib_port_infos['lmc']))
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'sm_lid', ib_port_infos['sm_lid']))
                hw_lst.append(('infiniband', 'card%i_port%i' % (ib_card, port),
                               'port_guid', ib_port_infos['port_guid']))
        return True
    else:
        sys.stderr.write('Info: No Infiniband device found\n')
        return False


def get_uuid():
    'Get uuid from dmidecode'
    uuid_cmd = Popen("dmidecode -t 1 | grep UUID | "
                     "awk '{print $2}'",
                     shell=True,
                     stdout=PIPE)
    return uuid_cmd.stdout.read().rstrip()


def detect_system(hw_lst, output=None):
    'Detect system characteristics from the output of lshw.'

    socket_count = 0

    def find_element(xml, xml_spec, sys_subtype,
                     sys_type='product', sys_cls='system',
                     attrib=None, transform=None):
        'Lookup an xml element and populate hw_lst when found.'
        elt = xml.findall(xml_spec)
        if len(elt) >= 1:
            if attrib:
                txt = elt[0].attrib[attrib]
            else:
                txt = elt[0].text
            if transform:
                txt = transform(txt)
            hw_lst.append((sys_cls, sys_type, sys_subtype, txt))
            return txt
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
        uuid = get_uuid()
        if uuid:
            # If we have an uuid, let's manage a quirk list of stupid
            # serial numbers TYAN or Supermicro are known to provide
            # dirty serial numbers In that case, let's use the uuid
            # instead
            for i in hw_lst:
                if 'system' in i[0] and 'product' in i[1] and 'serial' in i[2]:
                    # Does the current serial number is part of the quirk list
                    if i[3] in ['0123456789']:
                        # Let's delete the stupid SN and use the UUID instead
                        hw_lst.remove(i)
                        hw_lst.append(('system', 'product', 'serial', uuid))
                        break
            hw_lst.append(('system', 'product', 'uuid', uuid))

        for elt in xml.findall(".//node[@id='core']"):
            name = elt.find('physid')
            if name is not None:
                find_element(elt, 'product', 'name', 'motherboard', 'system')
                find_element(elt, 'vendor', 'vendor', 'motherboard', 'system')
                find_element(elt, 'version', 'version', 'motherboard', 'system')
                find_element(elt, 'serial', 'serial', 'motherboard', 'system')

        for elt in xml.findall(".//node[@id='firmware']"):
            name = elt.find('physid')
            if name is not None:
                find_element(elt, 'version', 'version', 'bios', 'firmware')
                find_element(elt, 'date', 'date', 'bios', 'firmware')
                find_element(elt, 'vendor', 'vendor', 'bios', 'firmware')

        bank_count = 0
        for elt in xml.findall(".//node[@class='memory']"):
            if not elt.attrib['id'].startswith('memory'):
                continue
            try:
                location = re.search('memory(:.*)', elt.attrib['id']).group(1)
            except:
                location = ''
            name = elt.find('physid')
            if name is not None:
                find_element(elt, 'size', 'size', 'total', 'memory')
                for bank_list in elt.findall(".//node[@id]"):
                    if 'bank:' in bank_list.get('id'):
                        bank_count = bank_count+1
                        for bank in elt.findall(".//node[@id='%s']" %
                                                (bank_list.get('id'))):
                            bank_id = bank_list.get('id').replace("bank:",
                                                                  "bank" +
                                                                  location +
                                                                  ":")
                            find_element(bank, 'size', 'size',
                                         bank_id, 'memory')
                            find_element(bank, 'clock', 'clock',
                                         bank_id, 'memory')
                            find_element(bank, 'description', 'description',
                                         bank_id, 'memory')
                            find_element(bank, 'vendor', 'vendor',
                                         bank_id, 'memory')
                            find_element(bank, 'product', 'product',
                                         bank_id, 'memory')
                            find_element(bank, 'serial', 'serial',
                                         bank_id, 'memory')
                            find_element(bank, 'slot', 'slot',
                                         bank_id, 'memory')
        if bank_count > 0:
            hw_lst.append(('memory', 'banks', 'count', str(bank_count)))

        for elt in xml.findall(".//node[@class='network']"):
            name = elt.find('logicalname')
            if name is not None:
                find_element(elt, 'businfo', 'businfo', name.text, 'network')
                find_element(elt, 'vendor', 'vendor', name.text, 'network')
                find_element(elt, 'product', 'product', name.text, 'network')
                find_element(elt, "configuration/setting[@id='firmware']",
                             'firmware', name.text, 'network', 'value')
                find_element(elt, 'size', 'size', name.text, 'network')
                ipv4 = find_element(elt, "configuration/setting[@id='ip']",
                                    'ipv4',
                                    name.text, 'network', 'value')
                if ipv4 is not None:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        netmask = socket.inet_ntoa(
                            fcntl.ioctl(sock, SIOCGIFNETMASK,
                                        struct.pack('256s', name.text))[20:24])
                        hw_lst.append(
                            ('network', name.text, 'ipv4-netmask', netmask))
                        cidr = get_cidr(netmask)
                        hw_lst.append(
                            ('network', name.text, 'ipv4-cidr', cidr))
                        hw_lst.append(
                            ('network', name.text, 'ipv4-network',
                             "%s" % IPNetwork('%s/%s' % (ipv4, cidr)).network))
                    except Exception:
                        sys.stderr.write('unable to get info for %s\n'
                                         % name.text)

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
                find_element(elt,
                             "configuration/setting[@id='autonegotiation']",
                             'autonegotiation', name.text, 'network', 'value')

                # lshw is not able to get the complete mac addr for ib
                # devices Let's workaround it with an ip command.
                if name.text.startswith('ib'):
                    cmds = "ip addr show %s | grep link | awk '{print $2}'"
                    status_ip, output_ip = cmd(cmds % name.text)
                    if status_ip == 0:
                        hw_lst.append(('network',
                                       name.text,
                                       'serial',
                                       output_ip.split('\n')[0].lower()))
                else:
                    find_element(elt, 'serial', 'serial', name.text, 'network',
                                 transform=string.lower)

                detect_utils.get_lld_status(hw_lst, name.text)

        for elt in xml.findall(".//node[@class='processor']"):
            name = elt.find('physid')
            if name is not None:
                hw_lst.append(('cpu', 'physical_%s' % (socket_count),
                               'physid', name.text))
                find_element(elt, 'product', 'product',
                             'physical_%s' % socket_count, 'cpu')
                find_element(elt, 'vendor', 'vendor',
                             'physical_%s' % socket_count, 'cpu')
                find_element(elt, 'version', 'version',
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
                cpuinfo_cmd = output_lines("grep flags /proc/cpuinfo |"
                                           "uniq | cut -d ':' -f 2")
                for line in cpuinfo_cmd:
                    hw_lst.append(('cpu', 'physical_%s' % (socket_count),
                                   'flags', line.rstrip('\n').strip()))

                socket_count = socket_count+1
    else:
        sys.stderr.write("Unable to run lshw: %s\n" % output)

    hw_lst.append(('cpu', 'physical', 'number', str(socket_count)))
    status, output = cmd('nproc')
    if status == 0:
        hw_lst.append(('cpu', 'logical', 'number', str(output)))

    osvendor_cmd = output_lines("lsb_release -is")
    for line in osvendor_cmd:
        hw_lst.append(('system', 'os', 'vendor', line.rstrip('\n').strip()))

    osinfo_cmd = output_lines("lsb_release -ds | tr -d '\"'")
    for line in osinfo_cmd:
        hw_lst.append(('system', 'os', 'version', line.rstrip('\n').strip()))

    uname_cmd = output_lines("uname -r")
    for line in uname_cmd:
        hw_lst.append(('system', 'kernel', 'version',
                       line.rstrip('\n').strip()))

    arch_cmd = output_lines("uname -i")
    for line in arch_cmd:
        hw_lst.append(('system', 'kernel', 'arch', line.rstrip('\n').strip()))

    cmdline_cmd = output_lines("cat /proc/cmdline")
    for line in cmdline_cmd:
        hw_lst.append(('system', 'kernel', 'cmdline',
                       line.rstrip('\n').strip()))


def _main():
    'Command line entry point.'
    hrdw = []

    detect_hpa(hrdw)
    detect_megacli(hrdw)
    detect_disks(hrdw)
    detect_system(hrdw)
    detect_ipmi(hrdw)
    detect_infiniband(hrdw)
    print(json.dumps(hrdw))

if __name__ == "__main__":
    _main()
