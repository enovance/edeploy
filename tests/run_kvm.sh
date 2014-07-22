#!/bin/bash
#
# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
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

set -e
DISK=kvm_storage.img
DISK_SIZE=4000 # in MB
HTTP_PORT=9000
INST=$1
MODE=$2
LOAD="$3"
HTTP_SERVER="$4"
DEBUG_SSH_PORT=2222
SSH_PORT=222
PYTHON_PID=0
RSYNC_PID=0
LOCKFILE=/var/run/edeploy.lock
SYSLINUX_VER=5.10

fatal_error() {
        echo $1;
        exit 1
}

check_binary() {
        type -p $1 >/dev/null || fatal_error "$1 is missing"
}

detect_kvm() {

    for kvm_bin in kvm qemu-kvm qemu-system-x86_64; do
        which $kvm_bin 2>/dev/null && return 0
    done
	fatal_error "Please Install KVM first"
}

prepare_disk() {
	if [ ! -f $DISK ]; then
		echo "Preparing system disk, please wait a short"
		qemu-img create -f qcow2 $DISK ${DISK_SIZE}M
	fi
}

run_kvm() {
    local kvm_bin=$(detect_kvm)

    if [ "$MODE" = "usb" ]; then
        LOAD_INDEX="0"
        DISK_INDEX="1"
        if [ "$1" = "local" ]; then
            LOAD_INDEX="1"
            DISK_INDEX="0"
        fi

        $kvm_bin --enable-kvm -m 512\
            -netdev user,id=net0,net=10.0.2.0/24,tftp=tftpboot,bootfile=/pxelinux.0 \
            -netdev user,id=net1,net=10.0.3.0/24 \
            -netdev user,id=net2,net=1.2.3.0/24 \
            -device virtio-net,netdev=net0,mac=52:54:12:34:00:01 \
            -device virtio-net,netdev=net1,mac=52:54:12:34:00:02 \
            -device virtio-net,netdev=net2,mac=52:54:12:34:00:03 \
            -drive file=$LOAD,if=virtio,id=drive-virtio-disk0,format=raw,cache=writeback,aio=native,media=disk,index=$LOAD_INDEX \
            -drive file=$DISK,if=virtio,id=drive-virtio-disk1,format=qcow2,cache=writeback,aio=native,media=disk,index=$DISK_INDEX \
            -serial stdio \
            -smbios type=1,manufacturer=kvm,product=edeploy_test_vm
    else
        BOOT_DEVICE="n"
        [ "$1" = "local" ] && BOOT_DEVICE="c"

        $kvm_bin --enable-kvm -m 512\
            -netdev user,id=net0,net=10.0.2.0/24,tftp=tftpboot,bootfile=/pxelinux.0,hostfwd=tcp::$SSH_PORT-:22,hostfwd=tcp::$DEBUG_SSH_PORT-:$DEBUG_SSH_PORT \
            -netdev user,id=net1,net=10.0.3.0/24 \
            -netdev user,id=net2,net=1.2.3.0/24 \
            -device virtio-net,netdev=net0,mac=52:54:12:34:00:01 \
            -device virtio-net,netdev=net1,mac=52:54:12:34:00:02 \
            -device virtio-net,netdev=net2,mac=52:54:12:34:00:03 \
            -drive file=$DISK,if=virtio,id=drive-virtio-disk0,format=qcow2,cache=writeback,aio=native,media=disk,index=0 \
            -boot $BOOT_DEVICE \
            -serial stdio \
            -smbios type=1,manufacturer=kvm,product=edeploy_test_vm
    fi
}


start_rsyncd() {
	cat > rsync-kvm.conf << EOF
use chroot = no
syslog facility = local5
pid file = rsyncd-edeploy.pid

[install]
	uid=root
	gid=root
	path=$INST/install

[metadata]
	uid=root
	gid=root
	path=$INST/metadata
EOF

	# Rsync shall die with the current test
	rsync --daemon --config rsync-kvm.conf --port 1515 --no-detach &
	RSYNC_PID=$!
}

start_httpd() {
	rm -f cgi-bin
	ln -sf ../server cgi-bin &>/dev/null
    if [ "$1" = "no_log" ]; then
        python -m CGIHTTPServer $HTTP_PORT &>/dev/null &
    else
        python -m CGIHTTPServer $HTTP_PORT &
    fi
	HTTP_PID=$!

    set +e
    echo "Waiting HTTP server to start"
    RETURN_CODE="7"
    while [ $RETURN_CODE -ne 0 ]; do
         curl -s http://localhost:${HTTP_PORT}/cgi-bin/upload.py &>/dev/null
         RETURN_CODE="$?"
         sleep .1
    done
    set -e
    echo "HTTP server started"
}

stop_httpd() {
    if [ ! -z $HTTP_PID ]; then
    	kill -9 $HTTP_PID &>/dev/null
    fi
	rm -f $LOCKFILE
}

stop_rsyncd() {
    if [ ! -z $RSYNC_PID ]; then
	    kill -9 $RSYNC_PID &>/dev/null
    fi
	rm -f rsyncd-edeploy.pid &>/dev/null
}

setup_pxe() {
	if [ ! -f tftpboot/pxelinux.0 -o ! -f tftpboot/ldlinux.c32 ]; then
		mkdir -p tftpboot
	        # Installing extlinux & mbr from source
		wget http://ftp.kernel.org/pub/linux/utils/boot/syslinux/syslinux-${SYSLINUX_VER}.tar.xz
		tar -xf syslinux-${SYSLINUX_VER}.tar.xz
		cp syslinux-${SYSLINUX_VER}/core/pxelinux.0 tftpboot/
		cp syslinux-${SYSLINUX_VER}/com32/elflink/ldlinux/ldlinux.c32 tftpboot/
		rm -rf syslinux-${SYSLINUX_VER}*
	fi
}

create_edeploy_conf() {
	cat > edeploy.conf << EOF
[SERVER]

HEALTHDIR=$PWD/../health/
CONFIGDIR=$PWD/../config/
HWDIR=$PWD/../config/hw
LOGDIR=$PWD/../config/logs
LOCKFILE=$LOCKFILE
USEPXEMNGR=False
PXEMNGRURL=http://192.168.122.1:8000/
EOF

# Insure upload.py can create its lock file locally
chmod a+rw .
chmod a+rw $PWD/../health/
chmod a+rw $PWD/../config/
chmod a+rw $PWD/../config/hw/
find $PWD/../config \
    -maxdepth 1 \
    -name '*.hw' -or \
    -name 'state' -or \
    -name 'kvm-test.cmdb' | xargs chmod a+rw

ln -sf $PWD/edeploy.conf /etc/
}

tweak_role() {
    # If no TEST_ROLE is given, let's consider mysql
    if [ -z "$TEST_ROLE" ]; then
        TEST_ROLE=mysql
    fi
    sed -i "s/set_role.*/set_role('$TEST_ROLE','$VERS',bootable_disk)/g" $PWD/../config/kvm-test.configure
   #sed -i "s/set_role('mysql', 'D7-F.1.0.0', bootable_disk)
}

stress-http() {
CONCURENT_HTTP_REQUESTS=$1
HTTP_SERVER=$2
SCRIPT_DIR="stress-http"
SCRIPT_FILE="upload"
PIDS=""
FAILED_CURL=0
FAILED_PYTHON=0
FAILED_MISSING=0
FAILED_ROLE=0

if [ -z "$HTTP_SERVER" ]; then
    HTTP_SERVER="localhost:${HTTP_PORT}"
fi

rm -rf $SCRIPT_DIR
mkdir -p $SCRIPT_DIR

cat > $SCRIPT_DIR/hw-match.py << EOF
[('disk', 'vda', 'size', '2'),
 ('system', 'product', 'name', 'edeploy_test_vm ()'),
 ('system', 'product', 'vendor', 'kvm'),
 ('system', 'memory', 'size', '536870912'),
 ('network', 'eth2', 'serial', '52:54:12:34:00:03'),
 ('network', 'eth2', 'ipv4', '1.2.3.15'),
 ('network', 'eth2', 'link', 'yes'),
 ('network', 'eth2', 'driver', 'virtio_net'),
 ('network', 'eth1', 'serial', '52:54:12:34:00:02'),
 ('network', 'eth1', 'ipv4', '10.0.3.15'),
 ('network', 'eth1', 'link', 'yes'),
 ('network', 'eth1', 'driver', 'virtio_net'),
 ('network', 'eth0', 'serial', '52:54:12:34:00:01'),
 ('network', 'eth0', 'ipv4', '10.0.2.15'),
 ('network', 'eth0', 'link', 'yes'),
 ('network', 'eth0', 'driver', 'virtio_net'),
 ('system', 'cpu', 'number', '1'),
 ('system', 'ipmi-fake', 'channel', 0)
]
EOF

echo "About to start the stress test on http://${HTTP_SERVER}/cgi-bin/upload.py"

START_TIME=$(date +"%s")
for instance in `seq 1 $CONCURENT_HTTP_REQUESTS`; do
    echo -n "Spawning http instance $instance pid="
    curl -o$SCRIPT_DIR/$SCRIPT_FILE.$instance --retry-delay 1 --retry-max-time 10 -F file=@$SCRIPT_DIR/hw-match.py http://${HTTP_SERVER}/cgi-bin/upload.py &>$SCRIPT_DIR/$SCRIPT_FILE.$instance.out &
    PID="$!"
    echo "$PID"
    PIDS="$PIDS $PID"
done
SPAWN_TIME=$(date +"%s")

MIN_WAIT=99999999999
MAX_WAIT=-1
COUNT=1
for pid in $PIDS; do
    REMAINING_PIDS=$(($CONCURENT_HTTP_REQUESTS - $COUNT))
    echo "Waiting http instance with pid=$pid : $REMAINING_PIDS remaining"
    START_WAIT=$(date +"%s")
    wait $pid
    PID_RETURN_CODE="$?"
    COUNT=$(($COUNT + 1))
    STOP_WAIT=$(date +"%s")
    WAIT_TIME=$(($STOP_WAIT - $START_WAIT))
    echo "$WAIT_TIME" >> $SCRIPT_DIR/wait
    if [ $WAIT_TIME -gt $MAX_WAIT ]; then
        MAX_WAIT=$WAIT_TIME
    fi
    if [ $WAIT_TIME -lt $MIN_WAIT ]; then
        MIN_WAIT=$WAIT_TIME
    fi
    if [ $PID_RETURN_CODE -ne 0 ]; then
        echo "pid=$pid failed at getting a script"
        FAILED_CURL=$((FAILED_CURL + 1))
    fi
done
WAIT_TIME=$(date +"%s")

for instance in `seq 1 $CONCURENT_HTTP_REQUESTS`; do
    if [ -e $SCRIPT_DIR/$SCRIPT_FILE.$instance ]; then
        grep -q "error in a Python program" $SCRIPT_DIR/$SCRIPT_FILE.$instance &&
            echo "Instance n°$instance failed with a python error : please check $SCRIPT_DIR/$SCRIPT_FILE.$instance" &&
            FAILED_PYTHON=$((FAILED_PYTHON + 1))

        # We need to check if a role is defined. If not that's a serious problem as the file can be damaged or incomplete
        # That's a good way to check file's integrity
        grep -v "def set_role" $SCRIPT_DIR/$SCRIPT_FILE.$instance | grep -q "set_role"
        if [ $? -ne 0 ]; then
            echo "Instance n°$instance failed is not a valid script_file : please check $SCRIPT_DIR/$SCRIPT_FILE.$instance" ;
            FAILED_ROLE=$((FAILED_ROLE + 1))
        fi
    else
            echo "Instance n°$instance didn't produce data : please check $SCRIPT_DIR/$SCRIPT_FILE.$instance*"
            FAILED_MISSING=$((FAILED_MISSING + 1))
    fi
done

REPORT_SPAWN_TIME=$(($SPAWN_TIME-$START_TIME))
REPORT_WAIT_TIME=$(($WAIT_TIME-$SPAWN_TIME))
AVERAGE_WAIT_TIME=$(echo "scale=3; $REPORT_WAIT_TIME / $CONCURENT_HTTP_REQUESTS" | bc | tr '.' ',')
TOTAL_FAILURES=$(($FAILED_CURL + FAILED_PYTHON + $FAILED_MISSING + $FAILED_ROLE))
STD_DEV_WAIT=$(awk '{sum+=$1; array[NR]=$1} END {for(x=1;x<=NR;x++){sumsq+=((array[x]-(sum/NR))**2);}print sqrt(sumsq/NR)}' $SCRIPT_DIR/wait | tr '.' ',')
echo "#######################"
echo "# Stress-http Results #"
echo "#######################"
printf "Number of requests  : %4d\n" $CONCURENT_HTTP_REQUESTS
echo "Failures counting"
printf "  CURL              : %4d\n" $FAILED_CURL
printf "  Python            : %4d\n" $FAILED_PYTHON
printf "  Missing files     : %4d\n" $FAILED_MISSING
printf "  No role defined   : %4d\n" $FAILED_ROLE
printf "  Total             : %4d\n" $TOTAL_FAILURES
echo "CURL timing"
printf "  Total Spawning  : %4d  seconds\n" $REPORT_SPAWN_TIME
printf "  Total Waiting   : %4d  seconds\n" $REPORT_WAIT_TIME
printf "  Min waiting     : %4d  seconds\n" $MIN_WAIT
printf "  Max waiting     : %4d  seconds\n" $MAX_WAIT
printf "  Average waiting : %7.2f seconds\n" $AVERAGE_WAIT_TIME
printf "  Std deviation   : %7.2f seconds\n" $STD_DEV_WAIT
}

do_exit() {
    set +e
    stop_httpd
    stop_rsyncd
}

############## MAIN
trap do_exit EXIT

check_binary curl

case "$MODE" in
    "stress-http")
        check_binary seq
        check_binary bc
        check_binary python
        if [ -z "$HTTP_SERVER" ]; then
            start_httpd no_log
        fi
        create_edeploy_conf
        if [ -z "$LOAD" ]; then
            LOAD=5
        fi

        stress-http $LOAD $HTTP_SERVER

        if [ -z "$HTTP_SERVER" ]; then
            stop_httpd
        fi
    ;;
    "health")
        setup_pxe
        prepare_disk
        start_httpd
        create_edeploy_conf
        run_kvm
        stop_httpd
    ;;
    "usb")
        prepare_disk
        run_kvm
        run_kvm local
    ;;
    *)
        check_binary rsync
        check_binary qemu-img
        check_binary python
        tweak_role
        setup_pxe
        start_rsyncd
        start_httpd
        create_edeploy_conf
        prepare_disk
        run_kvm
        run_kvm local
        stop_httpd
        stop_rsyncd
    ;;
esac
