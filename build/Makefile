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

# Exporting ALL variables to other childs
.EXPORT_ALL_VARIABLES:

MAKEFILE_DIR=$(shell pwd)
SDIR=/root/edeploy
TOP=/var/lib/debootstrap
DVER=D7
VERSION:=1.9.0
VERS=$(DVER)-$(VERSION)
DIST=wheezy

IMG=initrd.pxe
HEALTH_IMG=health.pxe
ARCH=amd64
export PATH := /sbin:/bin::$(PATH)
SERV:=10.66.6.10
HSERV:=10.66.6.10
DEBUG=1
UPLOAD_LOG:=0
PYDIR=../src
PYSERVERDIR=../server

LOAD=5
HTTP=
MAKEFILE_TARGET=$(MAKECMDGOALS)
CURRENT_TARGET=$@
export MAKEFILE_TARGET
export CURRENT_TARGET

INST=$(TOP)/install/$(VERS)
META=$(TOP)/metadata/$(VERS)

TEST_ROLE:=base

DEPS = respawn
HEALTH_DEPS = $(DEPS) $(PYDIR)/health_bench.py $(PYDIR)/health-check.py $(PYDIR)/health-client.py $(PYDIR)/health_libs.py $(PYDIR)/health_messages.py $(PYDIR)/health_protocol.py $(PYDIR)/health-server.py

ROLES = base pxe health-check deploy

all: $(ROLES)

health-check: $(INST)/$(HEALTH_IMG)
$(INST)/$(HEALTH_IMG): $(INST)/base.done  init.health init.common health-check.install $(HEALTH_DEPS)
	DEPS="$(DEPS)" ENABLE_IB=y ENABLE_MELLANOX=n ./health-check.install $(INST)/base $(INST)/health-check $(HEALTH_IMG) $(VERS) $(DEBUG)

health-img: $(INST)/$(HEALTH_IMG)
	./img.install $(INST)/base $(HEALTH_IMG) $(VERS) $(INST) $(SERV) $(HSERV) $(DEBUG) health

pxe: $(INST)/$(IMG)
$(INST)/$(IMG): $(INST)/base.done init init.common pxe.install $(DEPS) $(PYSERVERDIR)/upload.py
	DEPS="$(DEPS) $(PYSERVERDIR)/upload.py $(PYSERVERDIR)/try_match" ENABLE_IB=y ENABLE_MELLANOX=n ./pxe.install $(INST)/base $(INST)/pxe $(IMG) $(VERS) $(DEBUG)

img: $(INST)/$(IMG)
	./img.install $(INST)/base $(IMG) $(VERS) $(INST) $(SERV) $(HSERV) $(DEBUG)

base: $(INST)/base.done
$(INST)/base.done: base.install policy-rc.d edeploy common packages distributions repositories $(DVER)-ids.tables mngids.py
	mkdir -p $(INST)
	if [ -r $(DVER)-ids.tables ]; then cp $(DVER)-ids.tables $(INST)/ids.tables; fi
	./base.install $(INST)/base $(DIST) $(VERS)
	touch $(INST)/base.done

deploy: $(INST)/deploy.done
$(INST)/deploy.done: deploy.install $(INST)/base.done
	./deploy.install $(INST)/base $(INST)/deploy $(VERS)
	touch $(INST)/deploy.done

health-test: health-check
	cd ../tests/tftpboot/; ln -sf $(INST)/base/boot/vmlinuz* vmlinuz; ln -sf $(INST)/health.pxe initrd;
	cd ../tests; ./run_kvm.sh $(TOP) health

test: $(INST)/$(IMG) $(TEST_ROLE)
	cd ../tests/tftpboot/; ln -sf $(INST)/base/boot/vmlinuz* vmlinuz; ln -sf $(INST)/initrd.pxe initrd;
	cd ../tests; ./run_kvm.sh $(TOP)

stress-http:
	cd ../tests; ./run_kvm.sh $(TOP) stress-http $(LOAD) $(HTTP)

benchmark: $(INST)/benchmark.done
$(INST)/benchmark.done: benchmark.install $(INST)/base.done
	ENABLE_IB=y ./benchmark.install $(INST)/base $(INST)/benchmark $(VERS)
	touch $(INST)/benchmark.done

dist:
	tar zcvf ../edeploy.tgz Makefile init init.common README.rst *.install *.exclude edeploy update-scenario.sh *.py

clean:
	-rm -f *~ $(INST)/*.done

distclean: clean
	-rm -rf $(INST)/*

version:
	@echo "$(VERS)"

.PHONY: base img base pxe test stress-http benchmark dist clean distclean version health-check
