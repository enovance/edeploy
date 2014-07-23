#!/bin/bash

# Script used by Jenkins jobs to build roles and archive them if the
# target directory exists

if [ $# -lt 3 ]; then
    echo "$0 <src dir> <build dir> <archive dir> [<make params>...]" 1>&2
    exit 1
fi

set -e

SRC="$1"
shift
DIR="$1"
shift
ARCH="$1"
shift

if [ -f /var/run/froze-builds ]; then
    exit 0
fi

if [ -z "$ROLES" ]; then
    ROLES="base pxe health-check deploy"
fi

set -x

cd $SRC
sudo mkdir -p "$DIR"/install
RC=0
BROKEN=

for role in $ROLES; do
    if sudo env VIRTUALIZED=$VIRTUALIZED make TOP="$DIR" ARCHIVE="$ARCH" "$@" $role; then
	if [ -d "$ARCH" ]; then
	    VERS=$(sudo make TOP="$DIR" "$@" version)
	    mkdir -p "$ARCH"/$VERS/
	    sudo rsync -a "$DIR"/install/$VERS/*.* "$ARCH"/$VERS/
            if [ -d "$DIR"/install/$VERS/base/boot ]; then
                sudo rsync -a "$DIR"/install/$VERS/base/boot/vmlinuz* "$ARCH"/$VERS/vmlinuz
                (cd "$ARCH"/$VERS; md5sum vmlinuz > vmlinuz.md5)
            fi
	    git rev-parse HEAD > "$ARCH"/$VERS/$role.rev
            #TODO: do not work on Jenkins, because of local tags
            # OLD=$(git describe --abbrev=0 --tags)
            # /srv/edeploy/tools/pkg-diff.sh $ARCH/$DVER-$OLD/$role.packages $ARCH/$VERS/$role.packages > $SRC/$DVER-$role-diff
	fi
    else
	BROKEN="$BROKEN $role"
	RC=1
    fi
done

set +x

if [ -n "$BROKEN" ]; then
    echo "BROKEN ROLES:$BROKEN"
fi

exit $RC
