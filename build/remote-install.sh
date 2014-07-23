#!/bin/sh
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

# Copy an edeploy role to a remote system, install Grub2 on it and reboot

if [ $# != 4 ]; then
    echo "Usage: $0 <role source dir> <remote ssh host> <rsync server> <rsync port>" 1>&2
    exit 1
fi

src="$1"
DST="$2"
RSERV="$3"
PORT="$4"

set -e

EXCL=$(mktemp)
SCR=$(mktemp)

cleanup() {
    rm -f "$EXCL" "$SCR"
}

trap cleanup 0

cat > "$EXCL" <<EOF
/dev/
/etc/adjtime
/etc/fstab
/etc/mtab
/etc/network/interfaces
/etc/network/run
/etc/resolv.conf
/etc/ssh/ssh_host_dsa_key
/etc/ssh/ssh_host_dsa_key.pub
/etc/ssh/ssh_host_ecdsa_key
/etc/ssh/ssh_host_ecdsa_key.pub
/etc/ssh/ssh_host_rsa_key
/etc/ssh/ssh_host_rsa_key.pub
/lib/init/rw
/proc
/root/.ssh
/run
/sys
EOF

cat > "$SCR" <<EOF
#!/bin/bash

set -x

cat >> /var/lib/edeploy/conf <<EOL
RSERV=$RSERV
RSERV_PORT=$PORT
EOL

eval \$(tr ' ' '\n' < /proc/cmdline | egrep ^root=)

case "\$root" in
    UUID=*)
	eval \$root
	DISK=\$(readlink -f /dev/disk/by-uuid/\$UUID)
	;;
    *)
	if [ -b \$root ]; then
	    DISK=\$(readlink -f \$root)
	else
	    echo "Unable to find the root device"
	    exit 1
	fi
	;;
esac

DISK=\$(sed 's/.$//' <<< \$DISK)

/usr/sbin/grub-install \${DISK}
/usr/sbin/grub-mkconfig -o /boot/grub/grub.cfg

echo "1" > /proc/sys/kernel/sysrq

for k in s u; do
    echo "\$k" > /proc/sysrq-trigger
done

reboot -f
EOF

scp "$SCR" "$DST":/var/run
rsync -e ssh -avP --numeric-ids --delete-after --exclude-from="$EXCL" "$src/"  "$DST":/
ssh "$DST" bash /var/run/$(basename $SCR)

# remote-install.sh ends here
