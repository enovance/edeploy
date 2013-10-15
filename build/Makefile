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

SDIR=/root/edeploy
TOP=/var/lib/debootstrap
DVER=D7
PVER=F
REL=1.0.0
VERS=$(DVER)-$(PVER).$(REL)
DIST=wheezy

SRC=base
DST=pxe
IMG=initrd.pxe
HEALTH_IMG=health.pxe
ARCH=amd64
export PATH := /sbin:/bin::$(PATH)
SERV:=10.66.6.10
HSERV:=10.66.6.10
DEBUG=1
PYDIR=../src
PYSERVERDIR=../server

LOAD=5
HTTP=

INST=$(TOP)/install/$(VERS)
META=$(TOP)/metadata/$(VERS)

all: $(INST)/$(IMG) $(INST)/mysql.done

health-check: $(INST)/base.done init.health health-check.install $(PYDIR)/detect.py $(PYDIR)/hpacucli.py $(PYSERVERDIR)/matcher.py $(PYDIR)/diskinfo.py $(PYDIR)/ipmi.py
	./health-check.install $(INST)/base $(INST)/health-check $(HEALTH_IMG) $(VERS) $(DEBUG)

health-img: health-check
	./img.install $(INST)/base $(HEALTH_IMG) $(VERS) $(INST) $(SERV) $(HSERV) $(DEBUG) health

pxe $(INST)/$(IMG): $(INST)/base.done init pxe.install $(PYDIR)/detect.py $(PYDIR)/hpacucli.py $(PYSERVERDIR)/matcher.py $(PYDIR)/diskinfo.py $(PYDIR)/ipmi.py
	./pxe.install $(INST)/base $(INST)/pxe $(IMG) $(VERS) $(DEBUG)

img: $(INST)/$(IMG)
	./img.install $(INST)/base $(IMG) $(VERS) $(INST) $(SERV) $(HSERV) $(DEBUG)

base $(INST)/base.done: base.install policy-rc.d edeploy
	ENABLE_IB=$(ENABLE_IB) ARCH=$(ARCH) ./base.install $(INST)/base $(DIST) $(VERS)
	touch $(INST)/base.done

cloud $(INST)/cloud.done: cloud.install $(INST)/base.done
	./cloud.install $(INST)/base $(INST)/cloud $(VERS)
	touch $(INST)/cloud.done

devstack $(INST)/devstack.done: devstack.install $(INST)/cloud.done
	./devstack.install $(INST)/cloud $(INST)/devstack $(DIST) $(VERS)
	touch $(INST)/devstack.done

openstack $(INST)/openstack.done: openstack.install $(INST)/base.done
	./openstack.install $(INST)/base $(INST)/openstack $(VERS)
	touch $(INST)/openstack.done

openstack-controller $(INST)/openstack-controller.done: openstack-controller.install $(INST)/base.done
	./openstack-controller.install $(INST)/base $(INST)/openstack-controller $(VERS)
	touch $(INST)/openstack-controller.done

openstack-compute $(INST)/openstack-compute.done: openstack-compute.install $(INST)/base.done
	./openstack-compute.install $(INST)/base $(INST)/openstack-compute $(VERS)
	touch $(INST)/openstack-compute.done

openstack-swift-proxy $(INST)/openstack-swift-proxy.done: openstack-swift-proxy.install $(INST)/base.done
	./openstack-swift-proxy.install $(INST)/base $(INST)/openstack-swift-proxy $(VERS)
	touch $(INST)/openstack-swift-proxy.done

openstack-swift-storage $(INST)/openstack-swift-storage.done: openstack-swift-storage.install $(INST)/base.done
	./openstack-swift-storage.install $(INST)/base $(INST)/openstack-swift-storage $(VERS)
	touch $(INST)/openstack-swift-storage.done

mysql $(INST)/mysql.done: mysql.install $(INST)/base.done
	./mysql.install $(INST)/base $(INST)/mysql $(VERS)
	touch $(INST)/mysql.done

galera $(INST)/galera.done: galera.install $(INST)/base.done
	./galera.install $(INST)/base $(INST)/galera $(VERS)
	touch $(INST)/galera.done

haproxy $(INST)/haproxy.done: haproxy.install $(INST)/base.done
	./haproxy.install $(INST)/base $(INST)/haproxy $(VERS)
	touch $(INST)/haproxy.done

ceph $(INST)/ceph.done: ceph.install $(INST)/base.done
	./ceph.install $(INST)/base $(INST)/ceph $(VERS)
	touch $(INST)/ceph.done

docker $(INST)/docker.done: docker.install $(INST)/base.done
	./docker.install $(INST)/base $(INST)/docker $(VERS)
	touch $(INST)/docker.done

puppet-master $(INST)/puppet-master.done: puppet-master.install $(INST)/base.done
	./puppet-master.install $(INST)/base $(INST)/puppet-master $(VERS)
	touch $(INST)/puppet-master.done

chef-server $(INST)/chef-server.done: chef-server.install $(INST)/base.done
	./chef-server.install $(INST)/base $(INST)/chef-server $(VERS)
	touch $(INST)/chef-server.done

health-test: health-check
	cd ../tests/tftpboot/; ln -sf $(INST)/base/boot/vmlinuz* vmlinuz; ln -sf $(INST)/initrd.pxe initrd;
	cd ../tests; ./run_kvm.sh $(TOP) health

test: $(INST)/$(IMG)
	cd ../tests/tftpboot/; ln -sf $(INST)/base/boot/vmlinuz* vmlinuz; ln -sf $(INST)/initrd.pxe initrd;
	cd ../tests; ./run_kvm.sh $(TOP)

stress-http:
	cd ../tests; ./run_kvm.sh $(TOP) stress-http $(LOAD) $(HTTP)


dist:
	tar zcvf ../edeploy.tgz Makefile init init.common README.rst *.install edeploy update-scenario.sh *.py

clean:
	-rm -f *~ $(INST)/*.done

distclean: clean
	-rm -rf $(INST)/*
